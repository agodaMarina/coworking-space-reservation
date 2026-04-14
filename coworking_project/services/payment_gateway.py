import uuid
from django.utils import timezone


def simulate_payment(amount, method, user):
    """
    Simule un paiement.
    En production, remplacer par l'appel API FedaPay ou Stripe.
    """
    transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

    return {
        'success': True,
        'transaction_id': transaction_id,
        'amount': amount,
        'method': method,
        'paid_at': timezone.now(),
        'message': f'Paiement de {amount} FCFA effectué avec succès via {method}.'
    }


def process_refund(transaction_id, amount):
    """
    Simule un remboursement.
    En production, remplacer par l'appel API de remboursement.
    """
    return {
        'success': True,
        'refund_id': f"REF-{uuid.uuid4().hex[:12].upper()}",
        'transaction_id': transaction_id,
        'amount': amount,
        'message': f'Remboursement de {amount} FCFA effectué avec succès.'
    }