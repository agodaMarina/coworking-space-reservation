# Coworking Reservation API Documentation

## Vue d'ensemble

Cette API REST permet de gérer un système de réservation d'espaces de coworking. Elle fournit des fonctionnalités complètes pour la gestion des utilisateurs, des espaces, des réservations, des paiements et des notifications.

**Version de l'API:** 1.0.0
**Framework:** Django REST Framework
**Authentification:** JWT (JSON Web Tokens)
**Documentation automatique:** Disponible via Swagger UI et ReDoc

## Authentification

### JWT Authentication

L'API utilise l'authentification JWT avec des tokens d'accès et de rafraîchissement.

- **Type d'en-tête:** `Bearer`
- **Durée du token d'accès:** 60 minutes (production), 24 heures (développement)
- **Durée du token de rafraîchissement:** 7 jours (production), 30 jours (développement)
- **Rotation des tokens:** Activée
- **Blacklist:** Activée

### Limitation de taux (Rate Limiting)

- **Utilisateurs anonymes:** 100 requêtes/jour
- **Utilisateurs authentifiés:** 1000 requêtes/jour

### Permissions personnalisées

- `IsAdminUser`: Réservé aux administrateurs
- `IsManagerOrAdmin`: Réservé aux managers et administrateurs
- `IsOwnerOrAdmin`: Propriétaire de l'objet ou administrateur
- `IsVerifiedUser`: Utilisateurs vérifiés uniquement

## Endpoints API

### Base URL
```
https://api.coworking.com/api/
```

---

## 1. Authentification (`/auth/`)

### Inscription d'un utilisateur

**Endpoint:** `POST /api/auth/register/`
**Permissions:** Aucune (public)

**Corps de la requête:**
```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+22890123456",
  "password": "securepassword123",
  "password_confirm": "securepassword123"
}
```

**Réponse de succès (201):**
```json
{
  "message": "Compte créé avec succès.",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "johndoe",
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "phone": "+22890123456",
    "avatar": null,
    "role": "client",
    "is_verified": false,
    "created_at": "2024-01-15T10:30:00Z"
  },
  "tokens": {
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  }
}
```

**Erreurs possibles:**
- `400`: Données invalides (email déjà utilisé, mot de passe faible, etc.)

---

### Connexion

**Endpoint:** `POST /api/auth/login/`
**Permissions:** Aucune

**Corps de la requête:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Réponse de succès (200):**
```json
{
  "message": "Connexion réussie.",
  "user": {...},
  "tokens": {...}
}
```

---

### Rafraîchissement du token

**Endpoint:** `POST /api/auth/token/refresh/`
**Permissions:** Aucune

**Corps de la requête:**
```json
{
  "refresh": "refresh_token_here"
}
```

**Réponse (200):**
```json
{
  "access": "new_access_token",
  "refresh": "new_refresh_token"
}
```

---

### Déconnexion

**Endpoint:** `POST /api/auth/logout/`
**Permissions:** Authentifié

**Corps de la requête:**
```json
{
  "refresh": "refresh_token_to_blacklist"
}
```

---

### Profil utilisateur

**Endpoint:** `GET /api/auth/profile/`
**Permissions:** Authentifié

**Réponse (200):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "johndoe",
  "first_name": "John",
  "last_name": "Doe",
  "full_name": "John Doe",
  "phone": "+22890123456",
  "avatar": "https://api.coworking.com/media/avatars/user_1.jpg",
  "role": "client",
  "is_verified": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Modification:** `PUT/PATCH /api/auth/profile/`

---

### Changement de mot de passe

**Endpoint:** `POST /api/auth/change-password/`
**Permissions:** Authentifié

**Corps de la requête:**
```json
{
  "old_password": "currentpassword",
  "new_password": "newsecurepassword123",
  "new_password_confirm": "newsecurepassword123"
}
```

---

## 2. Gestion des espaces (`/spaces/`)

### Types d'espaces
- `desk`: Bureau individuel
- `open_space`: Espace ouvert
- `meeting_room`: Salle de réunion
- `private`: Bureau privé
- `conference`: Salle de conférence

### Équipements (Amenities)
- WiFi, Projecteur, Tableau blanc, etc.

---

### Liste des espaces

**Endpoint:** `GET /api/spaces/`
**Permissions:** Aucune

**Paramètres de requête:**
- `space_type`: Filtrer par type
- `is_available`: true/false
- `capacity`: Capacité minimum
- `search`: Recherche textuelle (nom, description, adresse)
- `ordering`: Tri (price_per_hour, price_per_day, capacity, name)

**Exemple:** `GET /api/spaces/?space_type=meeting_room&is_available=true&capacity=5`

---

### Détail d'un espace

**Endpoint:** `GET /api/spaces/{id}/`
**Permissions:** Aucune

**Réponse (200):**
```json
{
  "id": 1,
  "name": "Salle Innovation",
  "space_type": "meeting_room",
  "space_type_display": "Salle de réunion",
  "description": "Salle moderne avec équipement audiovisuel",
  "capacity": 10,
  "price_per_hour": "5000.00",
  "price_per_day": "30000.00",
  "address": "Lomé, Togo",
  "is_available": true,
  "photo": "https://api.coworking.com/media/spaces/photos/room_1_primary.jpg",
  "photos": [
    {
      "id": 1,
      "url": "https://api.coworking.com/media/spaces/photos/room_1_primary.jpg",
      "is_primary": true,
      "uploaded_at": "2024-01-15T10:30:00Z"
    }
  ],
  "amenities": [
    {"id": 1, "name": "WiFi", "icon": "wifi"},
    {"id": 2, "name": "Projecteur", "icon": "projector"}
  ],
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### Créer un espace

**Endpoint:** `POST /api/spaces/create/`
**Permissions:** Administrateur

**Corps de la requête:**
```json
{
  "name": "Salle Innovation",
  "space_type": "meeting_room",
  "description": "Salle moderne",
  "capacity": 10,
  "price_per_hour": "5000.00",
  "price_per_day": "30000.00",
  "address": "Lomé, Togo",
  "is_available": true,
  "amenities": [1, 2]
}
```

---

### Modifier un espace

**Endpoint:** `PUT/PATCH /api/spaces/{id}/update/`
**Permissions:** Administrateur

---

### Supprimer un espace

**Endpoint:** `DELETE /api/spaces/{id}/delete/`
**Permissions:** Administrateur

---

### Vérifier disponibilité

**Endpoint:** `GET /api/spaces/{id}/availability/?start_datetime=2024-01-20T10:00:00Z&end_datetime=2024-01-20T12:00:00Z&billing_type=hourly`
**Permissions:** Aucune

**Paramètres:**

- `start_datetime`: Date/heure début (ISO 8601)
- `end_datetime`: Date/heure fin (ISO 8601)
- `billing_type`: "hourly" ou "daily"

**Réponse:**

```json
{
  "space_id": 1,
  "space_name": "Salle Innovation",
  "is_available": true,
  "message": "L'espace est disponible pour cette période.",
  "estimated_price": "10000.00",
  "billing_type": "hourly"
}
```

---

### Upload de photo

**Endpoint:** `POST /api/spaces/{id}/photos/`
**Permissions:** Authentifié
**Content-Type:** `multipart/form-data`

**Corps:**
```
file: [fichier image]
is_primary: true/false
```

**Contraintes:**
- Taille max: 5 Mo
- Formats: JPEG, PNG, WebP

---

## 3. Réservations (`/reservations/`)

### Statuts de réservation
- `pending`: En attente
- `confirmed`: Confirmée
- `cancelled`: Annulée
- `completed`: Terminée
- `rejected`: Rejetée

### Types de facturation
- `hourly`: Par heure
- `daily`: Par jour

---

### Créer une réservation

**Endpoint:** `POST /api/reservations/create/`
**Permissions:** Authentifié

**Corps de la requête:**
```json
{
  "space": 1,
  "start_datetime": "2024-01-20T10:00:00Z",
  "end_datetime": "2024-01-20T12:00:00Z",
  "billing_type": "hourly",
  "notes": "Réunion d'équipe"
}
```

---

### Liste des réservations

**Endpoint:** `GET /api/reservations/`
**Permissions:** Authentifié

Retourne les réservations de l'utilisateur connecté (ou toutes pour admin).

---

### Détail d'une réservation

**Endpoint:** `GET /api/reservations/{id}/`
**Permissions:** Propriétaire ou admin

---

### Annuler une réservation

**Endpoint:** `POST /api/reservations/{id}/cancel/`
**Permissions:** Propriétaire ou admin

---

### Modifier une réservation

**Endpoint:** `PUT/PATCH /api/reservations/{id}/update/`
**Permissions:** Propriétaire ou admin

---

## 4. Paiements (`/payments/`)

### Statuts de paiement

- `pending`: En attente
- `completed`: Terminé
- `failed`: Échoué
- `refunded`: Remboursé

### Méthodes de paiement

- `stripe`: Stripe
- `cash`: Espèces
- `bank_transfer`: Virement bancaire

---

### Créer un paiement

**Endpoint:** `POST /api/payments/create/`
**Permissions:** Authentifié

**Corps:**

```json
{
  "reservation": 1,
  "amount": "10000.00",
  "method": "stripe"
}
```

---

### Confirmer un paiement

**Endpoint:** `POST /api/payments/{id}/confirm/`
**Permissions:** Authentifié

---

### Remboursement

**Endpoint:** `POST /api/payments/{id}/refund/`
**Permissions:** Administrateur

---

### Télécharger facture

**Endpoint:** `GET /api/payments/{id}/invoice/`
**Permissions:** Propriétaire du paiement

---

## 5. Notifications (`/notifications/`)

### Types de notifications
- `reservation_confirmed`: Réservation confirmée
- `reservation_cancelled`: Réservation annulée
- `payment_received`: Paiement reçu
- `space_unavailable`: Espace indisponible

---

### Liste des notifications

**Endpoint:** `GET /api/notifications/`
**Permissions:** Authentifié

---

### Marquer comme lu

**Endpoint:** `PUT /api/notifications/read/`
**Permissions:** Authentifié

Marque toutes les notifications comme lues.

---

### Marquer une notification comme lue

**Endpoint:** `PUT /api/notifications/{id}/read/`
**Permissions:** Propriétaire

---

## Administration

### Dashboard

**Endpoint:** `GET /api/admin/dashboard/`
**Permissions:** Administrateur

Retourne des statistiques générales.

### Export des réservations

**Endpoint:** `GET /api/admin/export/reservations/`
**Permissions:** Administrateur

Télécharge un fichier CSV des réservations.

### Gestion des utilisateurs

**Endpoint:** `GET /api/auth/admin/users/`
**Permissions:** Administrateur

**Modifier un utilisateur:** `PATCH /api/auth/admin/users/{id}/`

---

## Gestion des erreurs

### Codes d'erreur HTTP courants

- `400 Bad Request`: Données invalides
- `401 Unauthorized`: Non authentifié
- `403 Forbidden`: Permissions insuffisantes
- `404 Not Found`: Ressource introuvable
- `429 Too Many Requests`: Limite de taux dépassée
- `500 Internal Server Error`: Erreur serveur

### Structure des erreurs

```json
{
  "error": "Description de l'erreur",
  "field": "nom_du_champ" // optionnel
}
```

Ou pour les erreurs de validation:

```json
{
  "field_name": ["Erreur 1", "Erreur 2"]
}
```

---

## Pagination

L'API utilise la pagination par numéro de page.

**Paramètres:**
- `page`: Numéro de page (défaut: 1)
- `page_size`: Éléments par page (défaut: 20, max: 100)

**Réponse paginée:**
```json
{
  "count": 150,
  "next": "https://api.coworking.com/api/spaces/?page=2",
  "previous": null,
  "results": [...]
}
```

---

## Filtres et recherche

### Filtres disponibles

La plupart des endpoints de liste supportent:

- **Filtrage:** `?field=value`
- **Recherche:** `?search=query`
- **Tri:** `?ordering=field` (ou `-field` pour décroissant)

### Exemples

```
GET /api/spaces/?space_type=meeting_room&is_available=true
GET /api/spaces/?search=innovation
GET /api/spaces/?ordering=-price_per_hour
```

---

## Bonnes pratiques

### 1. Gestion des tokens

- Stockez le refresh token de manière sécurisée
- Rafraîchissez le token d'accès avant expiration
- Implémentez une logique de retry automatique

### 2. Gestion des erreurs

- Vérifiez toujours le code de statut HTTP
- Gérez les erreurs 401 en redirigeant vers la connexion
- Affichez des messages d'erreur user-friendly

### 3. Optimisation des performances

- Utilisez la pagination pour les listes importantes
- Cachez les données statiques (types d'espaces, équipements)
- Limitez les appels API fréquents

### 4. Sécurité

- Validez toujours les données côté client
- N'exposez pas les tokens dans les logs
- Utilisez HTTPS en production

---

## Exemples de code

### JavaScript (Fetch API)

```javascript
// Connexion
const login = async (email, password) => {
  const response = await fetch('/api/auth/login/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password })
  });

  const data = await response.json();
  if (response.ok) {
    localStorage.setItem('access_token', data.tokens.access);
    localStorage.setItem('refresh_token', data.tokens.refresh);
  }
  return data;
};

// Requête authentifiée
const getSpaces = async () => {
  const token = localStorage.getItem('access_token');
  const response = await fetch('/api/spaces/', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};
```

### Python (requests)

```python
import requests

# Configuration
BASE_URL = 'https://api.coworking.com/api'
headers = {'Content-Type': 'application/json'}

# Inscription
user_data = {
  "email": "user@example.com",
  "username": "johndoe",
  "first_name": "John",
  "last_name": "Doe",
  "password": "securepassword123",
  "password_confirm": "securepassword123"
}

response = requests.post(f'{BASE_URL}/auth/register/', json=user_data)
tokens = response.json()['tokens']

# Utilisation du token
headers['Authorization'] = f"Bearer {tokens['access']}"

# Récupération des espaces
spaces = requests.get(f'{BASE_URL}/spaces/', headers=headers).json()
```

---

## Schéma OpenAPI

La documentation complète OpenAPI est disponible aux endpoints suivants:

- **Swagger UI:** `/api/docs/`
- **ReDoc:** `/api/redoc/`
- **Schéma brut:** `/api/schema/`

Ces interfaces permettent de tester directement les endpoints et de voir tous les détails des paramètres, réponses et erreurs.

---

## Versions et changements

### Version 1.0.0 (actuelle)

- Implémentation complète de l'API de réservation
- Authentification JWT
- Gestion des espaces, réservations, paiements
- Système de notifications
- Interface d'administration

### Évolutions futures

- Support des réservations récurrentes
- Intégration calendrier externe
- API mobile optimisée
- Webhooks pour événements externes

---

## Support

Pour toute question concernant l'API:

- **Documentation interactive:** `/api/docs/`
- **Issues GitHub:** [lien vers le repo]
- **Email support:** support@coworking.com

Cette documentation est automatiquement générée et mise à jour avec le code source.
