from django.urls import path
from .views import (
    SpaceListView,
    SpaceDetailView,
    SpaceCreateView,
    SpaceUpdateView,
    SpaceDeleteView,
    AvailableSpaceListView,
    AmenityListView,
    AmenityCreateView,
    SpacePhotoUploadView,
    SpacePhotoDeleteView,
    SpaceAvailabilityGetView,
    
)

app_name = 'spaces'

urlpatterns = [
    # Espaces
    path('',                    SpaceListView.as_view(),          name='space-list'),
    path('available/',          AvailableSpaceListView.as_view(), name='space-available'),
    path('create/',             SpaceCreateView.as_view(),        name='space-create'),
    path('<int:pk>/',           SpaceDetailView.as_view(),        name='space-detail'),
    path('<int:pk>/update/',    SpaceUpdateView.as_view(),        name='space-update'),
    path('<int:pk>/delete/',    SpaceDeleteView.as_view(),        name='space-delete'),

    # Disponibilité en GET
    path('<int:pk>/availability/', SpaceAvailabilityGetView.as_view(), name='space-availability'),

    # Photos
    path('<int:pk>/photos/',    SpacePhotoUploadView.as_view(),   name='space-photo-upload'),
    path('<int:space_pk>/photos/<int:pk>/delete/', SpacePhotoDeleteView.as_view(), name='space-photo-delete'),

    # Équipements
    path('amenities/',          AmenityListView.as_view(),        name='amenity-list'),
    path('amenities/create/',   AmenityCreateView.as_view(),      name='amenity-create'),
]