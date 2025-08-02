# tasks.py
from celery_app import celery
from database import SessionLocal
from models import Subscription
from datetime import datetime, timedelta

@celery.task
def check_subscriptions():
    db = SessionLocal()
    now = datetime.utcnow()
    cutoff = now + timedelta(days=3)

    expiring = (
        db.query(Subscription)
          .filter(Subscription.end_date <= cutoff,
                  Subscription.end_date >= now)
          .all()
    )

    for sub in expiring:
        # Здесь будет реальный send_push/sub.notify(...)
        print(f"Напоминание: подписка user_id={sub.user_id} истекает {sub.end_date.date()}")

    db.close()
