from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer pour afficher une notification"""

    type_display = serializers.CharField(
        source='get_notification_type_display',
        read_only=True
    )
    channel_display = serializers.CharField(
        source='get_channel_display',
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'type_display',
            'channel', 'channel_display',
            'status', 'status_display',
            'message', 'sent_at', 'created_at'
        ]
        read_only_fields = ['id', 'sent_at', 'created_at']