from rest_framework import generics, status, filters, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from .models import Reservation
from apps.notifications.models import Notification
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
    send_reservation_request_to_admin,
    send_reservation_confirmed_to_user,
    send_reservation_rejected_to_user,
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

        # Notification en base (synchrone) + email async à l'utilisateur
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

        # Notifier les admins de la nouvelle demande
        try:
            send_reservation_request_to_admin.delay(reservation.id)
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

        if new_status != previous_status:
            # Enregistrer qui a confirmé et quand
            if new_status == Reservation.Status.CONFIRMED:
                from django.utils import timezone as tz
                instance.confirmed_at = tz.now()
                instance.confirmed_by = request.user
                instance.save(update_fields=['confirmed_at', 'confirmed_by'])
                try:
                    send_reservation_confirmed_to_user.delay(instance.id)
                except Exception:
                    pass

            elif new_status == Reservation.Status.REJECTED:
                try:
                    send_reservation_rejected_to_user.delay(instance.id)
                except Exception:
                    pass

            elif new_status == Reservation.Status.CANCELLED:
                Notification.create(
                    user=instance.user,
                    notification_type=Notification.Type.RESERVATION_CANCELLED,
                    message=f"Votre réservation #{instance.id} ({instance.space.name}) a été annulée.",
                    reservation=instance,
                )
                try:
                    send_reservation_cancelled_email.delay(
                        user_email=instance.user.email,
                        user_name=instance.user.full_name,
                        reservation_data={
                            'id': instance.id,
                            'space_name': instance.space.name,
                            'start_datetime': str(instance.start_datetime),
                            'end_datetime': str(instance.end_datetime),
                        },
                    )
                except Exception:
                    pass

        return Response({
            'message': 'Réservation mise à jour avec succès.',
            'reservation': ReservationSerializer(instance).data,
        })

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


class InitiatePaymentView(APIView):
    """
    Démarre le processus de paiement pour une réservation confirmée.
    Passe le statut de 'confirmed' à 'payment_pending'.
    Accessible uniquement par le propriétaire de la réservation.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: ReservationSerializer},
        summary="Initier le paiement d'une réservation confirmée",
        tags=['Réservations']
    )
    def post(self, request, pk):
        try:
            reservation = Reservation.objects.get(id=pk, user=request.user)
        except Reservation.DoesNotExist:
            return Response(
                {'error': 'Réservation introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if reservation.status != Reservation.Status.CONFIRMED:
            return Response(
                {
                    'error': (
                        "La réservation doit être confirmée par l'admin avant d'initier le paiement. "
                        f"Statut actuel : {reservation.get_status_display()}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        reservation.status = Reservation.Status.PAYMENT_PENDING
        reservation.save(update_fields=['status', 'updated_at'])

        return Response({
            'message': 'Vous pouvez maintenant procéder au paiement.',
            'reservation_id': reservation.id,
            'status': reservation.status,
            'reservation': ReservationSerializer(reservation).data,
        }, status=status.HTTP_200_OK)