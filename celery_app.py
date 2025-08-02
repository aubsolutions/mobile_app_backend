# celery_app.py
import os
from celery import Celery
from datetime import timedelta

# Подтягиваем URL из переменных окружения
REDIS_URL = os.environ['REDIS_URL']

celery = Celery(
    'enote_tasks',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Автодискавер тасков в модуле tasks
celery.autodiscover_tasks(['tasks'])

# Планировщик: раз в 24 часа
celery.conf.beat_schedule = {
    'check_subscriptions_daily': {
        'task': 'tasks.check_subscriptions',
        'schedule': timedelta(hours=24),
    },
}
celery.conf.timezone = 'UTC'
