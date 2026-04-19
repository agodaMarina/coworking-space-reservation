# apps/payments/payment_gateway.py
"""
Service de paiement — Stripe (mode test) + méthodes locales (cash, virement).

Choix d'architecture : Payment Intent (pas Checkout Session)
→ Adapté à un frontend Angular SPA qui gère son propre formulaire
→ Flux : backend crée le PI → renvoie client_secret → Angular confirme via Stripe.js
→ Webhook reçoit la confirmation serveur (source of truth)

Stripe ne supporte pas XOF (FCFA).
Stratégie : les montants sont stockés en XOF en base, et convertis en EUR
pour Stripe via un taux de référence FCFA→EUR (1 EUR ≈ 655.957 XOF).
"""

import uuid
import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Initialisation Stripe ────────────────────────────────────────────────────
stripe.api_key = settings.STRIPE['SECRET_KEY']

# Taux de conversion FCFA → EUR (taux fixe zone CFA)
# 1 EUR = 655.957 XOF (parité fixe officielle)
XOF_TO_EUR_RATE = Decimal('655.957')


# ────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ────────────────────────────────────────────────────────────────────────────

def fcfa_to_eur_cents(amount_xof: Decimal) -> int:
    """
    Convertit un montant FCFA en centimes EUR pour Stripe.
    Stripe exige des entiers en plus petite unité monétaire (centimes).

    Exemple : 10 000 XOF → 1525 centimes EUR (≈ 15.25 €)
    """
    amount_eur = Decimal(str(amount_xof)) / XOF_TO_EUR_RATE
    return max(1, int(round(amount_eur * 100)))  # minimum 1 centime


def eur_cents_to_fcfa(amount_cents: int) -> Decimal:
    """
    Convertit des centimes EUR en FCFA.
    Utilisé pour afficher les montants reçus depuis Stripe.
    """
    amount_eur = Decimal(amount_cents) / 100
    return (amount_eur * XOF_TO_EUR_RATE).quantize(Decimal('1'))


# ────────────────────────────────────────────────────────────────────────────
# PAYMENT INTENT — Création
# ────────────────────────────────────────────────────────────────────────────

def create_payment_intent(amount_xof: Decimal, user, reservation) -> dict:
    """
    Crée un PaymentIntent Stripe et retourne le client_secret
    à transmettre au frontend Angular pour confirmation via Stripe.js.

    Le montant est stocké en XOF en base Django, mais envoyé en EUR centimes
    à Stripe (XOF n'est pas supporté par Stripe).

    Args:
        amount_xof  : Montant en FCFA (Decimal)
        user        : Instance User Django (pour metadata et email)
        reservation : Instance Reservation Django (pour metadata)

    Returns:
        dict avec :
          - success (bool)
          - payment_intent_id (str) : "pi_xxx"  → à stocker dans Payment.transaction_id
          - client_secret (str)     : à envoyer au frontend
          - amount_xof (Decimal)    : montant original FCFA
          - amount_eur_cents (int)  : montant envoyé à Stripe
          - status (str)            : statut initial Stripe
        Ou en cas d'erreur :
          - success (bool) False
          - error (str)
          - error_code (str|None)
    """
    amount_cents = fcfa_to_eur_cents(Decimal(str(amount_xof)))

    metadata = {
        'integration': 'django_coworking',
        'user_id': str(user.id),
        'user_email': str(user.email),
        'reservation_id': str(reservation.id),
        'space_id': str(reservation.space_id),
        'amount_xof': str(amount_xof),
        'billing_type': reservation.billing_type,
        'created_at': timezone.now().isoformat(),
    }

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='eur',                          # XOF non supporté → EUR
            automatic_payment_methods={"enabled": True},
            receipt_email=user.email,
            description=(
                f"Réservation #{reservation.id} — "
                f"{reservation.space} — "
                f"{reservation.start_datetime.strftime('%d/%m/%Y %H:%M')}"
            ),
            metadata=metadata,
        )

        logger.info(
            "[Stripe] PaymentIntent créé : %s — %s XOF (%s EUR cents) — user: %s",
            intent.id, amount_xof, amount_cents, user.email,
        )

        return {
            'success': True,
            'payment_intent_id': intent.id,
            'client_secret': intent.client_secret,
            'amount_xof': amount_xof,
            'amount_eur_cents': amount_cents,
            'currency_stripe': 'eur',
            'status': intent.status,   # 'requires_payment_method'
            'message': 'PaymentIntent créé. En attente de confirmation par le client.',
        }

    except stripe.error.CardError as e:
        # Carte refusée (rare à la création, mais possible)
        logger.warning("[Stripe] Carte refusée : %s", e.user_message)
        return {'success': False, 'error': e.user_message, 'error_code': e.code}

    except stripe.error.InvalidRequestError as e:
        logger.error("[Stripe] Requête invalide : %s", e.user_message)
        return {'success': False, 'error': e.user_message or str(e), 'error_code': e.code}

    except stripe.error.AuthenticationError:
        logger.critical("[Stripe] Clé API invalide — vérifier STRIPE_SECRET_KEY dans .env")
        return {'success': False, 'error': 'Erreur de configuration du service de paiement.', 'error_code': 'auth_error'}

    except stripe.error.APIConnectionError:
        logger.error("[Stripe] Impossible de joindre l'API Stripe (réseau)")
        return {'success': False, 'error': 'Service de paiement temporairement indisponible.', 'error_code': 'network_error'}

    except stripe.error.StripeError as e:
        logger.error("[Stripe] Erreur inattendue : %s", str(e))
        return {'success': False, 'error': 'Erreur lors de la création du paiement.', 'error_code': 'stripe_error'}


# ────────────────────────────────────────────────────────────────────────────
# PAYMENT INTENT — Récupération / Vérification côté serveur
# ────────────────────────────────────────────────────────────────────────────

def retrieve_payment_intent(payment_intent_id: str) -> dict:
    """
    Récupère un PaymentIntent depuis l'API Stripe pour vérifier son statut.
    Appelé après que le frontend a confirmé le paiement, avant de valider
    la réservation en base.

    C'est la vérification serveur indispensable : ne jamais faire confiance
    au frontend seul pour marquer un paiement comme réussi.

    Statuts Stripe possibles :
        requires_payment_method → pas encore de carte
        requires_confirmation   → prêt à confirmer
        requires_action         → authentification 3D Secure requise
        processing              → en cours de traitement
        succeeded               → paiement réussi ✅
        canceled                → annulé

    Args:
        payment_intent_id : L'ID Stripe du PaymentIntent (ex: "pi_3Px...")

    Returns:
        dict avec 'success', 'paid' (bool), 'status', 'amount_xof', 'paid_at'
    """
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        paid = intent.status == 'succeeded'

        return {
            'success': True,
            'payment_intent_id': intent.id,
            'status': intent.status,
            'paid': paid,
            'amount_xof': eur_cents_to_fcfa(intent.amount) if paid else None,
            'amount_eur_cents': intent.amount,
            'currency_stripe': intent.currency,
            'paid_at': timezone.now() if paid else None,
            'metadata': dict(intent.metadata),
        }

    except stripe.error.InvalidRequestError as e:
        # PI introuvable ou ID malformé
        logger.error("[Stripe] PaymentIntent introuvable : %s — %s", payment_intent_id, e.user_message)
        return {'success': False, 'error': 'Transaction introuvable.', 'error_code': e.code}

    except stripe.error.StripeError as e:
        logger.error("[Stripe] Erreur récupération PI %s : %s", payment_intent_id, str(e))
        return {'success': False, 'error': 'Erreur lors de la vérification du paiement.'}


# ────────────────────────────────────────────────────────────────────────────
# REMBOURSEMENT
# ────────────────────────────────────────────────────────────────────────────

def process_refund(transaction_id: str, amount_xof: Decimal = None) -> dict:
    """
    Effectue un remboursement.

    - Si transaction_id commence par "pi_" → remboursement Stripe réel
    - Sinon (TXN-...) → simulation pour cash/virement

    Args:
        transaction_id : ID Stripe "pi_xxx" ou ID local "TXN-xxx"
        amount_xof     : Montant partiel à rembourser en FCFA (None = total)

    Returns:
        dict avec 'success', 'refund_id', 'amount_xof', 'status', 'message'
    """
    # ── Paiements locaux (cash, virement bancaire) ───────────────────────────
    if not transaction_id.startswith('pi_'):
        refund_id = f"REF-{uuid.uuid4().hex[:12].upper()}"
        logger.info("[Remboursement local] %s — montant: %s XOF", transaction_id, amount_xof)
        return {
            'success': True,
            'refund_id': refund_id,
            'transaction_id': transaction_id,
            'amount_xof': amount_xof,
            'status': 'succeeded',
            'message': f'Remboursement de {amount_xof} XOF effectué (hors Stripe).',
        }

    # ── Remboursement Stripe ─────────────────────────────────────────────────
    refund_params = {'payment_intent': transaction_id}
    if amount_xof is not None:
        refund_params['amount'] = fcfa_to_eur_cents(Decimal(str(amount_xof)))

    try:
        refund = stripe.Refund.create(**refund_params)
        refunded_xof = eur_cents_to_fcfa(refund.amount)
        success = refund.status in ('succeeded', 'pending')

        logger.info(
            "[Stripe] Remboursement %s créé pour PI %s — %s XOF — statut: %s",
            refund.id, transaction_id, refunded_xof, refund.status,
        )

        return {
            'success': success,
            'refund_id': refund.id,
            'transaction_id': transaction_id,
            'amount_xof': refunded_xof,
            'amount_eur_cents': refund.amount,
            'status': refund.status,
            'message': f'Remboursement de {refunded_xof} XOF initié avec succès.',
        }

    except stripe.error.InvalidRequestError as e:
        # Cas courants : PI déjà remboursé, montant supérieur au disponible, PI introuvable
        logger.error("[Stripe] Remboursement refusé pour %s : %s", transaction_id, e.user_message)
        return {
            'success': False,
            'error': e.user_message or str(e),
            'error_code': e.code,
        }

    except stripe.error.StripeError as e:
        logger.error("[Stripe] Erreur remboursement %s : %s", transaction_id, str(e))
        return {'success': False, 'error': 'Erreur lors du remboursement.'}


# ────────────────────────────────────────────────────────────────────────────
# MÉTHODES LOCALES (cash, virement) — conservées et propres
# ────────────────────────────────────────────────────────────────────────────

def process_local_payment(amount_xof: Decimal, method: str, user) -> dict:
    """
    Traite les paiements en espèces ou par virement bancaire.
    Ces méthodes ne passent pas par Stripe.

    Args:
        amount_xof : Montant en FCFA
        method     : 'cash' ou 'bank_transfer'
        user       : Instance User Django

    Returns:
        dict avec 'success', 'transaction_id', 'amount_xof', 'paid_at', 'message'
    """
    transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
    method_labels = {'cash': 'Espèces', 'bank_transfer': 'Virement bancaire'}

    logger.info(
        "[Paiement local] %s — %s XOF — user: %s → %s",
        method, amount_xof, getattr(user, 'email', str(user)), transaction_id,
    )

    return {
        'success': True,
        'transaction_id': transaction_id,
        'amount_xof': amount_xof,
        'method': method,
        'paid_at': timezone.now(),
        'message': f'Paiement de {amount_xof} XOF enregistré via {method_labels.get(method, method)}.',
    }


# ────────────────────────────────────────────────────────────────────────────
# WEBHOOK — Validation de la signature Stripe
# ────────────────────────────────────────────────────────────────────────────

def construct_webhook_event(payload: bytes, sig_header: str):
    """
    Valide la signature du webhook Stripe et retourne l'événement décodé.

    Lève :
        stripe.error.SignatureVerificationError → signature invalide
        ValueError                              → payload malformé

    Usage dans la view webhook :
        event = construct_webhook_event(request.body, request.META.get('HTTP_STRIPE_SIGNATURE'))
    """
    return stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.STRIPE['WEBHOOK_SECRET'],
    )
