from celery import shared_task
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings


@shared_task(bind=True, max_retries=3)
def send_reservation_received_email(self, user_email, user_name, reservation_data):
    """Envoie un email de réception de demande de réservation (statut : en attente)"""
    try:
        subject = f"Demande de réservation #{reservation_data['id']} reçue"
        text_content = f"""
        Bonjour {user_name},
        Votre demande de réservation #{reservation_data['id']} a bien été reçue et est en attente de confirmation.
        Espace : {reservation_data['space_name']}
        Début : {reservation_data['start_datetime']}
        Fin : {reservation_data['end_datetime']}
        Montant estimé : {reservation_data['total_price']} FCFA
        Vous recevrez un email dès que votre réservation sera confirmée ou rejetée.
        """
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            fail_silently=False,
        )

        return f"Email de réception envoyé à {user_email}"

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_reservation_rejected_email(self, user_email, user_name, reservation_data):
    """Envoie un email de rejet de réservation"""
    try:
        subject = f"Réservation #{reservation_data['id']} non confirmée"
        text_content = f"""
        Bonjour {user_name},
        Nous sommes désolés, votre réservation #{reservation_data['id']} n'a pas pu être confirmée.
        Espace : {reservation_data['space_name']}
        Début : {reservation_data['start_datetime']}
        Fin : {reservation_data['end_datetime']}
        Vous pouvez effectuer une nouvelle demande pour un autre créneau.
        """
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            fail_silently=False,
        )

        return f"Email de rejet envoyé à {user_email}"

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_reservation_confirmed_email(self, user_email, user_name, reservation_data):
    """Envoie un email de confirmation de réservation"""
    try:
        subject = f"Confirmation de votre réservation #{reservation_data['id']}"
        html_content = render_to_string(
            'emails/reservation_confirmed.html',
            {
                'user_name': user_name,
                'space_name': reservation_data['space_name'],
                'start_datetime': reservation_data['start_datetime'],
                'end_datetime': reservation_data['end_datetime'],
                'duration_hours': reservation_data['duration_hours'],
                'total_price': reservation_data['total_price'],
                'reservation_id': reservation_data['id'],
            }
        )
        text_content = f"""
        Bonjour {user_name},
        Votre réservation #{reservation_data['id']} a été confirmée.
        Espace : {reservation_data['space_name']}
        Début : {reservation_data['start_datetime']}
        Fin : {reservation_data['end_datetime']}
        Montant : {reservation_data['total_price']} FCFA
        """
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        return f"Email envoyé à {user_email}"

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_reservation_cancelled_email(self, user_email, user_name, reservation_data):
    """Envoie un email d'annulation de réservation"""
    try:
        subject = f"Annulation de votre réservation #{reservation_data['id']}"
        html_content = render_to_string(
            'emails/reservation_cancelled.html',
            {
                'user_name': user_name,
                'space_name': reservation_data['space_name'],
                'start_datetime': reservation_data['start_datetime'],
                'end_datetime': reservation_data['end_datetime'],
                'reservation_id': reservation_data['id'],
            }
        )
        text_content = f"""
        Bonjour {user_name},
        Votre réservation #{reservation_data['id']} a été annulée.
        Espace : {reservation_data['space_name']}
        """
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        return f"Email d'annulation envoyé à {user_email}"

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_payment_completed_email(self, user_email, user_name, payment_data):
    """Envoie un email de confirmation de paiement"""
    try:
        subject = f"Paiement confirmé — {payment_data['amount']} FCFA"
        text_content = f"""
        Bonjour {user_name},
        Votre paiement de {payment_data['amount']} FCFA a été confirmé.
        Méthode : {payment_data['method']}
        Transaction : {payment_data['transaction_id']}
        Réservation : #{payment_data['reservation_id']}
        """
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            fail_silently=False,
        )
        return f"Email de paiement envoyé à {user_email}"

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task
def mark_completed_reservations():
    """
    Tâche périodique — passe en COMPLETED les réservations CONFIRMED dont la date de fin est passée.
    Planifiée toutes les heures via Celery Beat.
    """
    from apps.reservations.models import Reservation

    updated = Reservation.objects.filter(
        status=Reservation.Status.CONFIRMED,
        end_datetime__lt=timezone.now(),
    ).update(status=Reservation.Status.COMPLETED)

    return f"{updated} réservation(s) marquée(s) comme terminées."


@shared_task
def send_reservation_reminder():
    """
    Tâche périodique — envoie des rappels 24h avant chaque réservation.
    À planifier avec Celery Beat.
    """
    from apps.reservations.models import Reservation
    from datetime import timedelta

    tomorrow = timezone.now() + timedelta(hours=48)
    upcoming = Reservation.objects.filter(
        status='confirmed',
        start_datetime__lte=tomorrow,
        start_datetime__gte=timezone.now(),
    )

    for reservation in upcoming:
        send_mail(
            subject=f"Rappel — Votre réservation commence bientôt",
            message=f"""
            Bonjour {reservation.user.full_name},
            Rappel : votre réservation de l'espace "{reservation.space.name}"
            commence le {reservation.start_datetime.strftime('%d/%m/%Y à %H:%M')}.
            """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reservation.user.email],
            fail_silently=True,
        )

    return f"{upcoming.count()} rappels envoyés."


def _save_notification(user_email, reservation_id, notification_type, channel, message):
    """Sauvegarde la notification en base de données"""
    try:
        from apps.accounts.models import User
        from apps.reservations.models import Reservation
        from apps.notifications.models import Notification

        user = User.objects.get(email=user_email)
        reservation = Reservation.objects.get(id=reservation_id)

        Notification.objects.create(
            user=user,
            reservation=reservation,
            notification_type=notification_type,
            channel=channel,
            status='sent',
            message=message,
            sent_at=timezone.now(),
        )
    except Exception:
        pass
