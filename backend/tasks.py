from celery_app import celery

@celery.task(name="test_task")
def test_task():
    return "Celery is working!"
