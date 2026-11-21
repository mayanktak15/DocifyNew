"""Celery tasks for optional background processing."""
import os
from celery import Celery

celery_app = Celery('docify', broker=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'), backend=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
celery_app.conf.update(task_serializer='json', result_serializer='json', accept_content=['json'], task_ignore_result=True)


@celery_app.task(name='docify.refresh_faq')
def refresh_faq():
    """Refresh FAQ data in this worker; web processes load it on restart."""
    from chatbot.service import documents, semantic_index
    documents.cache_clear()
    semantic_index.cache_clear()
    if os.getenv("DOCIFY_SEMANTIC_SEARCH", "").lower() == "true" and semantic_index() is None:
        raise RuntimeError("Semantic index unavailable")
    return len(documents())


celery_app.conf.beat_schedule = {'email-updates': {'task': 'docify.deliver_updates', 'schedule': 60.0}}


@celery_app.task(name='docify.deliver_updates')
def deliver_updates():
    """Drain committed opt-in notifications. Delivery is at least once."""
    if not os.getenv('SMTP_HOST') or not os.getenv('SMTP_FROM'):
        return 0
    from email.message import EmailMessage
    import smtplib
    import ssl
    from app import Notification, User, create_app, db, now
    sent = 0
    with create_app().app_context():
        for _ in range(25):
            row = db.session.scalar(db.select(Notification).where(Notification.email_pending.is_(True))
                                    .order_by(Notification.id).limit(1).with_for_update(skip_locked=True))
            if row is None:
                break
            user = db.session.get(User, row.user_id)
            if user.email_updates:
                mail = EmailMessage()
                mail['From'] = os.environ['SMTP_FROM']
                mail['To'] = user.email
                mail['Subject'] = 'New dashboard update'
                mail.set_content('Sign in to your account to read your latest update.')
                with smtplib.SMTP_SSL(os.environ['SMTP_HOST'], int(os.getenv('SMTP_PORT', '465')),
                                      context=ssl.create_default_context(), timeout=5) as smtp:
                    if os.getenv('SMTP_USER'):
                        smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
                    smtp.send_message(mail)
                row.emailed_at = now()
                sent += 1
            row.email_pending = False
            db.session.commit()
    return sent
