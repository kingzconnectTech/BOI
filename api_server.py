import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import time
import pandas as pd
import logging
from config import config
from data_feed import data_feed
from strategy_trend import TrendStrategy

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API")

app = FastAPI(title="IQ Bot Headless Server")

# Enable CORS for all origins (allows UI to connect)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

strategy = TrendStrategy()

# --- State ---
class BotState:
    def __init__(self):
        self.is_running = False
        self.active_trades = []
        self.logs = []
        self.session_profit = 0.0
        self.start_balance = 0.0

    def add_log(self, message: str):
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self.logs.append(entry)
        if len(self.logs) > 200:
            self.logs.pop(0)
        logger.info(message)

bot = BotState()

# --- Background Loop ---
def bot_loop():
    logger.info("Bot loop thread started")
    while True:
        if bot.is_running and data_feed.connected:
            try:
                # Update balance occasionally
                current_balance = data_feed.get_balance()
                if bot.start_balance == 0:
                    bot.start_balance = current_balance
                bot.session_profit = current_balance - bot.start_balance

                # Stop if limits reached
                if bot.session_profit >= config.TARGET_PROFIT:
                    bot.add_log("Target profit reached. Stopping.")
                    bot.is_running = False
                    continue
                
                if bot.session_profit <= -config.STOP_LOSS:
                    bot.add_log("Stop loss reached. Stopping.")
                    bot.is_running = False
                    continue

                # Refresh open assets periodically or just use config.ASSETS if fixed
                # For "auto-trade all pairs", we should update the list dynamically.
                # Only update occasionally to avoid spamming the API
                if int(time.time()) % 60 == 0:
                     open_pairs = data_feed.get_open_pairs()
                     if open_pairs:
                         config.ASSETS = open_pairs
                         bot.add_log(f"Updated asset list: {len(config.ASSETS)} pairs open")

                # Iterate assets
                for asset in config.ASSETS:
                    if not bot.is_running: break # Check interrupt

                    # Get candles
                    candles = data_feed.get_candles(asset, config.TIMEFRAME, limit=10)
                    if candles:
                        # Convert to DataFrame
                        # candles is usually a list of dicts: [{'id': ..., 'open': ..., 'close': ...}, ...]
                        # We need to ensure it's in the right format for strategy
                        # IQ Option API returns dict with keys 'open', 'close', 'min', 'max', 'volume' usually?
                        # Or it returns a dict of dicts? 
                        # stable_api get_candles returns a list of dicts.
                        
                        df = pd.DataFrame(candles)
                        
                        # Rename columns from IQ Option format (max/min) to standard (high/low)
                        if 'max' in df.columns:
                            df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
                        
                        # Generate signal
                        signal = strategy.check_signal(df)
                        
                        if signal:
                            bot.add_log(f"Signal found for {asset}: {signal}")
                            success, trade_id = data_feed.place_trade(
                                asset, 
                                config.TRADE_AMOUNT, 
                                signal, 
                                config.EXPIRY_MINUTES
                            )
                            if success:
                                bot.add_log(f"Trade placed: {trade_id}")
                                # Simple sleep to avoid multiple trades on same candle?
                                # Ideally we should track last trade time per asset.
                                # For "easy trades" user wants to see action, so maybe just sleep a bit.
                                time.sleep(10) 
                            else:
                                bot.add_log(f"Trade failed: {trade_id}")
                    
                    time.sleep(1) # Small delay between assets
            except Exception as e:
                bot.add_log(f"Error in bot loop: {e}")
                time.sleep(5)
        else:
            time.sleep(2) # Idle wait

# Start the loop in a daemon thread
t = threading.Thread(target=bot_loop, daemon=True)
t.start()

# --- Models ---
class StartRequest(BaseModel):
    email: str
    password: str
    mode: str = "PRACTICE"

class ConfigUpdate(BaseModel):
    trade_amount: float = None
    assets: list[str] = None

# --- Endpoints ---
@app.get("/status")
def get_status():
    return {
        "running": bot.is_running,
        "connected": data_feed.connected,
        "balance": data_feed.get_balance() if data_feed.connected else 0,
        "session_profit": bot.session_profit,
        "logs": bot.logs[-50:], # Send last 50 logs
        "config": {
            "assets": config.ASSETS,
            "target": config.TARGET_PROFIT
        }
    }

@app.get("/")
def root():
    return {
        "status": "Headless Bot Running", 
        "connected": data_feed.connected, 
        "running": bot.is_running
    }

@app.post("/start")
def start_bot(req: StartRequest):
    if bot.is_running:
        return {"message": "Already running"}
    
    # Set credentials and connect
    data_feed.set_credentials(req.email, req.password)
    config.MODE = req.mode
    
    bot.add_log("Connecting...")
    if data_feed.connect():
        bot.is_running = True
        bot.start_balance = data_feed.get_balance()
        bot.add_log(f"Connected. Balance: {bot.start_balance}")
        
        # Update assets immediately upon connection
        bot.add_log("Fetching open pairs...")
        open_pairs = data_feed.get_open_pairs()
        if open_pairs:
            config.ASSETS = open_pairs
            bot.add_log(f"Trading on {len(open_pairs)} open pairs: {', '.join(open_pairs[:5])}...")
        else:
            bot.add_log("Warning: No open pairs found or fetch failed.")
            
        return {"status": "started", "balance": bot.start_balance}
    else:
        bot.add_log("Connection failed")
        raise HTTPException(status_code=400, detail="Connection failed")

@app.post("/stop")
def stop_bot():
    bot.is_running = False
    bot.add_log("Bot stopped by user")
    return {"status": "stopped"}

@app.get("/logs")
def get_logs():
    return {"logs": bot.logs}

@app.post("/config")
def update_config(req: ConfigUpdate):
    if req.trade_amount:
        config.TRADE_AMOUNT = req.trade_amount
    if req.assets:
        config.ASSETS = req.assets
    return {"status": "updated", "config": {
        "trade_amount": config.TRADE_AMOUNT,
        "assets": config.ASSETS
    }}

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8001, reload=True)
