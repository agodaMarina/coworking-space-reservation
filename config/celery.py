import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'config.settings.development'
)

app = Celery('coworking')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'mark-completed-reservations': {
        'task': 'apps.notifications.tasks.mark_completed_reservations',
        'schedule': crontab(minute=0),  # toutes les heures pile
    },
    'send-reservation-reminders': {
        'task': 'apps.notifications.tasks.send_reservation_reminder',
        'schedule': crontab(hour=8, minute=0),  # chaque jour à 8h
    },
}

#celery -A config worker -l info
