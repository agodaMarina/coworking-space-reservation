from django.db import models
from django.conf import settings
from apps.reservations.models import Reservation


class Notification(models.Model):
    """Notification envoyée à un utilisateur"""

    class Type(models.TextChoices):
        RESERVATION_RECEIVED   = 'reservation_received',   'Demande reçue'
        RESERVATION_REQUEST    = 'reservation_request',    'Nouvelle demande (admin)'
        RESERVATION_CONFIRMED  = 'reservation_confirmed',  'Réservation confirmée'
        RESERVATION_REJECTED   = 'reservation_rejected',   'Réservation rejetée'
        RESERVATION_CANCELLED  = 'reservation_cancelled',  'Réservation annulée'
        RESERVATION_REMINDER   = 'reservation_reminder',   'Rappel de réservation'
        PAYMENT_COMPLETED      = 'payment_completed',      'Paiement effectué'
        PAYMENT_RECEIVED       = 'payment_received',       'Paiement reçu (admin)'
        PAYMENT_FAILED         = 'payment_failed',         'Paiement échoué'
        PAYMENT_REFUNDED       = 'payment_refunded',       'Paiement remboursé'

    class Channel(models.TextChoices):
        EMAIL = 'email', 'Email'
        SMS   = 'sms',   'SMS'

    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        SENT    = 'sent',    'Envoyée'
        FAILED  = 'failed',  'Échouée'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='utilisateur'
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='notifications',
        blank=True,
        null=True,
        verbose_name='réservation'
    )
    notification_type = models.CharField(
        max_length=30,
        choices=Type.choices,
        verbose_name='type de notification'
    )
    channel = models.CharField(
        max_length=10,
        choices=Channel.choices,
        verbose_name='canal d\'envoi'
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='statut'
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='titre'
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name='lue'
    )
    message = models.TextField(
        verbose_name='message'
    )
    sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='envoyée le'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='créée le'
    )

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification {self.get_notification_type_display()} — {self.user} — {self.get_status_display()}"

    @classmethod
    def create(cls, user, notification_type, message, reservation=None, channel='email'):
        """Crée et sauvegarde immédiatement une notification en base."""
        from django.utils import timezone
        return cls.objects.create(
            user=user,
            reservation=reservation,
            notification_type=notification_type,
            channel=channel,
            status=cls.Status.SENT,
            message=message,
            sent_at=timezone.now(),
        )