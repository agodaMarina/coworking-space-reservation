from django.db import models
from django.conf import settings
from apps.reservations.models import Reservation


class Payment(models.Model):
    """Paiement associé à une réservation"""

    class Status(models.TextChoices):
        PENDING   = 'pending',   'En attente'
        COMPLETED = 'completed', 'Complété'
        FAILED    = 'failed',    'Échoué'
        REFUNDED  = 'refunded',  'Remboursé'
        CANCELLED = 'cancelled', 'Annulé'

    class Method(models.TextChoices):
        CARD         = 'card',          'Carte bancaire'
        MOBILE_MONEY = 'mobile_money',  'Mobile Money'
        CASH         = 'cash',          'Espèces'
        BANK         = 'bank_transfer', 'Virement bancaire'

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name='réservation'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name='utilisateur'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='montant (FCFA)'
    )
    currency = models.CharField(
        max_length=10,
        default='XOF',
        verbose_name='devise'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='statut'
    )
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        verbose_name='méthode de paiement'
    )
    transaction_id = models.CharField(
        max_length=255,
        blank=True,
        unique=True,
        null=True,
        verbose_name='identifiant de transaction'
    )
    paid_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='payé le'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='créé le'
    )

    class Meta:
        verbose_name = 'Paiement'
        verbose_name_plural = 'Paiements'
        ordering = ['-created_at']

    def __str__(self):
        return f"Paiement #{self.id} — {self.amount} {self.currency} — {self.get_status_display()}"


class Invoice(models.Model):
    """Facture générée après un paiement"""

    payment = models.OneToOneField(
        Payment,
        on_delete=models.CASCADE,
        related_name='invoice',
        verbose_name='paiement'
    )
    reference = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='référence'
    )
    pdf_file = models.FileField(
        upload_to='invoices/',
        blank=True,
        null=True,
        verbose_name='fichier PDF'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='créée le'
    )

    class Meta:
        verbose_name = 'Facture'
        verbose_name_plural = 'Factures'
        ordering = ['-created_at']

    def __str__(self):
        return f"Facture {self.reference}"