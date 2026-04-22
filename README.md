# Coworking Space Reservation — API

API REST Django pour la gestion d'un espace de coworking à Lomé (Togo).  
Authentification JWT · Paiements Stripe + Mobile Money · Notifications email (Celery)

---

## Stack

| Couche | Technologie |
|--------|-------------|
| Framework | Django 5.0 + Django REST Framework |
| Base de données | PostgreSQL |
| Auth | SimpleJWT (access + refresh token) |
| Paiements | Stripe + local (Mobile Money, espèces, virement) |
| Asynchrone | Celery + Redis |
| Documentation | DRF Spectacular (Swagger / ReDoc) |

---

## Installation

```bash
# 1. Cloner et activer l'environnement
git clone <url-du-repository>
cd coworking-space-reservation
python3 -m venv env && source env/bin/activate
pip install -r requirements/development.txt

# 2. Variables d'environnement
cp .env.example .env   # puis remplir les valeurs

# 3. Base de données (Docker recommandé)
docker run --name cowork-pg -e POSTGRES_DB=coworking_db \
  -e POSTGRES_USER=keycloak -e POSTGRES_PASSWORD=keycloak \
  -p 5432:5432 -d postgres:16-alpine

python manage.py migrate --settings=config.settings.development
python manage.py createsuperuser --settings=config.settings.development

# 4. Lancer les services
python manage.py runserver --settings=config.settings.development
celery -A config worker --loglevel=info          # tâches async (emails)
celery -A config beat --loglevel=info            # tâches planifiées
stripe listen --forward-to localhost:8000/api/payments/webhook/  # webhook local
```

**Accès documentation interactive :**
- Swagger : `http://localhost:8000/api/docs/`
- ReDoc   : `http://localhost:8000/api/redoc/`

**Carte Stripe de test :** `4242 4242 4242 4242` — 12/34 — 123

---

## Variables d'environnement

```env
SECRET_KEY=...
DEBUG=True
ALLOWED_HOSTS=*

DB_NAME=coworking_db
DB_USER=keycloak
DB_PASSWORD=keycloak
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://localhost:6379/0

STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=noreply@coworking.com

CORS_ALLOWED_ORIGINS=http://localhost:4200
```

---

## Rôles et authentification

Toutes les requêtes protégées nécessitent :
```
Authorization: Bearer <access_token>
```

| Rôle | Accès |
|------|-------|
| **Public** | Lecture seule sur les espaces, sans token |
| **Client** (`role=client`) | Réservations, paiements, profil |
| **Admin** (`role=admin`) | Gestion complète |

---

## Endpoints — Public (sans token)

### Espaces

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/spaces/` | Liste tous les espaces |
| `GET` | `/api/spaces/<id>/` | Détail d'un espace |
| `GET` | `/api/spaces/available/` | Espaces disponibles uniquement (`is_available=True`) |
| `GET` | `/api/spaces/<id>/availability/` | Vérifie disponibilité + calcule le prix estimé |
| `GET` | `/api/spaces/amenities/` | Liste des équipements |

**Disponibilité espace (GET) :**
```
GET /api/spaces/3/availability/?start_datetime=2025-06-10T09:00:00&end_datetime=2025-06-10T17:00:00&billing_type=hourly
```

**Filtres — liste espaces :**
```
?space_type=meeting_room&is_available=true&capacity=10
?search=wifi&ordering=price_per_hour
```

Types d'espaces : `individual_office` · `open_space` · `meeting_room` · `private_office` · `conference_room`

---

## Endpoints — Client

### Authentification

| Méthode | URL | Description |
|---------|-----|-------------|
| `POST` | `/api/auth/register/` | Créer un compte |
| `POST` | `/api/auth/login/` | Connexion — retourne `access` + `refresh` |
| `POST` | `/api/auth/logout/` | Déconnexion (blacklist du refresh token) |
| `POST` | `/api/auth/token/refresh/` | Renouveler le token d'accès |
| `GET` | `/api/auth/profile/` | Voir son profil |
| `PATCH` | `/api/auth/profile/` | Modifier son profil |
| `POST` | `/api/auth/change-password/` | Changer son mot de passe |

**Inscription :**
```json
POST /api/auth/register/
{
  "email": "user@example.com",
  "username": "john_doe",
  "first_name": "John",
  "last_name": "Doe",
  "password": "motdepasse123",
  "password_confirm": "motdepasse123",
  "phone": "+228 90 00 00 00"
}
```

**Connexion :**
```json
POST /api/auth/login/
{
  "email": "user@example.com",
  "password": "motdepasse123"
}
```

---

### Réservations

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/reservations/` | Mes réservations |
| `POST` | `/api/reservations/create/` | Créer une réservation |
| `GET` | `/api/reservations/<id>/` | Détail d'une réservation |
| `POST` | `/api/reservations/<id>/cancel/` | Annuler (minimum 24h avant le début) |
| `POST` | `/api/reservations/availability/<space_id>/` | Vérifier disponibilité via POST |

**Créer une réservation :**
```json
POST /api/reservations/create/
{
  "space_id": 3,
  "start_datetime": "2025-06-10T09:00:00",
  "end_datetime": "2025-06-10T17:00:00",
  "billing_type": "hourly",
  "notes": "Besoin d'un vidéoprojecteur",
  "is_recurring": false,
  "recurrence_rule": "none"
}
```

`billing_type` : `hourly` (par heure) · `daily` (par jour, arrondi au jour supérieur)  
`recurrence_rule` : `none` · `daily` · `weekly` · `monthly`

**Statuts et transitions :**
```
pending   → confirmed  (admin)
pending   → rejected   (admin)
pending   → cancelled  (client 24h+ avant / admin)
confirmed → cancelled  (client 24h+ avant / admin)
confirmed → completed  (automatique via Celery Beat, toutes les heures)
```

**Filtres :**
```
GET /api/reservations/?status=confirmed&billing_type=hourly&ordering=-created_at
```

---

### Paiements

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/payments/` | Mes paiements |
| `GET` | `/api/payments/<id>/` | Détail d'un paiement |
| `POST` | `/api/payments/create/` | Créer un paiement pour une réservation |
| `POST` | `/api/payments/<id>/stripe-confirm/` | Confirmer un paiement Stripe après validation frontend |
| `GET` | `/api/payments/<id>/invoice/` | Télécharger la facture (paiement complété uniquement) |

**Paiement par carte (Stripe) :**
```json
POST /api/payments/create/
{
  "reservation_id": 12,
  "method": "card"
}
```
→ Retourne `client_secret` pour Stripe.js. Ensuite appeler `stripe-confirm/` :
```
POST /api/payments/12/stripe-confirm/
```

**Flux complet Stripe :**
```
1. POST /api/payments/create/              → reçoit client_secret
2. stripe.confirmCardPayment(client_secret) → côté frontend
3. POST /api/payments/<id>/stripe-confirm/  → confirmation serveur + email envoyé
```

**Paiement local :**
```json
POST /api/payments/create/
{
  "reservation_id": 12,
  "method": "mobile_money"
}
```
→ Statut `pending` jusqu'à validation manuelle par un admin.

Méthodes : `card` · `mobile_money` · `cash` · `bank_transfer`

---

### Notifications

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/notifications/` | Mes notifications |
| `GET` | `/api/notifications/stats/` | Compteur non lues |
| `POST` | `/api/notifications/read/` | Marquer toutes comme lues |
| `PATCH` | `/api/notifications/<id>/read/` | Marquer une notification comme lue |

---

## Endpoints — Admin

### Gestion des utilisateurs

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/auth/admin/users/` | Liste tous les utilisateurs |
| `POST` | `/api/auth/admin/users/create/` | Créer un utilisateur avec rôle choisi |
| `PATCH` | `/api/auth/admin/users/<id>/` | Modifier `is_active`, `role`, `is_verified` |
| `DELETE` | `/api/auth/admin/users/<id>/delete/` | Supprimer un utilisateur |

**Créer un utilisateur :**
```json
POST /api/auth/admin/users/create/
{
  "email": "manager@cowork.com",
  "username": "manager1",
  "first_name": "Alice",
  "last_name": "Martin",
  "phone": "+228 91 00 00 00",
  "role": "manager",
  "password": "motdepasse123",
  "password_confirm": "motdepasse123"
}
```

Rôles : `client` · `manager` · `admin`  
Les utilisateurs créés par un admin sont marqués `is_verified=True` automatiquement.

---

### Gestion des espaces

| Méthode | URL | Description |
|---------|-----|-------------|
| `POST` | `/api/spaces/create/` | Créer un espace |
| `PUT / PATCH` | `/api/spaces/<id>/update/` | Modifier un espace |
| `DELETE` | `/api/spaces/<id>/delete/` | Supprimer un espace |
| `POST` | `/api/spaces/<id>/photos/` | Uploader une photo (multipart ou base64) |
| `DELETE` | `/api/spaces/<id>/photos/<photo_id>/delete/` | Supprimer une photo |
| `POST` | `/api/spaces/amenities/create/` | Créer un équipement |

**Créer un espace :**
```json
POST /api/spaces/create/
{
  "name": "Salle Harmattan",
  "space_type": "meeting_room",
  "description": "Salle climatisée, 10 places, vidéoprojecteur",
  "capacity": 10,
  "price_per_hour": 5000,
  "price_per_day": 30000,
  "address": "Lomé, Quartier Administratif",
  "is_available": true,
  "amenity_ids": [1, 2, 3]
}
```

**Uploader une photo (multipart) :**
```
POST /api/spaces/3/photos/
Content-Type: multipart/form-data

file=<image.jpg>
is_primary=true
```

**Uploader une photo (base64) :**
```json
{
  "file": "data:image/jpeg;base64,/9j/4AAQ...",
  "is_primary": false
}
```

---

### Gestion des réservations

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/reservations/` | Liste **toutes** les réservations (tous clients) |
| `GET` | `/api/reservations/<id>/` | Détail d'une réservation |
| `PATCH` | `/api/reservations/<id>/update/` | Modifier le statut ou les notes |
| `POST` | `/api/reservations/<id>/cancel/` | Annuler sans contrainte de délai |

**Modifier le statut :**
```json
PATCH /api/reservations/12/update/
{
  "status": "confirmed"
}
```

Transitions autorisées :

| Statut actuel | Vers |
|---------------|------|
| `pending` | `confirmed`, `rejected`, `cancelled` |
| `confirmed` | `cancelled`, `completed` |
| `cancelled` / `completed` / `rejected` | aucune transition possible |

---

### Gestion des paiements

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/payments/` | Liste **tous** les paiements |
| `PATCH` | `/api/payments/<id>/confirm/` | Valider ou rejeter un paiement local |
| `POST` | `/api/payments/<id>/refund/` | Rembourser (partiel ou total) |
| `GET` | `/api/payments/stats/` | Statistiques revenus par méthode |

**Confirmer un paiement local :**
```json
PATCH /api/payments/7/confirm/
{
  "status": "completed"
}
```
Valeurs possibles : `completed` · `failed` · `refunded`

**Remboursement partiel :**
```json
POST /api/payments/7/refund/
{
  "amount": "5000.00",
  "reason": "Annulation anticipée"
}
```
Omettre `amount` pour un remboursement total.

---

### Tableau de bord & Export

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/admin/dashboard/` | KPIs sur une période |
| `GET` | `/api/admin/export/reservations/` | Export CSV de toutes les réservations |

**Dashboard :**
```
GET /api/admin/dashboard/?date_from=2025-01-01&date_to=2025-06-30
```

Retourne : total réservations, confirmées, annulées, terminées, revenus, taux d'occupation, réservations du jour.

---

### Notifications (admin)

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/api/notifications/all/` | Toutes les notifications de tous les utilisateurs |

---

## Récapitulatif des permissions

| Action | Public | Client | Admin |
|--------|--------|--------|-------|
| Lire les espaces | ✅ | ✅ | ✅ |
| Vérifier disponibilité | ✅ | ✅ | ✅ |
| S'inscrire / se connecter | ✅ | ✅ | ✅ |
| Voir / modifier son profil | — | ✅ | ✅ |
| Créer / modifier / supprimer un espace | — | — | ✅ |
| Uploader des photos | — | — | ✅ |
| Créer une réservation | — | ✅ | ✅ |
| Voir ses réservations | — | ✅ | ✅ |
| Voir toutes les réservations | — | — | ✅ |
| Modifier le statut d'une réservation | — | — | ✅ |
| Annuler une réservation | — | ✅ (24h min) | ✅ |
| Créer un paiement | — | ✅ | ✅ |
| Confirmer paiement local | — | — | ✅ |
| Rembourser | — | — | ✅ |
| Gérer les utilisateurs | — | — | ✅ |
| Dashboard / Export CSV | — | — | ✅ |

---

## Codes de réponse

| Code | Signification |
|------|--------------|
| `200` | Succès |
| `201` | Ressource créée |
| `204` | Suppression réussie |
| `400` | Données invalides ou règle métier non respectée |
| `401` | Token manquant ou expiré |
| `403` | Permission insuffisante |
| `404` | Ressource introuvable |

---

## Structure du projet

```
coworking-space-reservation/
├── apps/
│   ├── accounts/        # Auth JWT, profil, rôles
│   ├── spaces/          # Espaces, photos, équipements
│   ├── reservations/    # Réservations, disponibilité, dashboard
│   ├── payments/        # Stripe, paiements locaux, factures
│   └── notifications/   # Emails async, rappels, tâches Celery
├── services/
│   ├── availability.py       # Vérification chevauchements + calcul prix
│   └── reservation_logic.py  # Création + annulation réservations
├── config/
│   ├── settings/        # dev / prod
│   ├── urls.py
│   └── celery.py        # Beat schedule (COMPLETED toutes les heures, rappels 8h)
└── templates/emails/    # Templates HTML emails
```

---

## Notes de production

- Passer `CORS_ALLOW_ALL_ORIGINS = False` et renseigner `CORS_ALLOWED_ORIGINS`
- Utiliser les clés Stripe de **production** (`sk_live_...`)
- Configurer Nginx + Gunicorn + HTTPS
- Ajouter un handler de logs fichier ou Sentry (`logging` actuellement console uniquement)
