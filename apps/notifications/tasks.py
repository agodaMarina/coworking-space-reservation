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
    """Envoie un email HTML + notification in-app de confirmation de paiement à l'utilisateur."""
    try:
        from apps.payments.models import Payment
        from apps.notifications.models import Notification

        # ── Notification in-app ───────────────────────────────────────────────
        try:
            payment = Payment.objects.select_related('user', 'reservation').get(
                transaction_id=payment_data['transaction_id']
            )
            Notification.objects.create(
                user=payment.user,
                reservation=payment.reservation,
                notification_type=Notification.Type.PAYMENT_COMPLETED,
                title='Paiement confirmé !',
                message=(
                    f"Votre paiement de {payment.amount} FCFA pour la réservation "
                    f"#{payment.reservation.id} ({payment.reservation.space.name}) a été confirmé."
                ),
                channel='email',
                status='sent',
                sent_at=timezone.now(),
            )
        except Exception:
            pass

        # ── Email HTML ────────────────────────────────────────────────────────
        subject = f"[CoworkSpace] Paiement confirmé — {payment_data['amount']} FCFA"
        html_content = render_to_string(
            'emails/payment_completed.html',
            {
                'user_name': user_name,
                'amount': payment_data['amount'],
                'method': payment_data['method'],
                'transaction_id': payment_data['transaction_id'],
                'reservation_id': payment_data['reservation_id'],
            }
        )
        text_content = (
            f"Bonjour {user_name},\n\n"
            f"Votre paiement de {payment_data['amount']} FCFA a été confirmé.\n"
            f"Méthode : {payment_data['method']}\n"
            f"Transaction : {payment_data['transaction_id']}\n"
            f"Réservation : #{payment_data['reservation_id']}\n"
        )
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email],
        )
        email.attach_alternative(html_content, 'text/html')
        email.send()

        return f"Email de paiement envoyé à {user_email}"

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_reservation_request_to_admin(self, reservation_id):
    """Notifie tous les admins d'une nouvelle demande de réservation."""
    try:
        from apps.reservations.models import Reservation
        from apps.notifications.models import Notification
        from apps.accounts.models import User

        reservation = Reservation.objects.select_related('user', 'space').get(id=reservation_id)
        admin_users = User.objects.filter(role='admin')

        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                reservation=reservation,
                notification_type=Notification.Type.RESERVATION_REQUEST,
                title='Nouvelle demande de réservation',
                message=(
                    f"Demande de {reservation.user.full_name} pour "
                    f"{reservation.space.name} du "
                    f"{reservation.start_datetime.strftime('%d/%m/%Y %H:%M')} au "
                    f"{reservation.end_datetime.strftime('%d/%m/%Y %H:%M')}. "
                    f"Montant : {reservation.total_price} FCFA."
                ),
                channel='email',
                status='sent',
                sent_at=timezone.now(),
            )
            try:
                html_content = render_to_string(
                    'emails/admin_reservation_request.html',
                    {'reservation': reservation, 'admin': admin}
                )
                email = EmailMultiAlternatives(
                    subject=f"[CoworkSpace] Nouvelle demande de réservation #{reservation.id}",
                    body=f"Nouvelle demande de {reservation.user.full_name} pour {reservation.space.name}.",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[admin.email],
                )
                email.attach_alternative(html_content, 'text/html')
                email.send()
            except Exception:
                pass

        return f"Admins notifiés pour réservation #{reservation_id}"
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_reservation_confirmed_to_user(self, reservation_id):
    """Notifie l'utilisateur que sa réservation a été confirmée par l'admin."""
    try:
        from apps.reservations.models import Reservation
        from apps.notifications.models import Notification

        reservation = Reservation.objects.select_related('user', 'space').get(id=reservation_id)

        Notification.objects.create(
            user=reservation.user,
            reservation=reservation,
            notification_type=Notification.Type.RESERVATION_CONFIRMED,
            title='Réservation confirmée !',
            message=(
                f"Votre réservation #{reservation.id} pour {reservation.space.name} "
                f"a été confirmée. Vous pouvez procéder au paiement de {reservation.total_price} FCFA."
            ),
            channel='email',
            status='sent',
            sent_at=timezone.now(),
        )

        html_content = render_to_string(
            'emails/user_reservation_confirmed.html',
            {'reservation': reservation}
        )
        email = EmailMultiAlternatives(
            subject=f"[CoworkSpace] Votre réservation #{reservation.id} est confirmée",
            body=(
                f"Bonjour {reservation.user.full_name},\n\n"
                f"Votre réservation pour {reservation.space.name} a été confirmée.\n"
                f"Montant à régler : {reservation.total_price} FCFA."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[reservation.user.email],
        )
        email.attach_alternative(html_content, 'text/html')
        email.send()

        return f"Utilisateur notifié : réservation #{reservation_id} confirmée"
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_reservation_rejected_to_user(self, reservation_id):
    """Notifie l'utilisateur que sa réservation a été rejetée par l'admin."""
    try:
        from apps.reservations.models import Reservation
        from apps.notifications.models import Notification

        reservation = Reservation.objects.select_related('user', 'space').get(id=reservation_id)

        Notification.objects.create(
            user=reservation.user,
            reservation=reservation,
            notification_type=Notification.Type.RESERVATION_REJECTED,
            title='Réservation non confirmée',
            message=(
                f"Votre réservation #{reservation.id} pour {reservation.space.name} "
                f"n'a pas pu être confirmée. Vous pouvez soumettre une nouvelle demande."
            ),
            channel='email',
            status='sent',
            sent_at=timezone.now(),
        )

        html_content = render_to_string(
            'emails/user_reservation_rejected.html',
            {'reservation': reservation}
        )
        email = EmailMultiAlternatives(
            subject=f"[CoworkSpace] Réservation #{reservation.id} — Suite de votre demande",
            body=(
                f"Bonjour {reservation.user.full_name},\n\n"
                f"Nous sommes désolés, votre réservation #{reservation.id} "
                f"pour {reservation.space.name} n'a pas pu être confirmée."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[reservation.user.email],
        )
        email.attach_alternative(html_content, 'text/html')
        email.send()

        return f"Utilisateur notifié : réservation #{reservation_id} rejetée"
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_payment_confirmed_to_admin(self, payment_id):
    """Notifie les admins qu'un paiement a été reçu."""
    try:
        from apps.payments.models import Payment
        from apps.notifications.models import Notification
        from apps.accounts.models import User

        payment = Payment.objects.select_related('user', 'reservation__space').get(id=payment_id)
        admin_users = User.objects.filter(role='admin')

        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                notification_type=Notification.Type.PAYMENT_RECEIVED,
                title='Paiement reçu',
                message=(
                    f"Paiement de {payment.amount} XOF reçu de {payment.user.full_name} "
                    f"pour {payment.reservation.space.name} "
                    f"(réservation #{payment.reservation.id})."
                ),
                channel='email',
                status='sent',
                sent_at=timezone.now(),
            )
            try:
                html_content = render_to_string(
                    'emails/admin_payment_received.html',
                    {'payment': payment, 'admin': admin}
                )
                email = EmailMultiAlternatives(
                    subject=f"[CoworkSpace] Paiement reçu — {payment.amount} XOF",
                    body=f"Paiement de {payment.amount} XOF de {payment.user.full_name}.",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[admin.email],
                )
                email.attach_alternative(html_content, 'text/html')
                email.send()
            except Exception:
                pass

        return f"Admins notifiés du paiement #{payment_id}"
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
