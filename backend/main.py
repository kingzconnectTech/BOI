from fastapi import FastAPI
from bot_engine.redis_client import get_redis
from bot_engine.tasks import add

app = FastAPI()
redis_client = get_redis()

@app.post("/connect")
async def connect_bot(key_active: str):
    if not redis_client:
        return {"status": "error", "message": "Redis not connected"}
    
    if redis_client.exists(key_active):
        return {"status": "ok", "message": "Bot already connected"}
    
    redis_client.set(key_active, "active")
    # Test Celery task
    result = add.delay(10, 20)
    return {"status": "ok", "celery_task_id": result.id}
