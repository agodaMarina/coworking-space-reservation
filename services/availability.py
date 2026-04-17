from django.utils import timezone
from apps.reservations.models import Reservation


def check_availability(space, start_datetime, end_datetime, exclude_id=None):
    """
    Vérifie si un espace est disponible pour une période donnée.
    Retourne True si disponible, False sinon.
    """
    # Étape de sécurité : Rendre les dates "aware" si elles ne le sont pas
    # Cela évite l'erreur TypeError: can't compare offset-naive and offset-aware
    if start_datetime and timezone.is_naive(start_datetime):
        start_datetime = timezone.make_aware(start_datetime)
    
    if end_datetime and timezone.is_naive(end_datetime):
        end_datetime = timezone.make_aware(end_datetime)

    # Validations logiques
    if start_datetime >= end_datetime:
        return False, "La date de fin doit être après la date de début."

    if start_datetime < timezone.now():
        return False, "La date de début ne peut pas être dans le passé."

    # Recherche de chevauchements
    overlapping = Reservation.objects.filter(
        space=space,
        status__in=['pending', 'confirmed'],
        start_datetime__lt=end_datetime,
        end_datetime__gt=start_datetime,
    )

    if exclude_id:
        overlapping = overlapping.exclude(id=exclude_id)

    if overlapping.exists():
        return False, "Cet espace est déjà réservé pour cette période."

    return True, "Disponible."


def calculate_price(space, start_datetime, end_datetime, billing_type):
    """
    Calcule le prix total d'une réservation.
    """
    delta = end_datetime - start_datetime
    total_hours = delta.total_seconds() / 3600
    total_days = delta.days

    if billing_type == 'hourly':
        total_price = float(space.price_per_hour) * total_hours
    else:
        total_price = float(space.price_per_day) * (total_days if total_days > 0 else 1)

    return round(total_price, 2)