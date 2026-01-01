from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import threading
import time
import requests
import json
import firebase_admin
from firebase_admin import credentials
from tasks import run_trading_bot, celery_app, redis_client

# Initialize Firebase Admin
if not firebase_admin._apps:
    try:
        # Construct absolute path to serviceAccountKey.json
        base_dir = os.path.dirname(os.path.abspath(__file__))
        service_account_path = os.path.join(base_dir, "serviceAccountKey.json")
        
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        print("Firebase Admin initialized successfully")
    except Exception as e:
        print(f"Warning: Firebase Admin initialization failed: {e}")

# Global Bot Readiness Lock
# bot_ready = False

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keep-Alive Mechanism (AWS/Render)
def keep_alive():
    url = "http://brickchain.online"
    while True:
        try:
            time.sleep(300) # Ping every 5 minutes
            print(f"Pinging {url} to keep alive...")
            requests.get(url, timeout=10)
        except Exception as e:
            print(f"Keep-alive ping failed: {e}")

@app.on_event("startup")
async def startup_event():
    # Start the keep-alive thread
    # threading.Thread(target=keep_alive, daemon=True).start()
    print("API is ready. Worker tasks managed by Celery.")

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
    strategy: str = "Momentum" # Added for Strategy Selection

class StopRequest(BaseModel):
    email: str

class DisconnectRequest(BaseModel):
    email: str

class UpdateRequest(BaseModel):
    email: str
    amount: float = None
    duration: int = None
    stop_loss: float = None
    take_profit: float = None
    max_consecutive_losses: int = None
    max_trades: int = None
    auto_trading: bool = None
    strategy: str = None

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Backend is running"}

@app.post("/connect")
def connect_bot(data: ConnectRequest):
    """
    Checks if a bot session is active.
    Note: In this stateless architecture, /connect is mostly a 'pre-flight' check.
    The actual connection happens when /start queues the task.
    """
    key_active = f"bot:{data.email}:active"
    if redis_client.exists(key_active):
        return {"status": "connected", "message": "Bot already active", "data": get_status(data.email)}

    # Return success so frontend proceeds to 'start' page
    return {"status": "connected", "message": "Ready to start", "data": {"connected": True}}

@app.post("/start")
def start_bot(login_data: LoginRequest):
    key_active = f"bot:{login_data.email}:active"
    if redis_client.exists(key_active):
        # Already running, maybe update config?
        # For now, just return status
        return {"status": "started", "message": "Bot already running", "data": get_status(login_data.email)}

    # Trigger Celery Task
    task = run_trading_bot.delay(
        email=login_data.email, 
        password=login_data.password, 
        mode=login_data.mode,
        config=login_data.dict(),
        push_token=login_data.push_token
    )
    
    return {"status": "started", "message": f"Bot task queued (ID: {task.id})", "data": {"running": True}}


@app.post("/update")
def update_bot(data: UpdateRequest):
    key_config = f"bot:{data.email}:config"
    key_active = f"bot:{data.email}:active"
    
    if not redis_client.exists(key_active):
        return {"status": "error", "message": "Bot not active"}
    
    # Filter out None values
    config_update = {k: v for k, v in data.dict().items() if v is not None and k != 'email'}
    
    if config_update:
        # Push update to Redis
        redis_client.set(key_config, json.dumps(config_update))
        return {"status": "updated", "message": "Configuration update queued"}
    else:
        return {"status": "no_change", "message": "No configuration provided"}

@app.post("/stop")
def stop_bot(request: StopRequest):
    key_stop = f"bot:{request.email}:stop"
    key_active = f"bot:{request.email}:active"
    
    if not redis_client.exists(key_active):
        return {"status": "stopped", "message": "Bot not active"}
        
    redis_client.set(key_stop, "1")
    return {"status": "stopped", "message": "Stop signal sent"}

@app.post("/disconnect")
def disconnect_bot(request: DisconnectRequest):
    # Same as stop
    key_stop = f"bot:{request.email}:stop"
    redis_client.set(key_stop, "1")
    return {"status": "disconnected", "message": "Disconnect signal sent"}

@app.get("/status")
def get_status(email: str):
    key_status = f"bot:{email}:status"
    data = redis_client.get(key_status)
    if not data:
        return {
            "connected": False, 
            "running": False, 
            "balance": 0, 
            "currency": "", 
            "stats": {"profit": 0, "wins": 0, "losses": 0, "win_rate": 0}
        }
    return json.loads(data)

@app.get("/logs")
def get_logs(email: str):
    key_logs = f"bot:{email}:logs"
    logs = redis_client.lrange(key_logs, 0, -1)
    return {"logs": logs}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
