from celery_app import celery
import time

@celery_app.task(bind=True, name="test_task")
def test_task(self, name):
    print(f"Task started for {name}")
    time.sleep(5)
    print(f"Task finished for {name}")
    return f"Hello {name}"
