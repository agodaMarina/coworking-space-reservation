from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from django.utils import timezone
from rest_framework import generics, status, serializers
from .models import Payment, Invoice
from .serializers import (
    PaymentSerializer,
    PaymentCreateSerializer,
    PaymentConfirmSerializer,
)
from apps.reservations.models import Reservation
from apps.accounts.permissions import IsAdminUser
from services.payment_gateway import simulate_payment, process_refund


class PaymentCreateView(APIView):
    """
    Créer un paiement pour une réservation.
    Les paiements par carte et mobile_money sont validés immédiatement.
    Les paiements par virement ou espèces restent 'en attente' de validation admin.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=PaymentCreateSerializer,
        responses={201: PaymentSerializer},
        summary="Créer un paiement",
        tags=['Paiements']
    )
    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        
        try:
            reservation = Reservation.objects.get(id=data['reservation_id'])
        except Reservation.DoesNotExist:
            return Response(
                {'error': 'Réservation introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Vérification des permissions
        if reservation.user != request.user and not request.user.is_admin:
            return Response(
                {'error': 'Vous ne pouvez payer que vos propres réservations.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Simulation du processus de paiement via la passerelle
        result = simulate_payment(
            amount=reservation.total_price,
            method=data['method'],
            user=request.user
        )

        # --- LOGIQUE DE STATUT ---
        # Définir quelles méthodes sont instantanées
        INSTANT_METHODS = ['card', 'mobile_money']
        
        if result['success']:
            if data['method'] in INSTANT_METHODS:
                initial_status = 'completed'
            else:
                # Pour 'cash' et 'bank_transfer', le paiement est créé mais reste à valider
                initial_status = 'pending'
        else:
            initial_status = 'failed'

        # Création de l'enregistrement de paiement
        payment = Payment.objects.create(
            reservation=reservation,
            user=request.user,
            amount=reservation.total_price,
            currency='XOF',
            status=initial_status,
            method=data['method'],
            transaction_id=result['transaction_id'],
            # On n'enregistre la date de paiement que si c'est déjà complété
            paid_at=timezone.now() if initial_status == 'completed' else None,
        )

        # --- MISE À JOUR DE LA RÉSERVATION ---
        # La réservation n'est confirmée QUE si le paiement est 'completed'
        if initial_status == 'completed':
            reservation.status = 'confirmed'
            reservation.save()
        # Optionnel : si c'est en attente, on peut laisser la réservation en 'pending'
        # ou créer un statut spécifique 'awaiting_payment_validation'

        return Response({
            'message': result['message'] if initial_status != 'pending' else "Paiement enregistré. En attente de validation par l'administrateur.",
            'payment': PaymentSerializer(payment).data,
        }, status=status.HTTP_201_CREATED)


class PaymentListView(generics.ListAPIView):
    """Liste des paiements"""
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'method']

    @extend_schema(
        summary="Liste des paiements",
        tags=['Paiements']
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Payment.objects.none()
        user = self.request.user
        if user.is_admin:
            return Payment.objects.all()
        return Payment.objects.filter(user=user)


class PaymentDetailView(generics.RetrieveAPIView):
    """Détail d'un paiement"""
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    @extend_schema(
        summary="Détail d'un paiement",
        tags=['Paiements']
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Payment.objects.none()
        user = self.request.user
        if user.is_admin:
            return Payment.objects.all()
        return Payment.objects.filter(user=user)


class PaymentConfirmView(APIView):
    """Confirmer ou rejeter un paiement — admin seulement"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=PaymentConfirmSerializer,
        responses={200: PaymentSerializer},
        summary="Confirmer un paiement (admin)",
        tags=['Paiements']
    )
    def patch(self, request, pk):
        try:
            payment = Payment.objects.get(id=pk)
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Paiement introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = PaymentConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            # --- MODIFICATION ICI ---
            # On extrait le nom du champ qui pose problème
            champ_manquant = list(serializer.errors.keys())[0]
            return Response(
                {'error': f"Le champ '{champ_manquant}' est obligatoire pour confirmer cette action."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = PaymentConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        new_status = serializer.validated_data['status']
        payment.status = new_status

        if new_status == 'completed':
            payment.paid_at = timezone.now()
            payment.reservation.status = 'confirmed'
            payment.reservation.save()

        elif new_status == 'refunded':
            result = process_refund(
                payment.transaction_id,
                payment.amount
            )
            payment.reservation.status = 'cancelled'
            payment.reservation.save()

        elif new_status == 'failed':
            payment.reservation.status = 'pending'
            payment.reservation.save()

        payment.save()

        return Response({
            'message': f'Paiement mis à jour : {payment.get_status_display()}',
            'payment': PaymentSerializer(payment).data
        }, status=status.HTTP_200_OK)


class PaymentStatsView(APIView):
    """Statistiques des paiements — admin seulement"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Statistiques des paiements",
        tags=['Paiements'],
        responses={200: serializers.DictField()}
    )
    def get(self, request):
        from django.db.models import Sum, Count

        stats = {
            'total_payments': Payment.objects.count(),
            'completed_payments': Payment.objects.filter(status='completed').count(),
            'pending_payments': Payment.objects.filter(status='pending').count(),
            'failed_payments': Payment.objects.filter(status='failed').count(),
            'total_revenue': Payment.objects.filter(
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'revenue_by_method': list(
                Payment.objects.filter(status='completed')
                .values('method')
                .annotate(total=Sum('amount'), count=Count('id'))
            ),
        }

        return Response(stats, status=status.HTTP_200_OK)


class PaymentRefundView(APIView):
    """Remboursement partiel ou total — admin seulement"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Rembourser un paiement (admin)",
        tags=['Paiements'],
        responses={200: PaymentSerializer}
    )
    def post(self, request, pk):
        try:
            payment = Payment.objects.get(id=pk)
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Paiement introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if payment.status == 'refunded':
            return Response(
                {'error': 'Ce paiement a déjà été entièrement remboursé.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if payment.status != 'completed':
            return Response(
                {'error': 'Seuls les paiements complétés peuvent être remboursés.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        amount = request.data.get('amount')
        reason = request.data.get('reason', '')

        if not amount:
            return Response(
                {'error': 'Le montant du remboursement est requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        amount = float(amount)

        if amount > float(payment.amount):
            return Response(
                {'error': 'Le montant de remboursement dépasse le montant payé.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from services.payment_gateway import process_refund
        result = process_refund(payment.transaction_id, amount)

        if float(amount) == float(payment.amount):
            payment.status = 'refunded'
        else:
            payment.status = 'partial_refund'

        payment.save()
        payment.reservation.status = 'cancelled'
        payment.reservation.save()

        return Response({
            'message': result['message'],
            'payment_id': payment.id,
            'refunded_amount': str(amount),
            'total_refunded': str(amount),
            'payment_status': payment.status,
        }, status=status.HTTP_200_OK)


class InvoiceDownloadView(APIView):
    """Télécharger la facture d'un paiement"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Télécharger une facture",
        tags=['Paiements'],
        responses={200: None}
    )
    def get(self, request, pk):
        try:
            payment = Payment.objects.get(id=pk)
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Paiement introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if payment.user != request.user and not request.user.is_admin:
            return Response(
                {'error': 'Accès non autorisé.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if payment.status != 'completed':
            return Response(
                {'error': 'La facture n\'est disponible que pour les paiements complétés.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Génération de la facture en texte (PDF réel nécessite WeasyPrint)
        from django.http import HttpResponse
        response = HttpResponse(content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="facture-{payment.id}.txt"'
        )

        content = f"""
========================================
        FACTURE DE PAIEMENT
========================================
Référence     : FACT-{payment.id:06d}
Date          : {payment.paid_at.strftime('%d/%m/%Y %H:%M') if payment.paid_at else 'N/A'}

UTILISATEUR
-----------
Nom           : {payment.user.full_name}
Email         : {payment.user.email}

RÉSERVATION
-----------
Espace        : {payment.reservation.space.name}
Début         : {payment.reservation.start_datetime.strftime('%d/%m/%Y %H:%M')}
Fin           : {payment.reservation.end_datetime.strftime('%d/%m/%Y %H:%M')}

PAIEMENT
--------
Méthode       : {payment.get_method_display()}
Montant       : {payment.amount} {payment.currency}
Transaction   : {payment.transaction_id}
Statut        : {payment.get_status_display()}

========================================
     Merci pour votre confiance !
   Coworking Space — Lomé, Togo
========================================
        """

        response.write(content)
        return response