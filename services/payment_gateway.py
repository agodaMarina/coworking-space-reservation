# services/payment_gateway.py
"""
Service de paiement unifié — trois backends :

  1. Stripe       → paiement par carte (method='card')
                    XOF→EUR converti (Stripe ne supporte pas XOF)
                    Flux : backend crée PI → client_secret → Angular confirme via Stripe.js

  2. FedaPay      → Mobile Money (method='mobile_money') — Flooz MTN / T-Money Moov
                    XOF supporté nativement — aucune conversion
                    SDK v0.3.0 = webhook uniquement → transactions via REST API directe
                    Flux : backend POST /transactions → retourne payment_url → user paie
                           → FedaPay appelle webhook → backend confirme en base

  3. Local        → espèces / virement (method='cash' | 'bank_transfer')
                    Pas d'API tierce — validation manuelle par l'admin
"""

import uuid
import json
import logging
from decimal import Decimal

import requests
import stripe
from fedapay import Webhook as _FedaPayWebhook
from fedapay import error as _fedapay_error
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Initialisation Stripe ─────────────────────────────────────────────────────
stripe.api_key = settings.STRIPE['SECRET_KEY']

# Taux de conversion FCFA → EUR (parité fixe zone CFA — 1 EUR = 655.957 XOF)
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
# FEDAPAY — Mobile Money (Flooz MTN / T-Money Moov)
#
# SDK fedapay v0.3.0 = webhook uniquement (Webhook.construct_event).
# Création / récupération de transactions → REST API directe via requests.
#
# Flux paiement :
#   1. Backend POST /v1/transactions  →  reçoit {id, receipt_url, status}
#   2. Backend renvoie receipt_url au frontend
#   3. Frontend redirige l'utilisateur vers receipt_url (page FedaPay hébergée)
#   4. L'utilisateur saisit son numéro Mobile Money et valide
#   5. FedaPay envoie POST → /api/payments/fedapay-webhook/ (transaction.approved / declined)
#   6. Backend met à jour Payment + Reservation
# ────────────────────────────────────────────────────────────────────────────

_FEDAPAY_BASE_URLS = {
    'sandbox': 'https://sandbox.fedapay.com/api',
    'live':    'https://api.fedapay.com/v1',
}

FEDAPAY_OPERATORS = {
    'mtn':  'Flooz (MTN)',
    'moov': 'T-Money (Moov)',
}


def _fedapay_base_url() -> str:
    env = settings.FEDAPAY.get('ENVIRONMENT', 'sandbox')
    return _FEDAPAY_BASE_URLS.get(env, _FEDAPAY_BASE_URLS['sandbox'])


def _fedapay_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        'Authorization': f"Bearer {settings.FEDAPAY['SECRET_KEY']}",
        'Content-Type': 'application/json',
    })
    return session


def _parse_phone(phone_number: str) -> tuple:
    """Retourne (local_number, country_code) depuis un numéro international."""
    clean = phone_number.strip().replace(' ', '').replace('-', '')
    prefixes = {
        '+228': 'tg', '00228': 'tg',
        '+229': 'bj', '00229': 'bj',
        '+225': 'ci', '00225': 'ci',
        '+221': 'sn', '00221': 'sn',
        '+226': 'bf', '00226': 'bf',
    }
    for prefix, country in prefixes.items():
        if clean.startswith(prefix):
            return clean[len(prefix):], country
    return clean.lstrip('0') or clean, 'tg'


def create_fedapay_transaction(
    amount_xof: Decimal,
    user,
    reservation,
    phone_number: str,
    operator: str = 'mtn',
) -> dict:
    """
    Crée une transaction FedaPay via l'API REST et retourne le lien de paiement.

    Le SDK fedapay v0.3.0 ne couvre que les webhooks — on appelle l'API directement.

    Flux :
        POST /v1/transactions  →  {id, receipt_url, status: 'pending'}
        Le frontend redirige l'utilisateur vers receipt_url.
        L'utilisateur choisit Mobile Money sur la page FedaPay et valide.
        FedaPay notifie via webhook → transaction.approved / transaction.declined.

    Args:
        amount_xof   : Montant en XOF (Decimal) — FedaPay supporte XOF nativement
        user         : Instance User Django
        reservation  : Instance Reservation Django
        phone_number : Numéro Mobile Money du client (ex: "+22890123456")
        operator     : 'mtn' (Flooz) ou 'moov' (T-Money) — indicatif pour le frontend

    Returns:
        dict avec :
          - success (bool)
          - transaction_id (str) : "FEDA-{id}" → stocker dans Payment.transaction_id
          - fedapay_id (int)     : ID numérique FedaPay
          - payment_url (str)    : receipt_url → à ouvrir par le frontend
          - status (str)         : 'pending'
          - operator_label (str) : libellé de l'opérateur
          - message (str)
        Ou en cas d'erreur :
          - success (bool) False
          - error (str)
          - error_code (str)
    """
    local_number, country_code = _parse_phone(phone_number)

    payload = {
        'description': (
            f"Réservation #{reservation.id} — "
            f"{reservation.space} — "
            f"{reservation.start_datetime.strftime('%d/%m/%Y %H:%M')}"
        ),
        'amount': int(amount_xof),
        'currency': {'iso': 'XOF'},
        'callback_url': settings.FEDAPAY['CALLBACK_URL'],
        'customer': {
            'firstname': getattr(user, 'first_name', '') or '',
            'lastname':  getattr(user, 'last_name',  '') or '',
            'email':     str(user.email),
            'phone_number': {
                'number':  local_number,
                'country': country_code,
            },
        },
    }

    try:
        session = _fedapay_session()
        response = session.post(
            f"{_fedapay_base_url()}/transactions",
            json=payload,
            timeout=15,
        )

        if response.status_code == 401:
            logger.critical("[FedaPay] Clé API invalide — vérifier FEDAPAY_SECRET_KEY dans .env")
            return {'success': False, 'error': 'Erreur de configuration du service de paiement mobile.', 'error_code': 'auth_error'}

        if response.status_code in (400, 422):
            data = response.json()
            error_msg = data.get('message') or str(data)
            logger.error("[FedaPay] Requête invalide : %s", error_msg)
            return {'success': False, 'error': error_msg, 'error_code': 'invalid_request'}

        response.raise_for_status()
        data = response.json()

        # La réponse FedaPay enveloppe la transaction dans une clé "v1/transaction"
        tx = data.get('v1/transaction') or data.get('transaction') or data
        fedapay_id  = tx['id']
        receipt_url = tx.get('receipt_url') or tx.get('url')

        logger.info(
            "[FedaPay] Transaction #%s créée — %s XOF — %s — user: %s",
            fedapay_id, amount_xof, FEDAPAY_OPERATORS.get(operator, operator), user.email,
        )

        return {
            'success': True,
            'fedapay_id': fedapay_id,
            'transaction_id': f"FEDA-{fedapay_id}",
            'status': tx.get('status', 'pending'),
            'payment_url': receipt_url,
            'operator': operator,
            'operator_label': FEDAPAY_OPERATORS.get(operator, operator),
            'message': (
                f"Transaction Mobile Money créée. Redirigez l'utilisateur vers l'URL de paiement "
                f"pour valider via {FEDAPAY_OPERATORS.get(operator, operator)}."
            ),
        }

    except requests.exceptions.ConnectionError:
        logger.error("[FedaPay] Impossible de joindre l'API FedaPay (réseau)")
        return {'success': False, 'error': 'Service de paiement mobile temporairement indisponible.', 'error_code': 'network_error'}

    except requests.exceptions.Timeout:
        logger.error("[FedaPay] Timeout lors de la création de la transaction")
        return {'success': False, 'error': 'Le service de paiement mobile ne répond pas. Réessayez.', 'error_code': 'timeout'}

    except Exception as e:
        logger.error("[FedaPay] Erreur inattendue lors de la création : %s", str(e))
        return {'success': False, 'error': 'Erreur lors de la création du paiement mobile.', 'error_code': 'fedapay_error'}


def retrieve_fedapay_transaction(fedapay_id) -> dict:
    """
    Récupère le statut d'une transaction FedaPay via GET /v1/transactions/{id}.

    Utilisé pour vérifier côté serveur qu'un paiement Mobile Money est bien
    approuvé (ne jamais faire confiance au seul callback frontend).

    Statuts FedaPay :
        pending     → en attente de paiement
        approved    → paiement confirmé par l'opérateur ✅
        declined    → refusé (solde insuffisant, annulé, timeout)
        refunded    → remboursé
        transferred → fonds transférés au marchand
        canceled    → annulé avant paiement

    Args:
        fedapay_id : ID numérique FedaPay, ou chaîne "FEDA-{id}" ou "{id}"

    Returns:
        dict avec 'success', 'paid' (bool), 'status', 'amount_xof', 'paid_at'
    """
    raw_id = str(fedapay_id).replace('FEDA-', '')
    try:
        numeric_id = int(raw_id)
    except ValueError:
        return {'success': False, 'error': 'Identifiant FedaPay invalide.', 'error_code': 'invalid_id'}

    try:
        session = _fedapay_session()
        response = session.get(
            f"{_fedapay_base_url()}/transactions/{numeric_id}",
            timeout=15,
        )

        if response.status_code == 404:
            logger.error("[FedaPay] Transaction introuvable : %s", numeric_id)
            return {'success': False, 'error': 'Transaction Mobile Money introuvable.', 'error_code': 'not_found'}

        if response.status_code == 401:
            return {'success': False, 'error': 'Erreur de configuration du service de paiement mobile.', 'error_code': 'auth_error'}

        response.raise_for_status()
        data = response.json()

        tx     = data.get('v1/transaction') or data.get('transaction') or data
        status = tx.get('status', 'pending')
        paid   = status in ('approved', 'transferred')

        return {
            'success': True,
            'fedapay_id': numeric_id,
            'transaction_id': f"FEDA-{numeric_id}",
            'status': status,
            'paid': paid,
            'amount_xof': Decimal(str(tx['amount'])) if paid else None,
            'currency': 'XOF',
            'paid_at': timezone.now() if paid else None,
        }

    except requests.exceptions.ConnectionError:
        logger.error("[FedaPay] Réseau indisponible lors de la vérification de %s", fedapay_id)
        return {'success': False, 'error': 'Service de paiement mobile indisponible.', 'error_code': 'network_error'}

    except Exception as e:
        logger.error("[FedaPay] Erreur récupération transaction %s : %s", fedapay_id, str(e))
        return {'success': False, 'error': 'Erreur lors de la vérification du paiement mobile.'}


def construct_fedapay_webhook_event(payload: bytes, sig_header: str) -> dict:
    """
    Valide la signature du webhook FedaPay et retourne l'événement décodé.

    FedaPay utilise le header 'X-FEDAPAY-SIGNATURE' au format :
        t={timestamp},s={hmac_sha256}
    où le contenu signé est "{timestamp}.{payload_utf8}"

    Si FEDAPAY_WEBHOOK_SECRET n'est pas configuré (sandbox local / tests),
    la vérification est ignorée et le JSON est parsé directement.

    Lève :
        fedapay.error.SignatureVerificationError → signature invalide ou timestamp hors tolérance
        ValueError                               → payload JSON malformé
    """
    secret = settings.FEDAPAY.get('WEBHOOK_SECRET', '')
    env    = settings.FEDAPAY.get('ENVIRONMENT', 'sandbox')

    # Secret absent ou non encore configuré (placeholder) → skip en sandbox
    secret_is_real = bool(secret) and not secret.startswith('whsec_feda_...')

    if not secret_is_real:
        logger.warning("[FedaPay Webhook] FEDAPAY_WEBHOOK_SECRET non configuré — vérification ignorée (sandbox)")
        return json.loads(payload)

    # En sandbox, autoriser les requêtes sans header de signature (tests locaux)
    if not sig_header and env == 'sandbox':
        logger.warning("[FedaPay Webhook] Requête sans signature acceptée en sandbox")
        return json.loads(payload)

    return _FedaPayWebhook.construct_event(payload, sig_header, secret)


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
