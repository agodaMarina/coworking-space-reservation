from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'notification_type', 'channel', 'status', 'sent_at']
    list_filter = ['notification_type', 'channel', 'status']
    search_fields = ['user__email', 'message']
    ordering = ['-created_at']