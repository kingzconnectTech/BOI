# backend/bot_engine/redis_client.py
import redis
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "BoiRedis@2026!")

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    redis_client.ping()
    print(f"[Redis] Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except redis.AuthenticationError:
    print("[Redis] Authentication failed. Check REDIS_PASSWORD")
    redis_client = None
except Exception as e:
    print(f"[Redis] Connection failed: {e}")
    redis_client = None

def get_redis():
    return redis_client
