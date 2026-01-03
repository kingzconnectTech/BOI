from celery import Celery
from tasks import redis_client

celery = Celery(
    "bot_engine",
    broker="redis://:BoiRedis@2026!@172.31.8.33:6379/0",
    backend="redis://:BoiRedis@2026!@172.31.8.33:6379/0"
)

celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]
celery.conf.timezone = "Africa/Lagos"
celery.conf.enable_utc = True
