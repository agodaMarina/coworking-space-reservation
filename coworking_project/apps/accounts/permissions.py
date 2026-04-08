from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """Permission réservée aux administrateurs"""

    message = 'Accès réservé aux administrateurs.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_admin
        )


class IsManagerOrAdmin(BasePermission):
    """Permission réservée aux managers et administrateurs"""
    message = 'Accès réservé aux managers et administrateurs.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.role in ['manager', 'admin'] or request.user.is_superuser)
        )


class IsOwnerOrAdmin(BasePermission):
    """Permission réservée au propriétaire de l'objet ou à un admin"""

    message = 'Accès réservé au propriétaire ou aux administrateurs.'

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin:
            return True
        return obj.user == request.user


class IsVerifiedUser(BasePermission):
    """Permission réservée aux utilisateurs vérifiés"""

    message = 'Votre compte doit être vérifié pour effectuer cette action.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_verified
        )