import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import threading
import time

app = FastAPI(title="IQ Bot API (Fresh Start)")

# --- Minimal State ---
class BotState:
    def __init__(self):
        self.is_running = False
        self.signals = []
        self.last_update = None
        self.logs = []
        self.balance = 0.0
        self.session_profit = 0.0

    def add_log(self, message: str):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {message}")
        if len(self.logs) > 100:
            self.logs.pop(0)

bot = BotState()

def bot_loop():
    while True:
        if bot.is_running:
            # Placeholder for future logic
            bot.last_update = time.time()
        time.sleep(5)

t = threading.Thread(target=bot_loop, daemon=True)
t.start()

# --- Models ---
class TradeRequest(BaseModel):
    action: str
    amount: float
    asset: str
    duration: int

# --- Endpoints ---
@app.get("/")
def root():
    return {"status": "Fresh backend running", "version": "0.1"}

@app.get("/status")
def status():
    return {
        "is_running": bot.is_running,
        "is_connected": False,
        "auto_trade": False,
        "balance": bot.balance,
        "session_profit": bot.session_profit,
        "last_update": bot.last_update,
        "logs": bot.logs[-10:],
        "config": {
            "expiry": 2,
            "stop_loss": 2,
            "profit_goal": 5.0,
            "pairs": [],
            "trade_amount": 1.0
        }
    }

@app.get("/signals")
def get_signals():
    return bot.signals

@app.post("/start")
def start():
    bot.is_running = True
    bot.add_log("Bot Started")
    return {"status": "started"}

@app.post("/stop")
def stop():
    bot.is_running = False
    bot.add_log("Bot Stopped")
    return {"status": "stopped"}

@app.post("/trade")
def trade(req: TradeRequest):
    # Minimal placeholder
    bot.add_log(f"Manual Trade Request: {req.action} {req.asset} {req.amount}")
    return {"success": True, "message": "Accepted (no engine yet)"}

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
