from rest_framework import serializers
from django.utils import timezone
from .models import Reservation
from apps.spaces.serializers import SpaceSerializer
from apps.accounts.serializers import UserProfileSerializer


class ReservationSerializer(serializers.ModelSerializer):
    """Serializer pour afficher une réservation"""

    space_detail = SpaceSerializer(source='space', read_only=True)
    user_detail = UserProfileSerializer(source='user', read_only=True)
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    billing_type_display = serializers.CharField(
        source='get_billing_type_display',
        read_only=True
    )
    duration_hours = serializers.SerializerMethodField()
    can_pay = serializers.SerializerMethodField()
    confirmed_by = UserProfileSerializer(read_only=True)

    class Meta:
        model = Reservation
        fields = [
            'id', 'user_detail', 'space_detail',
            'start_datetime', 'end_datetime',
            'status', 'status_display',
            'total_price', 'billing_type', 'billing_type_display',
            'duration_hours', 'is_recurring', 'recurrence_rule',
            'notes', 'can_pay', 'confirmed_at', 'confirmed_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_price', 'status', 'confirmed_at', 'confirmed_by',
            'created_at', 'updated_at'
        ]

    def get_duration_hours(self, obj) -> float:
        return obj.duration_hours

    def get_can_pay(self, obj) -> bool:
        return obj.status in ['confirmed', 'payment_pending']


class ReservationCreateSerializer(serializers.Serializer):
    """Serializer pour créer une réservation"""

    space_id = serializers.IntegerField()
    start_datetime = serializers.DateTimeField()
    end_datetime = serializers.DateTimeField()
    billing_type = serializers.ChoiceField(
        choices=[('hourly', 'Par heure'), ('daily', 'Par jour')],
        default='hourly'
    )
    is_recurring = serializers.BooleanField(default=False)
    recurrence_rule = serializers.ChoiceField(
        choices=[
            ('none',    'Aucune'),
            ('daily',   'Quotidienne'),
            ('weekly',  'Hebdomadaire'),
            ('monthly', 'Mensuelle')
        ],
        default='none'
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default=''
    )

    def validate(self, attrs):
        if attrs['start_datetime'] >= attrs['end_datetime']:
            raise serializers.ValidationError(
                'La date de fin doit être après la date de début.'
            )
        if attrs['start_datetime'] < timezone.now():
            raise serializers.ValidationError(
                'La date de début ne peut pas être dans le passé.'
            )
        return attrs


VALID_TRANSITIONS = {
    Reservation.Status.PENDING:         {Reservation.Status.CONFIRMED, Reservation.Status.REJECTED, Reservation.Status.CANCELLED},
    Reservation.Status.CONFIRMED:       {Reservation.Status.PAYMENT_PENDING, Reservation.Status.CANCELLED},
    Reservation.Status.PAYMENT_PENDING: {Reservation.Status.PAID, Reservation.Status.CANCELLED},
    Reservation.Status.PAID:            {Reservation.Status.COMPLETED},
    Reservation.Status.CANCELLED:       set(),
    Reservation.Status.COMPLETED:       set(),
    Reservation.Status.REJECTED:        set(),
}


class ReservationUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour modifier le statut d'une réservation — admin"""

    class Meta:
        model = Reservation
        fields = ['status', 'notes']

    def validate_status(self, new_status):
        if self.instance:
            current = self.instance.status
            allowed = VALID_TRANSITIONS.get(current, set())
            if new_status not in allowed:
                readable = sorted(allowed) if allowed else ['aucune']
                raise serializers.ValidationError(
                    f"Transition '{current}' → '{new_status}' non autorisée. "
                    f"Transitions valides depuis '{current}' : {readable}."
                )
        return new_status