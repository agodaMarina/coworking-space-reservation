from django.utils import timezone
from .availability import check_availability, calculate_price
from apps.reservations.models import Reservation


def create_reservation(user, space, start_datetime, end_datetime, billing_type, notes='', is_recurring=False, recurrence_rule='none'):
    """
    Crée une réservation après vérification des disponibilités.
    """
    is_available, message = check_availability(space, start_datetime, end_datetime)

    if not is_available:
        return None, message

    if not space.is_available:
        return None, "Cet espace n'est pas disponible à la réservation."

    total_price = calculate_price(space, start_datetime, end_datetime, billing_type)

    reservation = Reservation.objects.create(
        user=user,
        space=space,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        status='pending',
        total_price=total_price,
        billing_type=billing_type,
        is_recurring=is_recurring,
        recurrence_rule=recurrence_rule,
        notes=notes,
    )

    return reservation, "Réservation créée avec succès."


def cancel_reservation(reservation, user):
    """
    Annule une réservation.
    """
    if reservation.user != user and not user.is_admin:
        return False, "Vous n'êtes pas autorisé à annuler cette réservation."

    if reservation.status == 'cancelled':
        return False, "Cette réservation est déjà annulée."

    if reservation.status == 'completed':
        return False, "Impossible d'annuler une réservation terminée."

    reservation.status = 'cancelled'
    reservation.save()

    return True, "Réservation annulée avec succès."