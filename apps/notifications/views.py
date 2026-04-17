from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from .models import Notification
from .serializers import NotificationSerializer
from apps.accounts.permissions import IsAdminUser


class NotificationListView(generics.ListAPIView):
    """Liste des notifications de l'utilisateur connecté"""
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    @extend_schema(
        summary="Mes notifications",
        tags=['Notifications']
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)


class NotificationMarkReadView(APIView):
    """Marquer toutes les notifications comme lues"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: None},
        summary="Marquer les notifications comme lues",
        tags=['Notifications']
    )
    def post(self, request):
        Notification.objects.filter(
            user=request.user,
            status='pending'
        ).update(status='sent')

        return Response(
            {'message': 'Toutes les notifications ont été marquées comme lues.'},
            status=status.HTTP_200_OK
        )


class NotificationStatsView(APIView):
    """Nombre de notifications non lues"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Statistiques des notifications",
        tags=['Notifications'],
        responses={200: NotificationSerializer}
    )
    def get(self, request):
        total = Notification.objects.filter(user=request.user).count()
        unread = Notification.objects.filter(
            user=request.user,
            status='pending'
        ).count()

        return Response({
            'total': total,
            'unread': unread,
        }, status=status.HTTP_200_OK)


class AdminNotificationListView(generics.ListAPIView):
    """Liste de toutes les notifications — admin"""
    permission_classes = [IsAdminUser]
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()

    @extend_schema(
        summary="Toutes les notifications (admin)",
        tags=['Notifications']
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class NotificationMarkOneReadView(APIView):
    """Marquer une notification individuelle comme lue"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: None},
        summary="Marquer une notification comme lue",
        tags=['Notifications']
    )
    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(
                id=pk,
                user=request.user
            )
        except Notification.DoesNotExist:
            return Response(
                {'error': 'Notification introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        notification.status = 'sent'
        notification.save()

        return Response(
            {'message': 'Notification marquée comme lue.'},
            status=status.HTTP_200_OK
        )