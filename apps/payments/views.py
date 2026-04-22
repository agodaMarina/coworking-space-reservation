# apps/payments/views.py

import logging
from decimal import Decimal

import stripe
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings

from rest_framework import generics, status, serializers
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from .models import Payment, Invoice
from .serializers import (
    PaymentSerializer,
    PaymentCreateSerializer,
    PaymentConfirmSerializer,
)
from apps.reservations.models import Reservation
from apps.accounts.permissions import IsAdminUser
from apps.notifications.tasks import send_payment_completed_email

# ── Import du gateway Stripe ───
from services.payment_gateway import (
    create_payment_intent,
    retrieve_payment_intent,
    process_refund,
    process_local_payment,
    construct_webhook_event,
)

logger = logging.getLogger(__name__)

# Méthodes traitées via Stripe
STRIPE_METHODS = [Payment.Method.CARD]

# Méthodes locales (validation admin manuelle)
LOCAL_METHODS = [Payment.Method.CASH, Payment.Method.BANK, Payment.Method.MOBILE_MONEY]


# ════════════════════════════════════════════════════════════════════════════
# POST /api/payments/create/
# ════════════════════════════════════════════════════════════════════════════

class PaymentCreateView(APIView):
    """
    Créer un paiement pour une réservation.

    - method='card'         → crée un PaymentIntent Stripe, retourne client_secret
                              Le frontend Angular doit confirmer via Stripe.js,
                              puis appeler POST /payments/{id}/stripe-confirm/
    - method='mobile_money' → enregistre le paiement en 'pending' (validation admin)
    - method='cash'         → idem pending
    - method='bank_transfer'→ idem pending
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
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # ── Récupération de la réservation ────────────────────────────────────
        try:
            reservation = Reservation.objects.select_related('space', 'user').get(
                id=data['reservation_id']
            )
        except Reservation.DoesNotExist:
            return Response(
                {'error': 'Réservation introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # ── Vérification des permissions ──────────────────────────────────────
        if reservation.user != request.user and not request.user.is_admin:
            return Response(
                {'error': 'Vous ne pouvez payer que vos propres réservations.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if reservation.status == Reservation.Status.CANCELLED:
            return Response(
                {'error': 'Impossible de payer une réservation annulée.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Vérifier qu'un paiement complété n'existe pas déjà ───────────────
        existing = Payment.objects.filter(
            reservation=reservation,
            status=Payment.Status.COMPLETED,
        ).first()
        if existing:
            return Response(
                {'error': 'Cette réservation est déjà payée.', 'payment_id': existing.id},
                status=status.HTTP_400_BAD_REQUEST
            )

        method = data['method']
        amount = reservation.total_price  # Decimal, en XOF

        # ════════════════════════════════════════════════════════════════════
        # CAS 1 : Paiement par carte → Stripe PaymentIntent
        # ════════════════════════════════════════════════════════════════════
        if method == Payment.Method.CARD:
            result = create_payment_intent(
                amount_xof=amount,
                user=request.user,
                reservation=reservation,
            )

            if not result['success']:
                return Response(
                    {'error': result.get('error', 'Erreur lors de la création du paiement.')},
                    status=status.HTTP_400_BAD_REQUEST
                )

            payment = Payment.objects.create(
                reservation=reservation,
                user=request.user,
                amount=amount,
                currency='XOF',
                status=Payment.Status.PENDING,
                method=Payment.Method.CARD,
                # Stocke le pi_xxx Stripe → utilisé pour confirm et refund
                transaction_id=result['payment_intent_id'],
            )

            logger.info(
                "[Payment] Stripe #%s créé — PI: %s — %s XOF",
                payment.id, result['payment_intent_id'], amount,
            )

            return Response({
                'message': 'PaymentIntent créé. Confirmez le paiement via Stripe.js.',
                'payment': PaymentSerializer(payment).data,
                # ↓ Ces deux champs sont UNIQUEMENT pour le frontend Stripe.js
                'stripe': {
                    'client_secret': result['client_secret'],
                    'publishable_key': settings.STRIPE['PUBLISHABLE_KEY'],
                    'payment_intent_id': result['payment_intent_id'],
                    'amount_xof': str(amount),
                    'amount_eur_cents': result['amount_eur_cents'],
                    'note': '1 EUR = 655.957 XOF (parité fixe CFA)',
                }
            }, status=status.HTTP_201_CREATED)

        # ════════════════════════════════════════════════════════════════════
        # CAS 2 : Mobile money, espèces, virement → validation admin
        # ════════════════════════════════════════════════════════════════════
        result = process_local_payment(
            amount_xof=amount,
            method=method,
            user=request.user,
        )

        payment = Payment.objects.create(
            reservation=reservation,
            user=request.user,
            amount=amount,
            currency='XOF',
            status=Payment.Status.PENDING,   # Admin valide manuellement
            method=method,
            transaction_id=result['transaction_id'],
        )

        logger.info(
            "[Payment] Local #%s créé — %s — %s XOF — en attente validation",
            payment.id, method, amount,
        )

        return Response({
            'message': "Paiement enregistré. En attente de validation par l'administrateur.",
            'payment': PaymentSerializer(payment).data,
        }, status=status.HTTP_201_CREATED)


# ════════════════════════════════════════════════════════════════════════════
# POST /api/payments/{id}/stripe-confirm/
# Nouveau endpoint — confirmation serveur après que Stripe.js a réussi
# ════════════════════════════════════════════════════════════════════════════

class PaymentStripeConfirmView(APIView):
    """
    Appelé par Angular APRÈS que Stripe.js ait confirmé le paiement côté client.
    Effectue la vérification serveur auprès de l'API Stripe (source of truth).

    Ne jamais faire confiance au frontend seul : ce endpoint vérifie
    le statut réel du PaymentIntent avant de confirmer en base.

    Flux :
        Angular → stripe.confirmCardPayment(client_secret)
        Angular → POST /api/payments/{id}/stripe-confirm/
        Django  → stripe.PaymentIntent.retrieve(pi_xxx)
        Django  → met à jour Payment + Reservation si succeeded
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: PaymentSerializer},
        summary="Confirmer un paiement Stripe (utilisateur)",
        tags=['Paiements']
    )
    def post(self, request, pk):
        try:
            payment = Payment.objects.select_related('reservation', 'user').get(
                id=pk,
                user=request.user,
            )
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Paiement introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Cette vue ne gère que les paiements Stripe
        if payment.method != Payment.Method.CARD:
            return Response(
                {'error': 'Ce endpoint est réservé aux paiements par carte Stripe.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Déjà traité (idempotent)
        if payment.status == Payment.Status.COMPLETED:
            return Response({
                'message': 'Ce paiement est déjà confirmé.',
                'payment': PaymentSerializer(payment).data,
            })

        # ── Vérification serveur auprès de Stripe ────────────────────────────
        result = retrieve_payment_intent(payment.transaction_id)

        if not result['success']:
            return Response(
                {'error': result.get('error', 'Impossible de vérifier le paiement.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        if result['paid']:
            now = timezone.now()
            payment.status = Payment.Status.COMPLETED
            payment.paid_at = now
            payment.save(update_fields=['status', 'paid_at'])

            # Confirmer la réservation uniquement si elle est encore en attente
            reservation = payment.reservation
            if reservation.status == Reservation.Status.PENDING:
                reservation.status = Reservation.Status.CONFIRMED
                reservation.save(update_fields=['status', 'updated_at'])

            logger.info(
                "[Payment] Stripe #%s confirmé — PI: %s — réservation #%s → confirmed",
                payment.id, payment.transaction_id, reservation.id,
            )

            try:
                send_payment_completed_email.delay(
                    user_email=payment.user.email,
                    user_name=payment.user.full_name,
                    payment_data={
                        'amount': str(payment.amount),
                        'method': payment.get_method_display(),
                        'transaction_id': payment.transaction_id,
                        'reservation_id': reservation.id,
                    }
                )
            except Exception:
                pass

        return Response({
            'message': 'Paiement confirmé avec succès ✅' if result['paid'] else 'Paiement non finalisé côté Stripe.',
            'stripe_status': result['status'],
            'paid': result['paid'],
            'payment': PaymentSerializer(payment).data,
        })


# ════════════════════════════════════════════════════════════════════════════
# GET /api/payments/
# ════════════════════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════════════════════
# GET /api/payments/{id}/
# ════════════════════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════════════════════
# PATCH /api/payments/{id}/confirm/
# Admin uniquement — validation manuelle des paiements locaux
# ════════════════════════════════════════════════════════════════════════════

class PaymentConfirmView(APIView):
    """
    Confirmer ou rejeter un paiement — admin seulement.

    Destiné aux paiements locaux (cash, mobile_money, bank_transfer)
    qui nécessitent une validation manuelle.

    Pour les paiements par carte Stripe, utiliser POST /stripe-confirm/ à la place.
    """
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=PaymentConfirmSerializer,
        responses={200: PaymentSerializer},
        summary="Confirmer un paiement (admin)",
        tags=['Paiements']
    )
    def patch(self, request, pk):
        try:
            payment = Payment.objects.select_related('reservation').get(id=pk)
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Paiement introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Les paiements Stripe se confirment via /stripe-confirm/, pas ici
        if payment.method == Payment.Method.CARD:
            return Response(
                {
                    'error': 'Les paiements par carte Stripe ne peuvent pas être confirmés manuellement.',
                    'hint': f'Utilisez POST /api/payments/{pk}/stripe-confirm/ après la confirmation Stripe.js.',
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = PaymentConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            champ_manquant = list(serializer.errors.keys())[0]
            return Response(
                {'error': f"Le champ '{champ_manquant}' est obligatoire pour confirmer cette action."},
                status=status.HTTP_400_BAD_REQUEST
            )

        new_status = serializer.validated_data['status']
        reservation = payment.reservation

        # ── Paiement validé par l'admin ───────────────────────────────────────
        if new_status == Payment.Status.COMPLETED:
            payment.status = Payment.Status.COMPLETED
            payment.paid_at = timezone.now()
            payment.save(update_fields=['status', 'paid_at'])

            if reservation.status == Reservation.Status.PENDING:
                reservation.status = Reservation.Status.CONFIRMED
                reservation.save(update_fields=['status', 'updated_at'])

            logger.info(
                "[Payment] #%s confirmé manuellement par admin — réservation #%s confirmée",
                payment.id, reservation.id,
            )

            try:
                send_payment_completed_email.delay(
                    user_email=payment.user.email,
                    user_name=payment.user.full_name,
                    payment_data={
                        'amount': str(payment.amount),
                        'method': payment.get_method_display(),
                        'transaction_id': payment.transaction_id,
                        'reservation_id': reservation.id,
                    }
                )
            except Exception:
                pass

        # ── Paiement remboursé ────────────────────────────────────────────────
        elif new_status == Payment.Status.REFUNDED:
            # Pour les paiements locaux : simulation du remboursement
            refund_result = process_refund(
                transaction_id=payment.transaction_id,
                amount_xof=Decimal(str(payment.amount)),
            )
            payment.status = Payment.Status.REFUNDED
            payment.save(update_fields=['status'])

            reservation.status = Reservation.Status.CANCELLED
            reservation.save(update_fields=['status', 'updated_at'])

            logger.info(
                "[Payment] #%s remboursé — refund_id: %s",
                payment.id, refund_result.get('refund_id'),
            )

        # ── Paiement rejeté ───────────────────────────────────────────────────
        elif new_status == Payment.Status.FAILED:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=['status'])

            # La réservation reste en pending pour permettre un nouveau paiement
            if reservation.status == Reservation.Status.CONFIRMED:
                reservation.status = Reservation.Status.PENDING
                reservation.save(update_fields=['status', 'updated_at'])

            logger.info("[Payment] #%s rejeté par admin", payment.id)

        else:
            return Response(
                {'error': f"Statut '{new_status}' non autorisé via cette action."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({
            'message': f'Paiement mis à jour : {payment.get_status_display()}',
            'payment': PaymentSerializer(payment).data,
        }, status=status.HTTP_200_OK)


# ════════════════════════════════════════════════════════════════════════════
# GET /api/payments/stats/
# ════════════════════════════════════════════════════════════════════════════

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
            'completed_payments': Payment.objects.filter(status=Payment.Status.COMPLETED).count(),
            'pending_payments': Payment.objects.filter(status=Payment.Status.PENDING).count(),
            'failed_payments': Payment.objects.filter(status=Payment.Status.FAILED).count(),
            'refunded_payments': Payment.objects.filter(status=Payment.Status.REFUNDED).count(),
            'total_revenue': Payment.objects.filter(
                status=Payment.Status.COMPLETED
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'revenue_by_method': list(
                Payment.objects.filter(status=Payment.Status.COMPLETED)
                .values('method')
                .annotate(total=Sum('amount'), count=Count('id'))
            ),
        }

        return Response(stats, status=status.HTTP_200_OK)


# ════════════════════════════════════════════════════════════════════════════
# POST /api/payments/{id}/refund/
# ════════════════════════════════════════════════════════════════════════════

class PaymentRefundView(APIView):
    """
    Remboursement partiel ou total — admin seulement.

    - Paiements carte (pi_xxx) → remboursement Stripe réel via API
    - Paiements locaux (TXN-xxx) → remboursement simulé (hors Stripe)

    Corps optionnel :
    {
        "amount": "5000.00",    // Partiel (FCFA). Omis = remboursement total
        "reason": "..."         // Texte libre pour l'historique
    }
    """
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Rembourser un paiement (admin)",
        tags=['Paiements'],
        responses={200: PaymentSerializer}
    )
    def post(self, request, pk):
        try:
            payment = Payment.objects.select_related('reservation').get(id=pk)
        except Payment.DoesNotExist:
            return Response(
                {'error': 'Paiement introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if payment.status == Payment.Status.REFUNDED:
            return Response(
                {'error': 'Ce paiement a déjà été remboursé.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if payment.status != Payment.Status.COMPLETED:
            return Response(
                {
                    'error': (
                        f'Seuls les paiements complétés peuvent être remboursés. '
                        f'Statut actuel : {payment.get_status_display()}.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Validation du montant ─────────────────────────────────────────────
        amount_raw = request.data.get('amount')
        if amount_raw is not None:
            try:
                amount_xof = Decimal(str(amount_raw))
                if amount_xof <= 0:
                    raise ValueError
            except (ValueError, Exception):
                return Response({'error': 'Montant invalide.'}, status=status.HTTP_400_BAD_REQUEST)

            if amount_xof > payment.amount:
                return Response(
                    {'error': f'Montant trop élevé. Maximum remboursable : {payment.amount} XOF.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            amount_xof = None  # Remboursement total

        # ── Appel du gateway (Stripe ou local selon le transaction_id) ────────
        result = process_refund(
            transaction_id=payment.transaction_id,
            amount_xof=amount_xof,
        )

        if not result['success']:
            return Response(
                {'error': result.get('error', 'Échec du remboursement.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── CORRECTION : 'partial_refund' n'existe pas dans Payment.Status ────
        # On utilise toujours 'refunded' (Stripe supporte les remboursements partiels
        # en interne, mais le modèle ne distingue pas partiel/total)
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=['status'])

        payment.reservation.status = Reservation.Status.CANCELLED
        payment.reservation.save(update_fields=['status', 'updated_at'])

        logger.info(
            "[Payment] #%s remboursé — montant: %s XOF — refund_id: %s",
            payment.id, result.get('amount_xof'), result.get('refund_id'),
        )

        return Response({
            'message': result['message'],
            'payment': PaymentSerializer(payment).data,
            'refund_id': result.get('refund_id'),
            'refunded_amount_xof': str(result.get('amount_xof', amount_xof or payment.amount)),
        }, status=status.HTTP_200_OK)


# ════════════════════════════════════════════════════════════════════════════
# GET /api/payments/{id}/invoice/
# ════════════════════════════════════════════════════════════════════════════

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
            payment = Payment.objects.select_related(
                'reservation__space', 'user'
            ).get(id=pk)
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

        if payment.status != Payment.Status.COMPLETED:
            return Response(
                {'error': "La facture n'est disponible que pour les paiements complétés."},
                status=status.HTTP_400_BAD_REQUEST
            )

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


# ════════════════════════════════════════════════════════════════════════════
# POST /api/payments/webhook/
# Stripe Webhook — source de vérité, ne nécessite PAS d'authentification JWT
# ════════════════════════════════════════════════════════════════════════════

class StripeWebhookView(APIView):
    """
    Endpoint Stripe Webhook.

    Stripe appelle ce endpoint pour notifier les événements de paiement.
    C'est le mécanisme de backup : si l'utilisateur ferme son navigateur
    avant que /stripe-confirm/ soit appelé, le webhook confirme quand même.

    Configuration :
        Dashboard → https://dashboard.stripe.com/test/webhooks
        URL       : https://ton-domaine.com/api/payments/webhook/
        Événements à activer :
            payment_intent.succeeded
            payment_intent.payment_failed
            charge.refunded

    En local :
        $ stripe listen --forward-to localhost:8000/api/payments/webhook/

    Sécurité : Pas de JWT ici. La sécurité repose sur la signature HMAC
    vérifiée via STRIPE_WEBHOOK_SECRET.
    """
    permission_classes = []   # Pas d'auth JWT — Stripe ne l'envoie pas
    authentication_classes = []

    @extend_schema(exclude=True)  # Exclure de la doc Swagger (endpoint interne)
    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

        if not sig_header:
            logger.warning("[Webhook] Requête sans header Stripe-Signature — rejetée")
            return HttpResponse('Missing signature', status=400)

        # ── Validation de la signature HMAC ───────────────────────────────────
        try:
            event = construct_webhook_event(payload, sig_header)
        except ValueError:
            logger.error("[Webhook] Payload JSON invalide")
            return HttpResponse('Invalid payload', status=400)
        except stripe.error.SignatureVerificationError:
            logger.error("[Webhook] Signature HMAC invalide")
            return HttpResponse('Invalid signature', status=400)

        event_type = event['type']
        data_object = event['data']['object']
        pi_id = data_object.get('id')

        logger.info("[Webhook] Événement reçu : %s — %s", event_type, pi_id)

        # ── payment_intent.succeeded ──────────────────────────────────────────
        if event_type == 'payment_intent.succeeded':
            self._handle_payment_succeeded(pi_id)

        # ── payment_intent.payment_failed ─────────────────────────────────────
        elif event_type == 'payment_intent.payment_failed':
            error_msg = data_object.get('last_payment_error', {}).get('message', 'Inconnu')
            self._handle_payment_failed(pi_id, error_msg)

        # ── charge.refunded ───────────────────────────────────────────────────
        elif event_type == 'charge.refunded':
            # charge.payment_intent contient le PI d'origine
            pi_from_charge = data_object.get('payment_intent')
            if pi_from_charge:
                self._handle_charge_refunded(pi_from_charge)

        # Stripe exige une réponse 200 rapide, sinon il retentera pendant 72h
        return HttpResponse(status=200)

    def _handle_payment_succeeded(self, pi_id: str) -> None:
        """Met à jour Payment + Reservation après un paiement réussi."""
        try:
            payment = Payment.objects.select_related('reservation').get(
                transaction_id=pi_id
            )
        except Payment.DoesNotExist:
            logger.warning("[Webhook] Aucun paiement trouvé pour PI %s", pi_id)
            return

        if payment.status == Payment.Status.COMPLETED:
            # Déjà traité via /stripe-confirm/ — idempotent
            return

        now = timezone.now()
        payment.status = Payment.Status.COMPLETED
        payment.paid_at = now
        payment.save(update_fields=['status', 'paid_at'])

        reservation = payment.reservation
        if reservation.status == Reservation.Status.PENDING:
            reservation.status = Reservation.Status.CONFIRMED
            reservation.save(update_fields=['status', 'updated_at'])

        logger.info(
            "[Webhook] Paiement #%s confirmé — réservation #%s → confirmed",
            payment.id, reservation.id,
        )

        try:
            send_payment_completed_email.delay(
                user_email=payment.user.email,
                user_name=payment.user.full_name,
                payment_data={
                    'amount': str(payment.amount),
                    'method': payment.get_method_display(),
                    'transaction_id': payment.transaction_id,
                    'reservation_id': reservation.id,
                }
            )
        except Exception:
            pass

    def _handle_payment_failed(self, pi_id: str, error_msg: str) -> None:
        """Met le paiement en 'failed' après un échec Stripe."""
        try:
            payment = Payment.objects.get(transaction_id=pi_id)
        except Payment.DoesNotExist:
            logger.warning("[Webhook] Aucun paiement trouvé pour PI échoué %s", pi_id)
            return

        if payment.status == Payment.Status.PENDING:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=['status'])
            logger.warning(
                "[Webhook] Paiement #%s échoué — raison: %s",
                payment.id, error_msg,
            )

    def _handle_charge_refunded(self, pi_id: str) -> None:
        """Met le paiement en 'refunded' après un remboursement Stripe."""
        try:
            payment = Payment.objects.get(transaction_id=pi_id)
        except Payment.DoesNotExist:
            logger.warning("[Webhook] Aucun paiement pour charge remboursée PI %s", pi_id)
            return

        if payment.status != Payment.Status.REFUNDED:
            payment.status = Payment.Status.REFUNDED
            payment.save(update_fields=['status'])
            logger.info("[Webhook] Paiement #%s → refunded via webhook", payment.id)
