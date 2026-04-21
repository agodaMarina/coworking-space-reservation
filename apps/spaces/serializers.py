from rest_framework import serializers
from django.core.files.base import ContentFile
import base64
import uuid
from .models import Space, Amenity, SpacePhoto


class AmenitySerializer(serializers.ModelSerializer):
    """Serializer pour les équipements"""

    class Meta:
        model = Amenity
        fields = ["id", "name", "icon"]


class SpacePhotoSerializer(serializers.ModelSerializer):
    """Serializer pour les photos d'espaces (utilisé dans la galerie)"""

    url = serializers.SerializerMethodField()

    class Meta:
        model = SpacePhoto
        fields = ["id", "url", "is_primary", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at"]

    def get_url(self, obj):
        request = self.context.get("request")
        if request and obj.file:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None


class SpaceSerializer(serializers.ModelSerializer):
    """Serializer pour afficher les détails d'un espace"""

    amenities = AmenitySerializer(many=True, read_only=True)
    space_type_display = serializers.CharField(
        source="get_space_type_display", read_only=True
    )

    # --- MODIFICATIONS ICI ---
    # On récupère la photo principale dynamiquement depuis SpacePhoto
    photo = serializers.SerializerMethodField()
    # On affiche aussi la liste de toutes les photos
    photos = SpacePhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Space
        fields = [
            "id",
            "name",
            "space_type",
            "space_type_display",
            "description",
            "capacity",
            "price_per_hour",
            "price_per_day",
            "address",
            "is_available",
            "photo",
            "photos",
            "amenities",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_photo(self, obj):
        """Logique pour extraire la photo principale ou la première disponible"""
        photo_obj = obj.photos.filter(is_primary=True).first() or obj.photos.first()
        if photo_obj:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(photo_obj.file.url)
            return photo_obj.file.url
        return None


class SpaceCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour créer et modifier un espace (SANS le champ photo direct)"""

    amenities = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Amenity.objects.all(), required=False
    )

    class Meta:
        model = Space
        fields = [
            "id",
            "name",
            "space_type",
            "description",
            "capacity",
            "price_per_hour",
            "price_per_day",
            "address",
            "is_available",
            "amenities",
        ]

    # Validations
    def validate_capacity(self, value):
        if value < 1:
            raise serializers.ValidationError(
                "La capacité doit être d'au moins 1 personne."
            )
        return value

    def validate_price_per_hour(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Le prix par heure doit être supérieur à 0."
            )
        return value

    def validate_price_per_day(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Le prix par jour doit être supérieur à 0."
            )
        return value

    def validate(self, data):
        price_hour = data.get("price_per_hour")
        price_day = data.get("price_per_day")
        if price_hour and price_day and price_day <= price_hour:
            raise serializers.ValidationError(
                {
                    "price_per_day": "Le prix par jour doit être strictement supérieur au prix par heure."
                }
            )
        return data


class SpacePhotoUploadSerializer(serializers.Serializer):
    """Serializer dédié à l'upload de fichiers photos"""

    file = serializers.CharField()  # Accepte string base64 ou fichier
    is_primary = serializers.BooleanField(default=False)

    def validate_file(self, value):
        # Vérifier si c'est une string base64 (pour les requêtes JSON)
        if isinstance(value, str):
            try:
                # Format attendu: "data:image/jpeg;base64,/9j/4AAQ..."
                if not value.startswith("data:image/"):
                    raise serializers.ValidationError(
                        "Format base64 invalide. Utilisez le format 'data:image/jpeg;base64,...'"
                    )

                # Extraire le type MIME et les données
                header, encoded = value.split(",", 1)
                mime_type = header.split(";")[0].split(":")[1]

                allowed_types = ["image/jpeg", "image/png", "image/webp"]
                if mime_type not in allowed_types:
                    raise serializers.ValidationError(
                        "Format non supporté. Utilisez JPEG, PNG ou WebP."
                    )

                # Décoder et vérifier la taille
                try:
                    decoded_data = base64.b64decode(encoded)
                except Exception:
                    raise serializers.ValidationError("Données base64 invalides.")

                max_size = 5 * 1024 * 1024  # 5 Mo
                if len(decoded_data) > max_size:
                    raise serializers.ValidationError(
                        "La photo est trop lourde (maximum 5 Mo)."
                    )

                # Créer un fichier Django
                file_extension = mime_type.split("/")[1]
                if file_extension == "jpeg":
                    file_extension = "jpg"

                filename = f"upload_{uuid.uuid4()}.{file_extension}"
                file_obj = ContentFile(decoded_data, name=filename)
                file_obj.content_type = mime_type

                return file_obj

            except ValueError:
                raise serializers.ValidationError("Format base64 invalide.")
        else:
            # C'est un fichier uploadé (multipart)
            max_size = 5 * 1024 * 1024  # 5 Mo
            if value.size > max_size:
                raise serializers.ValidationError(
                    "La photo est trop lourde (maximum 5 Mo)."
                )

            allowed_types = ["image/jpeg", "image/png", "image/webp"]
            if value.content_type not in allowed_types:
                raise serializers.ValidationError(
                    "Format non supporté. Utilisez JPEG, PNG ou WebP."
                )
            return value


# serializers.py


class SpaceMinimalSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()
    photos = SpacePhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Space
        fields = ["id", "name", "photo", "photos"]

    def get_photo(self, obj):
        """Logique pour extraire la photo principale ou la première disponible"""
        photo_obj = obj.photos.filter(is_primary=True).first() or obj.photos.first()
        if photo_obj and photo_obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(photo_obj.file.url)
            return photo_obj.file.url
        return None
