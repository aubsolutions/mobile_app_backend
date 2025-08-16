# tasks.py
from celery_app import celery
from database import SessionLocal
from models import Subscription
from datetime import datetime, timedelta
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@celery.task
def check_subscriptions():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        cutoff = now + timedelta(days=3)

        expiring = (
            db.query(Subscription)
              .filter(Subscription.end_date <= cutoff,
                      Subscription.end_date >= now)
              .all()
        )

        logger.info("Проверка подписок: найдено %d истекающих в окне %s → %s",
                    len(expiring), now, cutoff)

        for sub in expiring:
            logger.info("Напоминание: user_id=%s истекает %s",
                        sub.user_id, sub.end_date.date())

    finally:
        db.close()