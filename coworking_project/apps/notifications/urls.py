from django.urls import path
from .views import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkOneReadView,
    NotificationStatsView,
    AdminNotificationListView,
)

app_name = 'notifications'

urlpatterns = [
    path('',          NotificationListView.as_view(),    name='notification-list'),
    path('read/',     NotificationMarkReadView.as_view(), name='notification-read'),
    path('stats/',    NotificationStatsView.as_view(),   name='notification-stats'),
    path('all/',      AdminNotificationListView.as_view(), name='notification-all'),
    path('<int:pk>/read/', NotificationMarkOneReadView.as_view(), name='notification-read-one'),
]