from rest_framework import generics, status, filters, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from .models import Reservation
from apps.notifications.models import Notification
from apps.payments.models import Payment
from services.payment_gateway import process_local_payment
from .serializers import (
    ReservationSerializer,
    ReservationCreateSerializer,
    ReservationUpdateSerializer,
)
from apps.spaces.models import Space
from apps.accounts.permissions import IsAdminUser, IsOwnerOrAdmin
from services.reservation_logic import create_reservation, cancel_reservation
from apps.notifications.tasks import (
    send_reservation_received_email,
    send_reservation_confirmed_email,
    send_reservation_cancelled_email,
    send_reservation_rejected_email,
)


class ReservationCreateView(APIView):
    """Créer une nouvelle réservation"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ReservationCreateSerializer,
        responses={201: ReservationSerializer},
        summary="Créer une réservation",
        tags=['Réservations']
    )
    def post(self, request):
        serializer = ReservationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            space = Space.objects.get(id=data['space_id'])
        except Space.DoesNotExist:
            return Response(
                {'error': 'Espace introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        reservation, message = create_reservation(
            user=request.user,
            space=space,
            start_datetime=data['start_datetime'],
            end_datetime=data['end_datetime'],
            billing_type=data['billing_type'],
            notes=data.get('notes', ''),
            is_recurring=data.get('is_recurring', False),
            recurrence_rule=data.get('recurrence_rule', 'none'),
        )

        if not reservation:
            return Response(
                {'error': message},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Notification en base (synchrone) + email async
        Notification.create(
            user=request.user,
            notification_type=Notification.Type.RESERVATION_RECEIVED,
            message=f"Votre demande de réservation #{reservation.id} ({reservation.space.name}) a bien été reçue et est en attente de confirmation.",
            reservation=reservation,
        )
        try:
            send_reservation_received_email.delay(
                user_email=request.user.email,
                user_name=request.user.full_name,
                reservation_data={
                    'id': reservation.id,
                    'space_name': reservation.space.name,
                    'start_datetime': str(reservation.start_datetime),
                    'end_datetime': str(reservation.end_datetime),
                    'duration_hours': reservation.duration_hours,
                    'total_price': str(reservation.total_price),
                }
            )
        except Exception:
            pass

        return Response({
            'message': message,
            'reservation': ReservationSerializer(reservation).data
        }, status=status.HTTP_201_CREATED)


class ReservationListView(generics.ListAPIView):
    """Liste des réservations de l'utilisateur connecté"""
    permission_classes = [IsAuthenticated]
    serializer_class = ReservationSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'billing_type', 'is_recurring']
    ordering_fields = ['created_at', 'start_datetime']
    ordering = ['-created_at']

    @extend_schema(
        summary="Mes réservations",
        tags=['Réservations']
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Reservation.objects.none()
        user = self.request.user
        if user.is_admin:
            return Reservation.objects.all()
        return Reservation.objects.filter(user=user)


class ReservationDetailView(generics.RetrieveAPIView):
    """Détail d'une réservation"""
    permission_classes = [IsAuthenticated]
    serializer_class = ReservationSerializer

    @extend_schema(
        summary="Détail d'une réservation",
        tags=['Réservations']
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Reservation.objects.none()
        user = self.request.user
        if user.is_admin:
            return Reservation.objects.all()
        return Reservation.objects.filter(user=user)


class ReservationCancelView(APIView):
    """Annuler une réservation"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: None},
        summary="Annuler une réservation",
        tags=['Réservations']
    )
    def post(self, request, pk):
        try:
            reservation = Reservation.objects.get(id=pk)
        except Reservation.DoesNotExist:
            return Response(
                {'error': 'Réservation introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        success, message = cancel_reservation(reservation, request.user)

        if not success:
            return Response(
                {'error': message},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Envoyer email d'annulation en arrière-plan
        try:
            send_reservation_cancelled_email.delay(
                user_email=reservation.user.email,
                user_name=reservation.user.full_name,
                reservation_data={
                    'id': reservation.id,
                    'space_name': reservation.space.name,
                    'start_datetime': str(reservation.start_datetime),
                    'end_datetime': str(reservation.end_datetime),
                }
            )
        except Exception:
            pass  # Ne pas bloquer si Celery n'est pas lancé

        return Response(
            {'message': message},
            status=status.HTTP_200_OK
        )


class ReservationUpdateView(generics.UpdateAPIView):
    """Modifier le statut d'une réservation — admin seulement"""
    permission_classes = [IsAdminUser]
    serializer_class = ReservationUpdateSerializer
    queryset = Reservation.objects.all()

    @extend_schema(
        summary="Modifier partiellement une réservation (admin)",
        tags=['Réservations']
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        summary="Modifier une réservation (admin)",
        tags=['Réservations']
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.data:
            return Response(
                {'error': 'Veuillez renseigner les champs à modifier.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        previous_status = instance.status
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        new_status = instance.status

        # Notification en base + email async si le statut a changé
        if new_status != previous_status:
            reservation_data = {
                'id': instance.id,
                'space_name': instance.space.name,
                'start_datetime': str(instance.start_datetime),
                'end_datetime': str(instance.end_datetime),
                'duration_hours': instance.duration_hours,
                'total_price': str(instance.total_price),
            }

            # Création automatique d'un paiement cash en attente à la confirmation
            payment_created = None
            if new_status == Reservation.Status.CONFIRMED:
                already_paid = Payment.objects.filter(
                    reservation=instance,
                    status__in=[Payment.Status.PENDING, Payment.Status.COMPLETED],
                ).exists()

                if not already_paid:
                    result = process_local_payment(
                        amount_xof=instance.total_price,
                        method=Payment.Method.CASH,
                        user=instance.user,
                    )
                    payment_created = Payment.objects.create(
                        reservation=instance,
                        user=instance.user,
                        amount=instance.total_price,
                        currency='XOF',
                        status=Payment.Status.PENDING,
                        method=Payment.Method.CASH,
                        transaction_id=result['transaction_id'],
                    )

            notif_map = {
                Reservation.Status.CONFIRMED: (
                    Notification.Type.RESERVATION_CONFIRMED,
                    f"Votre réservation #{instance.id} ({instance.space.name}) a été confirmée. "
                    f"Montant à régler : {instance.total_price} FCFA.",
                    send_reservation_confirmed_email,
                ),
                Reservation.Status.CANCELLED: (
                    Notification.Type.RESERVATION_CANCELLED,
                    f"Votre réservation #{instance.id} ({instance.space.name}) a été annulée.",
                    send_reservation_cancelled_email,
                ),
                Reservation.Status.REJECTED: (
                    Notification.Type.RESERVATION_REJECTED,
                    f"Votre réservation #{instance.id} ({instance.space.name}) n'a pas pu être confirmée.",
                    send_reservation_rejected_email,
                ),
            }

            if new_status in notif_map:
                notif_type, message, email_task = notif_map[new_status]

                Notification.create(
                    user=instance.user,
                    notification_type=notif_type,
                    message=message,
                    reservation=instance,
                )

                try:
                    email_task.delay(
                        user_email=instance.user.email,
                        user_name=instance.user.full_name,
                        reservation_data=reservation_data,
                    )
                except Exception:
                    pass

        response_data = {
            'message': 'Réservation mise à jour avec succès.',
            'reservation': ReservationSerializer(instance).data,
        }
        if payment_created:
            from apps.payments.serializers import PaymentSerializer
            response_data['payment_created'] = PaymentSerializer(payment_created).data
            response_data['payment_note'] = (
                f"Paiement en attente créé automatiquement ({payment_created.amount} XOF). "
                f"À valider via PATCH /api/payments/{payment_created.id}/confirm/ une fois encaissé."
            )

        return Response(response_data)

class SpaceAvailabilityView(APIView):
    """Vérifier la disponibilité d'un espace"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Vérifier disponibilité d'un espace avant réservation",
        tags=['Réservations'],
        responses={200: serializers.DictField()}
    )
    def post(self, request, pk):
        try:
            space = Space.objects.get(id=pk)
        except Space.DoesNotExist:
            return Response(
                {'error': 'Espace introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        start_datetime = request.data.get('start_datetime')
        end_datetime = request.data.get('end_datetime')

        if not start_datetime or not end_datetime:
            return Response(
                {'error': 'Les dates de début et fin sont requises.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from services.availability import check_availability, calculate_price
        from django.utils.dateparse import parse_datetime

        start = parse_datetime(start_datetime)
        end = parse_datetime(end_datetime)

        if not start or not end:
            return Response(
                {'error': 'Format de date invalide.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not space.is_available:
            return Response({
                'space_id': pk,
                'space_name': space.name,
                'is_available': False,
                'message': "Cet espace n'est pas disponible à la réservation.",
            }, status=status.HTTP_200_OK)

        is_available, message = check_availability(space, start, end)

        response_data = {
            'space_id': pk,
            'space_name': space.name,
            'is_available': is_available,
            'message': message,
        }

        if is_available:
            billing_type = request.data.get('billing_type', 'hourly')
            price = calculate_price(space, start, end, billing_type)
            response_data['estimated_price'] = price
            response_data['billing_type'] = billing_type

        return Response(response_data, status=status.HTTP_200_OK)