from django.db import models
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFit


class Amenity(models.Model):
    """Équipements disponibles dans un espace (WiFi, projecteur, etc.)"""

    name = models.CharField(max_length=100, verbose_name="nom")
    icon = models.CharField(max_length=50, blank=True, verbose_name="icône")

    class Meta:
        verbose_name = "Équipement"
        verbose_name_plural = "Équipements"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Space(models.Model):
    """Espace de coworking ou salle de réunion"""

    class SpaceType(models.TextChoices):
        DESK = "desk", "Bureau individuel"
        OPEN_SPACE = "open_space", "Espace ouvert"
        MEETING = "meeting_room", "Salle de réunion"
        PRIVATE = "private", "Bureau privé"
        CONFERENCE = "conference", "Salle de conférence"

    name = models.CharField(max_length=200, unique=True, verbose_name="nom")
    space_type = models.CharField(
        max_length=20, choices=SpaceType.choices, verbose_name="type d'espace"
    )
    description = models.TextField(blank=True, verbose_name="description")
    capacity = models.PositiveIntegerField(
        default=1, verbose_name="capacité (personnes)"
    )
    price_per_hour = models.DecimalField(
        max_digits=8, decimal_places=2, verbose_name="prix par heure (FCFA)"
    )
    price_per_day = models.DecimalField(
        max_digits=8, decimal_places=2, verbose_name="prix par jour (FCFA)"
    )
    address = models.CharField(max_length=300, blank=True, verbose_name="adresse")
    is_available = models.BooleanField(default=True, verbose_name="disponible")
    amenities = models.ManyToManyField(
        Amenity, blank=True, related_name="spaces", verbose_name="équipements"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="modifié le")

    class Meta:
        verbose_name = "Espace"
        verbose_name_plural = "Espaces"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_space_type_display()})"


class SpacePhoto(models.Model):
    """Photos d'un espace"""

    space = models.ForeignKey(
        Space, on_delete=models.CASCADE, related_name="photos", verbose_name="espace"
    )
    file = ProcessedImageField(
        upload_to="spaces/photos/",
        processors=[ResizeToFit(800, 600)],
        options={"quality": 80},  # Qualité 80% pour un bon ratio poids/qualité
        verbose_name="photo",
    )
    is_primary = models.BooleanField(default=False, verbose_name="photo principale")
    position = models.PositiveIntegerField(default=0, verbose_name="position/ordre")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="uploadée le")

    class Meta:
        verbose_name = "Photo"
        verbose_name_plural = "Photos"
        ordering = ["-is_primary", "position", "-uploaded_at"]

    def __str__(self):
        return f"Photo {self.position} de {self.space.name}"
