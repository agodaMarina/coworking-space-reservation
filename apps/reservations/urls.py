from django.urls import path
from .views import (
    ReservationCreateView,
    ReservationListView,
    ReservationDetailView,
    ReservationCancelView,
    ReservationUpdateView,
    SpaceAvailabilityView,
    InitiatePaymentView,
)

app_name = 'reservations'

urlpatterns = [
    # Réservations
    path('',              ReservationListView.as_view(),   name='reservation-list'),
    path('create/',       ReservationCreateView.as_view(), name='reservation-create'),
    path('<int:pk>/',     ReservationDetailView.as_view(), name='reservation-detail'),
    path('<int:pk>/cancel/', ReservationCancelView.as_view(), name='reservation-cancel'),
    path('<int:pk>/update/', ReservationUpdateView.as_view(), name='reservation-update'),
    path('<int:pk>/initiate-payment/', InitiatePaymentView.as_view(), name='initiate-payment'),

    # Disponibilité
    path('availability/<int:pk>/', SpaceAvailabilityView.as_view(), name='space-availability'),
]