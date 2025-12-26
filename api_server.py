
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import time
from datetime import datetime
import pandas as pd
import json
import yfinance as yf # For currency rates

# Import Bot Modules
import config
from data_feed import DataFeed
from strategy_trend import TrendPullbackStrategy
import indicators

app = FastAPI(title="IQ Bot API", description="Backend for Mobile App")

# Enable CORS (allow mobile app to connect)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global State ---
class BotState:
    def __init__(self):
        self.is_running = False
        self.data_feed = DataFeed()
        self.strategy = TrendPullbackStrategy()
        self.signals = [] # List of signals
        self.last_update = None
        self.auto_trade_enabled = False
        self.sound_queue = [] # For app notifications
        self.active_pairs = config.PAIRS_OTC
        self.trade_amount = config.TRADE_AMOUNT
        self.account_currency = "USD" # Default
        self.expiry_minutes = config.EXPIRY_MINUTES
        self.stop_loss = config.STOP_LOSS_LIMIT
        self.profit_goal = config.SESSION_PROFIT_GOAL
        self.logs = []

    def add_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        # Keep logs manageable
        if len(self.logs) > 100:
            self.logs.pop(0)

bot_state = BotState()

# --- Background Task ---
def bot_loop():
    """
    Main loop running in background thread.
    Replaces the Streamlit 'while' loop.
    """
    print("Bot Loop Started")
    while True:
        if bot_state.is_running:
            try:
                # 1. Update Data & Check Signals
                for ticker in bot_state.active_pairs:
                    # Fetch Data (1d is enough as per recent optimization)
                    df = bot_state.data_feed.fetch_data(symbol=ticker, period="1d", interval=config.ENTRY_TIMEFRAME)
                    
                    if df is None or df.empty:
                        continue

                    # Calculate Indicators
                    df = indicators.calculate_indicators(df)
                    
                    # Update Outcomes for existing signals
                    bot_state.strategy.update_outcomes(df, bot_state.signals, current_asset=ticker)
                    
                    # Analyze Strategy
                    signal = bot_state.strategy.analyze_1m(df, symbol=ticker)
                    
                    if signal:
                        # Deduplicate signals
                        # Check if we already have this signal for this time
                        existing = [s for s in bot_state.signals if s['asset'] == ticker and s['time'] == signal['time']]
                        
                        if not existing:
                            # Convert timestamp to string for JSON serialization
                            signal['time_str'] = str(signal['time'])
                            signal['status'] = 'PENDING'
                            
                            bot_state.signals.append(signal)
                            bot_state.add_log(f"SIGNAL: {signal['type']} {ticker}")
                            bot_state.sound_queue.append("notification")
                            
                            # Auto Trade Execution
                            if bot_state.auto_trade_enabled:
                                if not bot_state.data_feed.is_connected:
                                    bot_state.add_log(f"Skipped Auto-Trade {ticker}: Not Connected")
                                else:
                                    bot_state.add_log(f"Executing Auto-Trade: {ticker} {signal['type']}")
                                    success, msg = bot_state.data_feed.execute_trade(
                                        symbol=ticker,
                                        action=signal['type'],
                                        amount=bot_state.trade_amount,
                                        duration=bot_state.expiry_minutes,
                                        trade_mode="AUTO"
                                    )
                                    
                                    # Update Signal Status
                                    sig_idx = -1
                                    if bot_state.signals[-1]['asset'] == ticker:
                                        if success:
                                            bot_state.signals[sig_idx]['status'] = 'EXECUTED'
                                            bot_state.signals[sig_idx]['execution_msg'] = msg
                                            bot_state.sound_queue.append("money")
                                            bot_state.add_log(f"Trade Success: {msg}")
                                        else:
                                            bot_state.signals[sig_idx]['status'] = 'FAILED'
                                            bot_state.signals[sig_idx]['execution_msg'] = msg
                                            bot_state.add_log(f"Trade Failed: {msg}")

                bot_state.last_update = datetime.now().isoformat()
                
            except Exception as e:
                print(f"Loop Error: {e}")
                bot_state.add_log(f"Loop Error: {str(e)}")
        
        # Sleep to prevent CPU hogging (10 seconds loop)
        time.sleep(10)

# Start Background Thread
t = threading.Thread(target=bot_loop, daemon=True)
t.start()

# --- Pydantic Models ---
class ConnectRequest(BaseModel):
    email: str
    password: str
    account_type: str = "PRACTICE"

class ConfigRequest(BaseModel):
    auto_trade: bool
    trade_amount: float
    currency: str = "USD"
    expiry_minutes: int = 2
    stop_loss: int = 2
    profit_goal: float = 5.0
    active_pairs: list = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC"]

# --- Rate Caching ---
rate_cache = {'USD': 1.0, 'NGN': 1650.0, 'EUR': 0.92, 'GBP': 0.77}
last_rate_update = 0

def get_rates():
    global rate_cache, last_rate_update
    if time.time() - last_rate_update < 3600 and len(rate_cache) > 1:
        return rate_cache
        
    print("Fetching Exchange Rates...")
    try:
        # NGN (USD -> NGN)
        df = yf.download("NGN=X", period="1d", progress=False)
        if not df.empty:
            val = df['Close'].iloc[-1]
            if hasattr(val, 'item'): val = val.item()
            rate_cache['NGN'] = float(val)
            
        # EUR (EUR -> USD) => We need USD -> EUR (1/x)
        df = yf.download("EURUSD=X", period="1d", progress=False)
        if not df.empty:
            val = df['Close'].iloc[-1]
            if hasattr(val, 'item'): val = val.item()
            rate_cache['EUR'] = 1.0 / float(val)

        # GBP (GBP -> USD)
        df = yf.download("GBPUSD=X", period="1d", progress=False)
        if not df.empty:
            val = df['Close'].iloc[-1]
            if hasattr(val, 'item'): val = val.item()
            rate_cache['GBP'] = 1.0 / float(val)
            
        last_rate_update = time.time()
    except Exception as e:
        print(f"Rate Fetch Error: {e}")
        
    return rate_cache

# --- API Endpoints ---

@app.get("/")
def read_root():
    return {"status": "IQ Bot API Running", "version": "1.1"}

@app.post("/connect")
def connect_iq(req: ConnectRequest):
    success, message = bot_state.data_feed.connect_iq(req.email, req.password, req.account_type)
    if success:
        bot_state.add_log(f"Connected to IQ Option ({req.account_type})")
        # Update Account Currency
        bot_state.account_currency = bot_state.data_feed.get_account_currency()
        bot_state.add_log(f"Account Currency: {bot_state.account_currency}")
    else:
        bot_state.add_log(f"Connection Failed: {message}")
    return {"success": success, "message": message}

@app.post("/disconnect")
def disconnect_iq():
    bot_state.data_feed.is_connected = False
    bot_state.data_feed.use_iq = False
    bot_state.data_feed.iq_api = None # Clear instance
    bot_state.add_log("Disconnected from IQ Option")
    return {"status": "disconnected"}

@app.get("/rates")
def get_exchange_rates():
    return get_rates()

@app.get("/status")
def get_status():
    return {
        "is_running": bot_state.is_running,
        "is_connected": bot_state.data_feed.is_connected,
        "auto_trade": bot_state.auto_trade_enabled,
        "balance": bot_state.data_feed.iq_api.get_balance() if bot_state.data_feed.is_connected else 0,
        "last_update": bot_state.last_update,
        "logs": bot_state.logs[-10:], # Last 10 logs
        "config": {
            "expiry": bot_state.expiry_minutes,
            "stop_loss": bot_state.stop_loss,
            "profit_goal": bot_state.profit_goal,
            "pairs": bot_state.active_pairs,
            "trade_amount": bot_state.trade_amount
        }
    }

@app.post("/start")
def start_bot():
    bot_state.is_running = True
    bot_state.add_log("Bot Started")
    return {"status": "started"}

@app.post("/stop")
def stop_bot():
    bot_state.is_running = False
    bot_state.add_log("Bot Stopped")
    return {"status": "stopped"}

@app.post("/config")
def update_config(req: ConfigRequest):
    bot_state.auto_trade_enabled = req.auto_trade
    bot_state.expiry_minutes = req.expiry_minutes
    bot_state.stop_loss = req.stop_loss
    bot_state.profit_goal = req.profit_goal
    bot_state.active_pairs = req.active_pairs
    
    # Update Strategy Instance
    if bot_state.strategy:
        bot_state.strategy.expiry_minutes = req.expiry_minutes
        bot_state.strategy.stop_loss_limit = req.stop_loss

    # Currency Conversion Logic
    try:
        rates = get_rates()
        input_currency = req.currency
        account_currency = bot_state.account_currency
        
        # 1. Convert Input -> USD
        # Rate is USD -> Currency (e.g. 1 USD = 1600 NGN)
        rate_input = rates.get(input_currency, 1.0)
        amount_usd = req.trade_amount / rate_input
        
        # 2. Convert USD -> Account Currency
        rate_account = rates.get(account_currency, 1.0)
        final_amount = amount_usd * rate_account
        
        bot_state.trade_amount = round(final_amount, 2)
        
        bot_state.add_log(f"Config: {req.trade_amount}{input_currency} -> {bot_state.trade_amount}{account_currency}")
    except Exception as e:
        print(f"Conversion Error: {e}")
        bot_state.trade_amount = req.trade_amount # Fallback
        
    return {"status": "updated", "converted_amount": bot_state.trade_amount}

@app.get("/chart_data")
def get_chart_data(symbol: str = "EURUSD-OTC"):
    """
    Returns last 50 candles for charting.
    """
    try:
        df = bot_state.data_feed.fetch_data(symbol=symbol, period="1d", interval=config.ENTRY_TIMEFRAME)
        if df is None or df.empty:
            return {"error": "No data"}
        
        # Calculate indicators if not present
        if 'ema_fast' not in df.columns:
            df = indicators.calculate_indicators(df)
            
        # Limit to last 50 for mobile performance
        df_slice = df.tail(50)
        
        data = []
        for index, row in df_slice.iterrows():
            data.append({
                "timestamp": index.timestamp() * 1000, # ms for JS
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close'],
                "ema_fast": row.get('ema_fast', None),
                "ema_slow": row.get('ema_slow', None)
            })
            
        return {"symbol": symbol, "data": data}
    except Exception as e:
        return {"error": str(e)}

@app.get("/signals")
def get_signals():
    # Return recent signals
    return bot_state.signals[-20:] # Last 20

@app.get("/sound")
def pop_sound():
    if bot_state.sound_queue:
        return {"sound": bot_state.sound_queue.pop(0)}
    return {"sound": None}

if __name__ == "__main__":
    # Host 0.0.0.0 allows access from other devices (like mobile phone)
    import socket
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"\n[INFO] Server running. Mobile App URL: http://{local_ip}:8000\n")
    except:
        pass
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
