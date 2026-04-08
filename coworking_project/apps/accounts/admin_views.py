from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import filters, serializers
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from .models import User
from .serializers import UserProfileSerializer, AdminUserUpdateSerializer
from .permissions import IsAdminUser


class AdminUserListView(generics.ListAPIView):
    """Liste tous les utilisateurs — admin seulement"""
    permission_classes = [IsAdminUser]
    serializer_class = UserProfileSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['role', 'is_active', 'is_verified']
    search_fields = ['email', 'first_name', 'last_name']
    queryset = User.objects.all().order_by('-date_joined')

    @extend_schema(
        summary="Liste tous les utilisateurs (admin)",
        tags=['Administration']
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminUserUpdateView(APIView):
    """Modifier un utilisateur — admin seulement"""
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=AdminUserUpdateSerializer,
        responses={200: UserProfileSerializer},
        summary="Modifier un utilisateur (admin)",
        tags=['Administration']
    )
    def patch(self, request, pk):
        # 1. Récupération de l'utilisateur
        try:
            user = User.objects.get(id=pk)
        except User.DoesNotExist:
            return Response(
                {'error': 'Utilisateur introuvable.'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # 2. Contrôle strict du corps vide
        if not request.data:
            return Response(
                {'error': "Le corps de la requête est vide. Aucune modification à effectuer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Initialisation du serializer avec l'instance existante
        # partial=True permet de ne modifier qu'un seul champ sur les trois
        serializer = AdminUserUpdateSerializer(user, data=request.data, partial=True)

        # 4. Validation automatique
        if not serializer.is_valid():
            # On réutilise ta logique de message clair pour le premier champ en erreur
            first_field = list(serializer.errors.keys())[0]
            return Response(
                {'error': f"Erreur sur le champ '{first_field}': {serializer.errors[first_field][0]}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Sauvegarde via le serializer
        updated_user = serializer.save()

        return Response({
            'message': 'Utilisateur mis à jour avec succès.',
            'user': UserProfileSerializer(updated_user).data
        }, status=status.HTTP_200_OK)