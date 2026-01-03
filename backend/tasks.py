from celery_app import celery

@celery.task(bind=True, name="test_task")
def test_task(self):
    return "Celery is working!"
