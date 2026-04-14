from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Payment
from apps.reservations.models import Reservation


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer pour afficher un paiement"""

    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    method_display = serializers.CharField(
        source='get_method_display',
        read_only=True
    )
    user_email = serializers.CharField(
        source='user.email',
        read_only=True
    )
    reservation_info = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'user_email', 'reservation_info',
            'amount', 'currency', 'status', 'status_display',
            'method', 'method_display', 'transaction_id',
            'paid_at', 'created_at'
        ]
        read_only_fields = [
            'id', 'transaction_id', 'paid_at', 'created_at'
        ]

    @extend_schema_field(serializers.DictField())
    def get_reservation_info(self, obj):
        return {
            'id': obj.reservation.id,
            'space': obj.reservation.space.name,
            'start': obj.reservation.start_datetime,
            'end': obj.reservation.end_datetime,
        }


class PaymentCreateSerializer(serializers.Serializer):
    """Serializer pour créer un paiement"""

    reservation_id = serializers.IntegerField()
    method = serializers.ChoiceField(
        choices=[
            ('card',          'Carte bancaire'),
            ('mobile_money',  'Mobile Money (Flooz / T-Money)'),
            ('cash',          'Espèces'),
            ('bank_transfer', 'Virement bancaire'),
        ]
    )

    def validate_reservation_id(self, value):
        try:
            reservation = Reservation.objects.get(id=value)
        except Reservation.DoesNotExist:
            raise serializers.ValidationError('Réservation introuvable.')

        if reservation.status == 'cancelled':
            raise serializers.ValidationError(
                'Impossible de payer une réservation annulée.'
            )

        if Payment.objects.filter(
            reservation=reservation,
            status='completed'
        ).exists():
            raise serializers.ValidationError(
                'Cette réservation a déjà été payée.'
            )

        return value


class PaymentConfirmSerializer(serializers.Serializer):
    """Serializer pour confirmer un paiement — admin"""

    status = serializers.ChoiceField(
        choices=[
            ('completed', 'Complété'),
            ('failed',    'Échoué'),
            ('refunded',  'Remboursé'),
        ]
    )