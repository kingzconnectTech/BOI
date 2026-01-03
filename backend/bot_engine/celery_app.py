# backend/bot_engine/celery_app.py
from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "BoiRedis@2026!")

REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

celery = Celery(
    "bot_engine",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Optional: Auto-discover tasks
celery.autodiscover_tasks(['bot_engine'])
