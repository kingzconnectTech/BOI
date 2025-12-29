from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
from bot_service import bot_instance

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    email: str
    password: str
    mode: str = "PRACTICE"
    amount: float = 1.0
    duration: int = 1
    stop_loss: float = 0.0
    take_profit: float = 0.0

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Backend is running"}

@app.post("/start")
def start_bot(login_data: LoginRequest):
    bot_instance.clear_logs() # Clear previous logs
    
    # Set config
    bot_instance.set_config(login_data.amount, login_data.duration, login_data.stop_loss, login_data.take_profit)
    
    success, message = bot_instance.connect(login_data.email, login_data.password, login_data.mode)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Start auto trading loop
    bot_instance.start_trading()
    
    status = bot_instance.get_status()
    return {"status": "started", "message": message, "data": status}

@app.post("/stop")
def stop_bot():
    success, message = bot_instance.stop()
    return {"status": "stopped", "message": message}

@app.get("/status")
def get_status():
    return bot_instance.get_status()

@app.get("/logs")
def get_logs():
    return {"logs": bot_instance.get_logs()}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
