from celery import Celery

celery = Celery(
    "boi",
    broker="redis://:BoiRedis@2026!@172.31.8.33:6379/0",
    backend="redis://:BoiRedis@2026!@172.31.8.33:6379/0",
)

celery.conf.update(
    task_routes={
        "bot_engine.trading_bot.*": {"queue": "default"}
    },
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
)
