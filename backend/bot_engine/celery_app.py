from celery import Celery

celery = Celery(
    "boi",
    broker="redis://:BoiRedis@2026!@172.31.8.33:6379/0",
    backend="redis://:BoiRedis@2026!@172.31.8.33:6379/0",
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
