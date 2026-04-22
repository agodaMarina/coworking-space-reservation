from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.utils import timezone
from django.http import HttpResponse
from datetime import datetime, timedelta
import csv

from apps.accounts.permissions import IsAdminUser
from apps.reservations.models import Reservation
from apps.payments.models import Payment


class DashboardView(APIView):
    """Tableau de bord admin — KPIs"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Tableau de bord (admin)",
        tags=['Administration'],
        parameters=[
            OpenApiParameter('date_from', str, description='Date début (YYYY-MM-DD)'),
            OpenApiParameter('date_to', str, description='Date fin (YYYY-MM-DD)'),
        ],
        responses={200: serializers.DictField()}
    )
    def get(self, request):
        from django.db.models import Sum, Count

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if date_from:
            date_from = timezone.make_aware(datetime.strptime(date_from, '%Y-%m-%d'))
        else:
            date_from = timezone.now() - timedelta(days=30)

        if date_to:
            date_to = timezone.make_aware(datetime.strptime(date_to, '%Y-%m-%d'))
        else:
            date_to = timezone.now()

        reservations = Reservation.objects.filter(
            created_at__gte=date_from,
            created_at__lte=date_to,
        )

        total_revenue = Payment.objects.filter(
            status='completed',
            created_at__gte=date_from,
            created_at__lte=date_to,
        ).aggregate(total=Sum('amount'))['total'] or 0

        total = reservations.count()
        confirmed = reservations.filter(status='confirmed').count()
        completed = reservations.filter(status='completed').count()
        occupancy_rate = round((confirmed + completed) / total, 2) if total > 0 else 0

        bookings_today = Reservation.objects.filter(
            start_datetime__date=timezone.now().date()
        ).select_related('space', 'user')

        return Response({
            'period': {
                'from': str(date_from.date() if hasattr(date_from, 'date') else date_from),
                'to': str(date_to.date() if hasattr(date_to, 'date') else date_to),
            },
            'total_bookings': total,
            'confirmed_bookings': confirmed,
            'cancelled_bookings': reservations.filter(status='cancelled').count(),
            'completed_bookings': reservations.filter(status='completed').count(),
            'total_revenue': str(total_revenue),
            'occupancy_rate': occupancy_rate,
            'bookings_today': [
                {
                    'id': r.id,
                    'space_name': r.space.name,
                    'user_name': r.user.full_name,
                    'start_datetime': r.start_datetime,
                    'end_datetime': r.end_datetime,
                    'status': r.status,
                    'total_price': str(r.total_price),
                }
                for r in bookings_today
            ],
        }, status=status.HTTP_200_OK)


class ExportReservationsCSVView(APIView):
    """Export des réservations en CSV"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Exporter les réservations en CSV",
        tags=['Administration'],
        responses={200: None}
    )
    def get(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="reservations-{timezone.now().strftime("%Y-%m-%d")}.csv"'
        )

        response.write('\ufeff')  # BOM UTF-8 pour Excel

        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Utilisateur', 'Email', 'Espace',
            'Début', 'Fin', 'Durée (h)', 'Statut',
            'Type facturation', 'Prix total (FCFA)',
            'Récurrente', 'Créée le'
        ])

        reservations = Reservation.objects.select_related(
            'user', 'space'
        ).all().order_by('-created_at')

        for r in reservations:
            writer.writerow([
                r.id,
                r.user.full_name,
                r.user.email,
                r.space.name,
                r.start_datetime.strftime('%d/%m/%Y %H:%M'),
                r.end_datetime.strftime('%d/%m/%Y %H:%M'),
                r.duration_hours,
                r.get_status_display(),
                r.get_billing_type_display(),
                r.total_price,
                'Oui' if r.is_recurring else 'Non',
                r.created_at.strftime('%d/%m/%Y %H:%M'),
            ])

        return response