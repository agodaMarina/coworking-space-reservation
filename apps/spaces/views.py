from django.db import models
from rest_framework import generics, status, filters, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Space, Amenity, SpacePhoto
from .serializers import (
    SpaceSerializer,
    SpaceCreateUpdateSerializer,
    AmenitySerializer,
    SpacePhotoSerializer,
    SpacePhotoUploadSerializer,
    SpaceMinimalSerializer,
)
from apps.accounts.permissions import IsAdminUser


class SpaceListView(generics.ListAPIView):
    """Liste de tous les espaces disponibles"""

    permission_classes = [AllowAny]
    serializer_class = SpaceSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["space_type", "is_available", "capacity"]
    search_fields = ["name", "description", "address"]
    ordering_fields = ["price_per_hour", "price_per_day", "capacity", "name"]
    ordering = ["name"]

    @extend_schema(summary="Liste de tous les espaces", tags=["Espaces"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return Space.objects.all()


class SpaceDetailView(generics.RetrieveAPIView):
    """Détail d'un espace"""

    permission_classes = [AllowAny]
    serializer_class = SpaceSerializer
    queryset = Space.objects.all()

    @extend_schema(summary="Détail d'un espace", tags=["Espaces"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class SpaceCreateView(generics.CreateAPIView):
    """Créer un nouvel espace — admin seulement"""

    permission_classes = [IsAdminUser]
    serializer_class = SpaceCreateUpdateSerializer
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary="Créer un nouvel espace", tags=["Espaces"])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return Response(
                {
                    "message": "Espace créé avec succès.",
                    "space": SpaceSerializer(serializer.instance).data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SpaceUpdateView(generics.UpdateAPIView):
    """Modifier un espace — admin seulement"""

    permission_classes = [IsAdminUser]
    serializer_class = SpaceCreateUpdateSerializer
    queryset = Space.objects.all()
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary="Modifier un espace", tags=["Espaces"])
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(summary="Modifier partiellement un espace", tags=["Espaces"])
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.data:
            return Response(
                {"error": "Veuillez renseigner les champs à modifier."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "message": "Espace modifié avec succès.",
                    "space": SpaceSerializer(serializer.instance).data,
                }
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SpaceDeleteView(generics.DestroyAPIView):
    """Supprimer un espace — admin seulement"""

    permission_classes = [IsAdminUser]
    queryset = Space.objects.all()
    serializer_class = SpaceSerializer

    @extend_schema(summary="Supprimer un espace", tags=["Espaces"])
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        space_id = instance.id
        self.perform_destroy(instance)
        return Response(
            {"message": "Espace supprimé avec succès.", "space_id": space_id},
            status=status.HTTP_200_OK,
        )


class AvailableSpaceListView(generics.ListAPIView):
    """Liste des espaces disponibles uniquement"""

    permission_classes = [AllowAny]
    serializer_class = SpaceSerializer

    @extend_schema(summary="Liste des espaces disponibles", tags=["Espaces"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return Space.objects.filter(is_available=True)


class AmenityListView(generics.ListAPIView):
    """Liste de tous les équipements"""

    permission_classes = [AllowAny]
    serializer_class = AmenitySerializer
    queryset = Amenity.objects.all()

    @extend_schema(summary="Liste de tous les équipements", tags=["Équipements"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AmenityCreateView(generics.CreateAPIView):
    """Créer un équipement — admin seulement"""

    permission_classes = [IsAdminUser]
    serializer_class = AmenitySerializer

    @extend_schema(summary="Créer un équipement", tags=["Équipements"])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Équipement créé avec succès.", "amenity": serializer.data},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SpaceAvailabilityGetView(APIView):
    """Vérifier la disponibilité d'un espace via GET"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Disponibilités d'un espace",
        tags=["Espaces"],
        parameters=[
            OpenApiParameter(
                "start_datetime", str, description="Date début (ISO 8601)"
            ),
            OpenApiParameter("end_datetime", str, description="Date fin (ISO 8601)"),
            OpenApiParameter("billing_type", str, description="hourly ou daily"),
        ],
        responses={200: serializers.DictField()},
    )
    def get(self, request, pk):
        try:
            space = Space.objects.get(id=pk)
        except Space.DoesNotExist:
            return Response(
                {"error": "Espace introuvable."}, status=status.HTTP_404_NOT_FOUND
            )

        start_datetime = request.query_params.get("start_datetime")
        end_datetime = request.query_params.get("end_datetime")

        if not start_datetime or not end_datetime:
            return Response(
                {"error": "Les paramètres start_datetime et end_datetime sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from services.availability import check_availability, calculate_price
        from django.utils.dateparse import parse_datetime

        start = parse_datetime(start_datetime)
        end = parse_datetime(end_datetime)

        if not start or not end:
            return Response(
                {"error": "Format de date invalide. Utilisez le format ISO 8601."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not space.is_available:
            return Response({
                "space_id": pk,
                "space_name": space.name,
                "is_available": False,
                "message": "Cet espace n'est pas disponible à la réservation.",
            }, status=status.HTTP_200_OK)

        is_available, message = check_availability(space, start, end)

        response_data = {
            "space_id": pk,
            "space_name": space.name,
            "is_available": is_available,
            "message": message,
        }

        if is_available:
            billing_type = request.query_params.get("billing_type", "hourly")
            price = calculate_price(space, start, end, billing_type)
            response_data["estimated_price"] = price
            response_data["billing_type"] = billing_type

        return Response(response_data, status=status.HTTP_200_OK)


class SpacePhotoUploadView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        request=SpacePhotoUploadSerializer,
        responses={201: SpaceMinimalSerializer},  # On utilise le nouveau serializer ici
        tags=["Espaces"],
        description="Upload d'une photo pour un espace. Supporte multipart/form-data et JSON avec base64.",
    )
    def post(self, request, pk):
        try:
            space = Space.objects.get(id=pk)
        except Space.DoesNotExist:
            return Response({"error": "Espace introuvable."}, status=404)

        serializer = SpacePhotoUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        # Gestion de la photo principale
        is_primary = serializer.validated_data.get("is_primary", False)
        if is_primary:
            space.photos.filter(is_primary=True).update(is_primary=False)

        # Déterminer la position (max position + 1)
        max_position = (
            space.photos.aggregate(max_pos=models.Max("position"))["max_pos"] or 0
        )
        next_position = max_position + 1

        try:
            SpacePhoto.objects.create(
                space=space,
                file=serializer.validated_data["file"],
                is_primary=is_primary,
                position=next_position,
            )
        except Exception as e:
            return Response(
                {"error": "Erreur lors du traitement de l'image.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # LA MEILLEURE PRATIQUE :
        # On utilise le sérialiseur dédié pour rendre la réponse.
        output_serializer = SpaceMinimalSerializer(space, context={"request": request})

        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class SpacePhotoDeleteView(generics.DestroyAPIView):
    """Supprimer une photo spécifique d'un espace avec message de confirmation"""

    permission_classes = [IsAdminUser]
    queryset = SpacePhoto.objects.all()
    serializer_class = SpacePhotoSerializer

    @extend_schema(summary="Supprimer une photo d'espace", tags=["Espaces"])
    def delete(self, request, *args, **kwargs):
        # On récupère les deux IDs depuis l'URL
        space_id = self.kwargs.get("space_pk")
        photo_id = self.kwargs.get("pk")

        # Vérification de sécurité : la photo appartient-elle bien à cet espace ?
        try:
            # On vérifie l'existence avant de laisser destroy() faire le travail
            SpacePhoto.objects.get(id=photo_id, space_id=space_id)
        except SpacePhoto.DoesNotExist:
            return Response(
                {"error": "Cette photo n'existe pas pour cet espace."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return super().delete(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Surcharge pour renvoyer un message JSON au lieu de 204 No Content"""
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {
                "message": "La photo a été supprimée avec succès.",
                "photo_id": kwargs.get("pk"),
                "space_id": kwargs.get("space_pk"),
            },
            status=status.HTTP_200_OK,
        )
