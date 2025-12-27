import uvicorn
from fastapi import FastAPI, HTTPException, Body, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import time
from datetime import datetime
import pandas as pd
import json
import uuid
import yfinance as yf # For currency rates
from exponent_server_sdk import PushClient, PushMessage

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

# --- Session Management ---
class BotState:
    def __init__(self, session_id):
        self.session_id = session_id
        self.is_running = False
        self.data_feed = DataFeed(session_id=session_id)
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
        self.session_profit = 0.0
        self.total_losses = 0
        self.consecutive_losses = 0
        self.loss_memory = [] # Stores conditions of losing trades
        self.logs = []
        self.push_tokens = set() # User-specific push tokens

    def add_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        # Keep logs manageable
        if len(self.logs) > 100:
            self.logs.pop(0)

class SessionManager:
    def __init__(self):
        self.sessions = {} # token -> BotState

    def create_session(self):
        token = str(uuid.uuid4())
        self.sessions[token] = BotState(session_id=token)
        return token

    def get_session(self, token: str):
        return self.sessions.get(token)

    def remove_session(self, token: str):
        if token in self.sessions:
            # Ensure disconnected
            try:
                self.sessions[token].data_feed.disconnect()
            except:
                pass
            del self.sessions[token]

session_manager = SessionManager()

# --- Dependency ---
async def get_current_bot(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    # Expect format "Bearer <token>"
    try:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
             raise HTTPException(status_code=401, detail="Invalid Authorization Header Format")
        token = parts[1]
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Authorization Header Format")

    bot = session_manager.get_session(token)
    if not bot:
        raise HTTPException(status_code=401, detail="Invalid or Expired Session")
    return bot

# --- Push Notifications ---
def send_push_notification(bot: BotState, title, body):
    # Run in thread to not block bot loop
    def _send():
        for token in list(bot.push_tokens):
            try:
                PushClient().publish(
                    PushMessage(to=token, title=title, body=body)
                )
            except Exception as e:
                print(f"Push Error: {e}")
    threading.Thread(target=_send).start()

# --- Background Task ---
def bot_loop():
    """
    Main loop running in background thread.
    Iterates over all active sessions.
    """
    print("Bot Loop Started")
    while True:
        # Snapshot of sessions
        active_sessions = list(session_manager.sessions.values())
        
        for bot_state in active_sessions:
            if bot_state.is_running:
                try:
                    # 1. Update Data & Check Signals
                    for ticker in bot_state.active_pairs:
                        # Fetch Data
                        df = bot_state.data_feed.fetch_data(symbol=ticker, period="1d", interval=config.ENTRY_TIMEFRAME)
                        
                        if df is None or df.empty:
                            continue

                        # Calculate Indicators
                        df = indicators.calculate_indicators(df)
                        
                        # Update Outcomes for existing signals
                        bot_state.strategy.update_outcomes(df, bot_state.signals, current_asset=ticker)
                        
                        # --- CLEANUP: Expire old PENDING signals ---
                        now_ts = datetime.now()
                        for s in bot_state.signals:
                            if s['status'] == 'PENDING':
                                try:
                                    sig_time = s['time']
                                    if isinstance(sig_time, pd.Timestamp):
                                        sig_time = sig_time.to_pydatetime()
                                    
                                    if (now_ts - sig_time).total_seconds() > 300:
                                        s['status'] = 'EXPIRED'
                                except:
                                    pass

                        # --- Process Completed Trades (Profit/Loss & ML) ---
                        for sig in bot_state.signals:
                            if sig.get('processed_outcome'): continue
                            
                            outcome = sig.get('outcome')
                            
                            # Verification for Real Trades
                            if sig.get('status') == 'EXECUTED' and 'trade_id' in sig:
                                real_outcome = bot_state.data_feed.check_trade_result(sig['trade_id'], sig.get('trade_type', 'BINARY'))
                                
                                if real_outcome in ['WIN', 'LOSS', 'TIE']:
                                    outcome = real_outcome
                                    sig['outcome'] = real_outcome
                                else:
                                    continue # Wait for API

                            if outcome in ['WIN', 'LOSS']:
                                sig['processed_outcome'] = True
                                
                                profit = 0
                                if outcome == 'WIN':
                                    profit = bot_state.trade_amount * 0.85
                                    bot_state.session_profit += profit
                                    bot_state.consecutive_losses = 0
                                    send_push_notification(bot_state, "Trade Won 💰", f"{ticker} Profit: +{profit:.2f}")
                                elif outcome == 'LOSS':
                                    profit = -bot_state.trade_amount
                                    bot_state.session_profit += profit
                                    bot_state.consecutive_losses += 1
                                    bot_state.total_losses += 1
                                    send_push_notification(bot_state, "Trade Loss 🔻", f"{ticker} Loss: {profit:.2f}")
                                    
                                    if 'indicators' in sig:
                                        bot_state.loss_memory.append({
                                            'indicators': sig['indicators'],
                                            'type': sig['type'],
                                            'time': sig['time_str']
                                        })
                                        bot_state.add_log(f"ML: Recorded loss pattern for {ticker}")
                                
                                bot_state.add_log(f"Trade Finished: {outcome} ({profit:+.2f}) | Session: {bot_state.session_profit:+.2f}")
                                
                                # --- Risk Management Checks ---
                                if bot_state.session_profit >= bot_state.profit_goal:
                                    bot_state.add_log(f"🎉 Profit Goal Reached ({bot_state.session_profit:.2f})! Stopping Bot.")
                                    bot_state.is_running = False
                                    bot_state.data_feed.disconnect()
                                    break

                                if bot_state.session_profit <= -bot_state.stop_loss:
                                    bot_state.add_log(f"🛑 Stop Loss Hit ({bot_state.session_profit:.2f})! Stopping Bot.")
                                    bot_state.is_running = False
                                    bot_state.data_feed.disconnect()
                                    break
                                    
                                if bot_state.consecutive_losses >= 2:
                                    bot_state.add_log("⚠️ 2 Consecutive Losses! Analyzing patterns...")
                                    bot_state.add_log("ML: Adjusting strategy parameters temporarily.")

                        if not bot_state.is_running: break

                        # Analyze Strategy
                        signal = bot_state.strategy.analyze_1m(df, symbol=ticker)
                        
                        if signal:
                            # --- ML Guard ---
                            should_skip = False
                            if bot_state.consecutive_losses >= 1:
                                 for bad_trade in bot_state.loss_memory[-5:]:
                                     if (signal['type'] == bad_trade['type'] and 
                                         abs(signal['indicators']['rsi'] - bad_trade['indicators']['rsi']) < 2.0):
                                         should_skip = True
                                         bot_state.add_log(f"ML: Skipped signal - Similar to recent loss (RSI {signal['indicators']['rsi']:.1f})")
                                         break
                            
                            if should_skip: continue

                            # Deduplicate
                            existing = [s for s in bot_state.signals if s['asset'] == ticker and s['time'] == signal['time']]
                            
                            if not existing:
                                signal['time_str'] = str(signal['time'])
                                signal['status'] = 'PENDING'
                                
                                bot_state.signals.append(signal)
                                bot_state.add_log(f"SIGNAL: {signal['type']} {ticker}")
                                bot_state.sound_queue.append("notification")
                                
                                # Auto Trade Execution
                                if bot_state.auto_trade_enabled:
                                    if not bot_state.data_feed.is_connected:
                                        bot_state.add_log(f"Skipped Auto-Trade {ticker}: Not Connected")
                                        bot_state.signals[-1]['status'] = 'SKIPPED'
                                    else:
                                        bot_state.add_log(f"Executing Auto-Trade: {ticker} {signal['type']}")
                                        
                                        max_retries = 3
                                        success = False
                                        details = None
                                        msg = ""
                                        
                                        for attempt in range(max_retries):
                                            success, details, msg = bot_state.data_feed.execute_trade(
                                                symbol=ticker,
                                                action=signal['type'],
                                                amount=bot_state.trade_amount,
                                                duration=bot_state.expiry_minutes,
                                                trade_mode="AUTO"
                                            )
                                            
                                            if success:
                                                break
                                            
                                            bot_state.add_log(f"Execution Retry {attempt+1}/{max_retries} Failed: {msg}")
                                            time.sleep(1)
                                        
                                        sig_idx = -1
                                        if bot_state.signals[-1]['asset'] == ticker:
                                            if success:
                                                bot_state.signals[sig_idx]['status'] = 'EXECUTED'
                                                bot_state.signals[sig_idx]['execution_msg'] = msg
                                                if details:
                                                    bot_state.signals[sig_idx]['trade_id'] = details['id']
                                                    bot_state.signals[sig_idx]['trade_type'] = details['type']
                                                bot_state.signals[sig_idx]['execution_time'] = datetime.now()
                                                bot_state.sound_queue.append("money")
                                                bot_state.add_log(f"Trade Success: {msg}")
                                                send_push_notification(bot_state, "Trade Executed 🚀", f"{ticker} {msg}")
                                            else:
                                                bot_state.signals[sig_idx]['status'] = 'FAILED'
                                                bot_state.signals[sig_idx]['execution_msg'] = msg
                                                bot_state.add_log(f"Trade Failed: {msg}")

                    bot_state.last_update = datetime.now().isoformat()
                    
                except Exception as e:
                    print(f"Loop Error ({bot_state.session_id}): {e}")
                    bot_state.add_log(f"Loop Error: {str(e)}")
        
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

class PushToken(BaseModel):
    token: str

# --- Rate Caching ---
rate_cache = {'USD': 1.0, 'NGN': 1650.0, 'EUR': 0.92, 'GBP': 0.77}
last_rate_update = 0

def get_rates():
    global rate_cache, last_rate_update
    if time.time() - last_rate_update < 3600 and len(rate_cache) > 1:
        return rate_cache
        
    print("Fetching Exchange Rates...")
    try:
        df = yf.download("NGN=X", period="1d", progress=False)
        if not df.empty:
            val = df['Close'].iloc[-1]
            if hasattr(val, 'item'): val = val.item()
            rate_cache['NGN'] = float(val)
            
        df = yf.download("EURUSD=X", period="1d", progress=False)
        if not df.empty:
            val = df['Close'].iloc[-1]
            if hasattr(val, 'item'): val = val.item()
            rate_cache['EUR'] = 1.0 / float(val)

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
    return {"status": "IQ Bot API Running", "version": "2.0 Multi-User"}

@app.post("/connect")
def connect_iq(req: ConnectRequest):
    # Create new session
    token = session_manager.create_session()
    bot_state = session_manager.get_session(token)
    
    success, message = bot_state.data_feed.connect_iq(req.email, req.password, req.account_type)
    if success:
        bot_state.add_log(f"Connected to IQ Option ({req.account_type})")
        # Update Account Currency
        bot_state.account_currency = bot_state.data_feed.get_account_currency() or "USD"
        bot_state.add_log(f"Account Currency: {bot_state.account_currency}")
    else:
        bot_state.add_log(f"Connection Failed: {message}")
        # Optionally remove session if failed? No, let user retry or see logs.
    
    return {"success": success, "message": message, "token": token}

@app.post("/disconnect")
def disconnect_iq(bot_state: BotState = Depends(get_current_bot)):
    bot_state.data_feed.disconnect()
    bot_state.add_log("Disconnected from IQ Option")
    # Clean up session
    session_manager.remove_session(bot_state.session_id)
    return {"status": "disconnected"}

@app.get("/signals")
def get_signals(bot_state: BotState = Depends(get_current_bot)):
    return bot_state.signals

@app.get("/rates")
def get_exchange_rates():
    return get_rates()

@app.get("/status")
def get_status(bot_state: BotState = Depends(get_current_bot)):
    # Safely get balance
    balance = 0
    if bot_state.data_feed.is_connected and bot_state.data_feed.iq_api:
        try:
            balance = bot_state.data_feed.iq_api.get_balance()
        except:
            pass

    return {
        "is_running": bot_state.is_running,
        "is_connected": bot_state.data_feed.is_connected,
        "auto_trade": bot_state.auto_trade_enabled,
        "balance": balance,
        "last_update": bot_state.last_update,
        "logs": bot_state.logs[-10:],
        "config": {
            "expiry": bot_state.expiry_minutes,
            "stop_loss": bot_state.stop_loss,
            "profit_goal": bot_state.profit_goal,
            "pairs": bot_state.active_pairs,
            "trade_amount": bot_state.trade_amount
        }
    }

@app.post("/start")
def start_bot(bot_state: BotState = Depends(get_current_bot)):
    bot_state.is_running = True
    bot_state.add_log("Bot Started")
    return {"status": "started"}

@app.post("/stop")
def stop_bot(bot_state: BotState = Depends(get_current_bot)):
    bot_state.is_running = False
    bot_state.add_log("Bot Stopped")
    return {"status": "stopped"}

@app.post("/config")
def update_config(req: ConfigRequest, bot_state: BotState = Depends(get_current_bot)):
    bot_state.auto_trade_enabled = req.auto_trade
    bot_state.expiry_minutes = req.expiry_minutes
    bot_state.stop_loss = req.stop_loss
    bot_state.profit_goal = req.profit_goal
    bot_state.active_pairs = req.active_pairs
    
    if bot_state.strategy:
        bot_state.strategy.expiry_minutes = req.expiry_minutes
        bot_state.strategy.stop_loss_limit = req.stop_loss

    # Currency Conversion Logic
    try:
        rates = get_rates()
        input_currency = req.currency
        account_currency = bot_state.account_currency
        
        # 1. Convert Input -> USD
        rate_input = rates.get(input_currency, 1.0)
        amount_usd = req.trade_amount / rate_input
        
        # 2. Convert USD -> Account Currency
        rate_account = rates.get(account_currency, 1.0)
        final_amount = amount_usd * rate_account
        
        bot_state.trade_amount = round(final_amount, 2)
        
        bot_state.add_log(f"Config: {req.trade_amount}{input_currency} -> {bot_state.trade_amount}{account_currency}")
    except Exception as e:
        print(f"Conversion Error: {e}")
        bot_state.trade_amount = req.trade_amount
        
    return {"status": "updated", "converted_amount": bot_state.trade_amount}

@app.post("/register_push")
def register_push(data: PushToken, bot_state: BotState = Depends(get_current_bot)):
    bot_state.push_tokens.add(data.token)
    print(f"Registered Push Token for session {bot_state.session_id}: {data.token}")
    return {"status": "registered"}

@app.get("/chart_data")
def get_chart_data(symbol: str = "EURUSD-OTC", bot_state: BotState = Depends(get_current_bot)):
    """
    Returns last 50 candles for charting.
    """
    try:
        df = bot_state.data_feed.fetch_data(symbol=symbol, period="1d", interval=config.ENTRY_TIMEFRAME)
        if df is None or df.empty:
            return {"error": "No data"}
        
        if 'ema_fast' not in df.columns:
            df = indicators.calculate_indicators(df)
            
        df_slice = df.tail(50)
        
        data = []
        for index, row in df_slice.iterrows():
            data.append({
                "timestamp": index.timestamp() * 1000,
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close']
            })
            
        return data
    except Exception as e:
        print(f"Chart Data Error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
