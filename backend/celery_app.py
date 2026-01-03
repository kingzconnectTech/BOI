from celery import Celery
from redis_client import redis_client

celery = Celery(
    "bot_engine",
    broker="redis://:BoiRedis@2026!@127.0.0.1:6379/0",
    backend="redis://:BoiRedis@2026!@127.0.0.1:6379/0"
)

celery.conf.task_routes = {
    "tasks.*": {"queue": "default"}
}
