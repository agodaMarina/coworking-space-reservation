from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    ProfileView,
    ChangePasswordView,
    UserListView,
)
from .admin_views import AdminUserListView, AdminUserUpdateView, AdminCreateUserView, AdminDeleteUserView

app_name = 'accounts'

urlpatterns = [
    # Inscription & Connexion
    path('register/', RegisterView.as_view(),  name='register'),
    path('login/',    LoginView.as_view(),     name='login'),
    path('logout/',   LogoutView.as_view(),    name='logout'),

    # Refresh token JWT
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # Profil
    path('profile/',         ProfileView.as_view(),        name='profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),

    # Liste utilisateurs (admin)
    path('users/', UserListView.as_view(), name='user-list'),

    # Admin users
    path('admin/users/',          AdminUserListView.as_view(),       name='admin-user-list'),
    path('admin/users/create/',   AdminCreateUserView.as_view(),     name='admin-user-create'),
    path('admin/users/<int:pk>/', AdminUserUpdateView.as_view(),     name='admin-user-update'),
    path('admin/users/<int:pk>/delete/', AdminDeleteUserView.as_view(), name='admin-user-delete'),
]