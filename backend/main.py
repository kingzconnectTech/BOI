from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import threading
import time
import requests
from bot_service import bot_manager
import firebase_admin
from firebase_admin import credentials

# Initialize Firebase Admin
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        print("Firebase Admin initialized successfully")
    except Exception as e:
        print(f"Warning: Firebase Admin initialization failed: {e}")

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keep-Alive Mechanism for Render Free Tier
def keep_alive():
    url = "https://boi-lgdy.onrender.com"
    while True:
        try:
            time.sleep(600) # Ping every 10 minutes
            print(f"Pinging {url} to keep alive...")
            requests.get(url)
        except Exception as e:
            print(f"Keep-alive ping failed: {e}")

@app.on_event("startup")
async def startup_event():
    # Start the keep-alive thread
    threading.Thread(target=keep_alive, daemon=True).start()

class ConnectRequest(BaseModel):
    email: str
    password: str
    mode: str = "PRACTICE"

class LoginRequest(BaseModel):
    email: str
    password: str
    mode: str = "PRACTICE"
    amount: float = 1.0
    duration: int = 1
    stop_loss: float = 0.0
    take_profit: float = 0.0
    max_consecutive_losses: int = 0
    max_trades: int = 0
    auto_trading: bool = True
    push_token: str = None # Added for Push Notifications

class StopRequest(BaseModel):
    email: str

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Backend is running"}

@app.post("/connect")
def connect_bot(data: ConnectRequest):
    bot = bot_manager.get_bot(data.email)
    success, message = bot.connect(data.email, data.password, data.mode)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {"status": "connected", "message": message, "data": bot.get_status()}

@app.post("/start")
def start_bot(login_data: LoginRequest):
    bot = bot_manager.get_bot(login_data.email)
    bot.clear_logs() # Clear previous logs
    
    # Set config
    bot.set_config(
        login_data.amount, 
        login_data.duration, 
        login_data.stop_loss, 
        login_data.take_profit,
        login_data.max_consecutive_losses,
        login_data.max_trades,
        login_data.auto_trading
    )
    
    # Set Push Token
    if login_data.push_token:
        bot.set_push_token(login_data.push_token)
    
    success, message = bot.connect(login_data.email, login_data.password, login_data.mode)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Start auto trading loop
    bot.start_trading()
    
    status = bot.get_status()
    return {"status": "started", "message": message, "data": status}

@app.post("/stop")
def stop_bot(request: StopRequest):
    bot = bot_manager.get_bot(request.email)
    success, message = bot.stop()
    return {"status": "stopped", "message": message}

@app.get("/status")
def get_status(email: str):
    bot = bot_manager.get_bot(email)
    return bot.get_status()

@app.get("/logs")
def get_logs(email: str):
    bot = bot_manager.get_bot(email)
    return {"logs": bot.get_logs()}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
