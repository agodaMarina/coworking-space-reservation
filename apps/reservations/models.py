from django.db import models
from django.conf import settings
from apps.spaces.models import Space


class Reservation(models.Model):
    """Réservation d'un espace de coworking"""

    class Status(models.TextChoices):
        PENDING   = 'pending',   'En attente'
        CONFIRMED = 'confirmed', 'Confirmée'
        CANCELLED = 'cancelled', 'Annulée'
        COMPLETED = 'completed', 'Terminée'
        REJECTED  = 'rejected',  'Rejetée'

    class BillingType(models.TextChoices):
        HOURLY = 'hourly', 'Par heure'
        DAILY  = 'daily',  'Par jour'

    class RecurrenceRule(models.TextChoices):
        NONE    = 'none',    'Aucune'
        DAILY   = 'daily',   'Quotidienne'
        WEEKLY  = 'weekly',  'Hebdomadaire'
        MONTHLY = 'monthly', 'Mensuelle'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reservations',
        verbose_name='utilisateur'
    )
    space = models.ForeignKey(
        Space,
        on_delete=models.CASCADE,
        related_name='reservations',
        verbose_name='espace'
    )
    start_datetime = models.DateTimeField(
        verbose_name='date et heure de début'
    )
    end_datetime = models.DateTimeField(
        verbose_name='date et heure de fin'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='statut'
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='prix total (FCFA)'
    )
    billing_type = models.CharField(
        max_length=10,
        choices=BillingType.choices,
        default=BillingType.HOURLY,
        verbose_name='type de facturation'
    )
    is_recurring = models.BooleanField(
        default=False,
        verbose_name='récurrente'
    )
    recurrence_rule = models.CharField(
        max_length=10,
        choices=RecurrenceRule.choices,
        default=RecurrenceRule.NONE,
        verbose_name='règle de récurrence'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='notes'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='créée le'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='modifiée le'
    )

    class Meta:
        verbose_name = 'Réservation'
        verbose_name_plural = 'Réservations'
        ordering = ['-created_at']
        # Contrainte : un espace ne peut pas avoir 2 réservations confirmées
        # qui se chevauchent — géré dans le service, pas ici

    def __str__(self):
        return f"Réservation #{self.id} — {self.user} — {self.space}"

    @property
    def duration_hours(self):
        """Durée de la réservation en heures"""
        delta = self.end_datetime - self.start_datetime
        return round(delta.total_seconds() / 3600, 2)