# celery_app.py
import os
from celery import Celery
from datetime import timedelta

REDIS_URL = os.environ.get("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set")

celery = Celery(
    "enote_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],          # <-- ЯВНО грузим модуль tasks.py
)

# Если брокер поднимается позже — не падаем
celery.conf.broker_connection_retry_on_startup = True
celery.conf.timezone = "UTC"

celery.conf.beat_schedule = {
    "check_subscriptions_daily": {
        "task": "tasks.check_subscriptions",
        "schedule": timedelta(hours=24),
    },
}

# На случай капризов пути — принудительно дернем импорт
try:
    import tasks  # noqa: F401
except Exception as e:
    print("!!! Failed to import tasks:", e)