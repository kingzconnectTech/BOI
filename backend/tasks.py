import os
import time
import json
import redis
from celery_app import celery_app, REDIS_URL
from bot_engine.session_manager import BotSessionManager

# Redis Connection (For simple checks if needed, though SessionManager handles its own)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

@celery_app.task(bind=True, name="run_trading_bot")
def run_trading_bot(self, email, password, mode="PRACTICE", config=None, push_token=None):
    """
    Defines the Trading Task:
    1. Takes user ID (email) and credentials.
    2. Starts a trading bot loop in this separate Celery worker.
    3. Updates Redis with bot status via BotSessionManager.
    """
    task_id = self.request.id
    print(f"[Task-{task_id}] Initializing Bot Session for {email}...")
    
    # Delegate to BotSessionManager which handles the loop and Redis updates
    manager = BotSessionManager(REDIS_URL, task_id)
    return manager.run_session(email, password, mode, config, push_token)

