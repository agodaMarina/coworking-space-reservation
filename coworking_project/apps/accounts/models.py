from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Modèle utilisateur personnalisé.
    On utilise l'email comme identifiant principal
    à la place du username.
    """

    class Role(models.TextChoices):
        CLIENT = 'client', 'Client'
        ADMIN  = 'admin',  'Administrateur'
        MANAGER = 'manager', 'Manager'

    email = models.EmailField(
        unique=True,
        verbose_name='adresse email'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='téléphone'
    )
    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        verbose_name='photo de profil'
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.CLIENT,
        verbose_name='rôle'
    )
    is_verified = models.BooleanField(
        default=False,
        verbose_name='compte vérifié'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='créé le'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='modifié le'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    @property
    def full_name(self):
        """Retourne le nom complet de l'utilisateur"""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_admin(self):
        """Vérifie si l'utilisateur est administrateur"""
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_manager(self):
        """Vérifie si l'utilisateur est manager"""
        return self.role == self.Role.MANAGER