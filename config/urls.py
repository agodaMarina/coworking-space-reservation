from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from apps.reservations.admin_views import DashboardView, ExportReservationsCSVView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Documentation API
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Applications
    path('api/auth/',          include('apps.accounts.urls')),
    path('api/spaces/',        include('apps.spaces.urls')),
    path('api/reservations/',  include('apps.reservations.urls')),
    path('api/payments/',      include('apps.payments.urls')),
    path('api/notifications/', include('apps.notifications.urls')),

    # Administration
    path('api/admin/dashboard/', DashboardView.as_view(),           name='admin-dashboard'),
    path('api/admin/export/reservations/', ExportReservationsCSVView.as_view(), name='admin-export'),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )