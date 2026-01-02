import os
from celery import Celery

# Celery Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "bot_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['tasks']
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker configuration
    worker_concurrency=4,  # Allow multiple bots
    worker_prefetch_multiplier=1
)
