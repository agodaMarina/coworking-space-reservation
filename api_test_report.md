# 📊 Rapport de Tests — Coworking API

> Généré le **20/04/2026 à 10:49:02**
> Durée totale : **7.5s**  |  Cible : `http://localhost:8000`

## 📈 Résumé global

| Indicateur | Valeur |
|---|---|
| Tests exécutés | **86** |
| ✅ Réussis | **72** |
| ❌ Échoués | **14** |
| 💥 Erreurs réseau/connexion | **0** |
| ⚠️  Avertissements (auth inattendue) | **1** |
| 🎯 Taux de réussite | **83.7%** |
| ⏱️  Temps moyen de réponse | **86.7ms** |

```
Progression  [████████████████░░░░] 83.7%
```

## 📂 Résultats par catégorie

### 🏗️ Infra — 1/3 (33%)

| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |
|---|---------|----------|-------------|---------|------|-------|------|--------|
| 1 | `GET` | `/api/docs/` | Swagger UI accessible | `200` | `406` | 15ms | none | ❌ |
| 2 | `GET` | `/api/schema/` | Schéma OpenAPI (JSON) | `200` | `200` | 392ms | none | ✅ |
| 3 | `GET` | `/api/redoc/` | ReDoc accessible | `200` | `406` | 46ms | none | ❌ |

### 🔐 Auth — 19/21 (90%)

| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |
|---|---------|----------|-------------|---------|------|-------|------|--------|
| 1 | `POST` | `/api/auth/register/` | Inscription nouvel utilisateur | `201` | `201` | 319ms | none | ✅ |
| 2 | `POST` | `/api/auth/register/` | Inscription — email manquant | `400` | `400` | 72ms | none | ✅ |
| 3 | `POST` | `/api/auth/register/` | Inscription — mots de passe différents | `400` | `400` | 72ms | none | ✅ |
| 4 | `POST` | `/api/auth/login/` | Connexion admin | `200` | `200` | 332ms | none | ✅ |
| 5 | `POST` | `/api/auth/login/` | Connexion — mauvais mot de passe | `401` | `400` | 337ms | none | ❌ |
| 6 | `POST` | `/api/auth/login/` | Connexion — email inexistant | `401` | `400` | 324ms | none | ❌ |
| 7 | `POST` | `/api/auth/login/` | Re-login pour refresh token | `200` | `200` | 284ms | none | ✅ |
| 8 | `POST` | `/api/auth/token/refresh/` | Rafraîchissement token — valide | `200` | `200` | 79ms | none | ✅ |
| 9 | `POST` | `/api/auth/token/refresh/` | Rafraîchissement token — invalide | `401` | `401` | 45ms | none | ✅ |
| 10 | `GET` | `/api/auth/profile/` | Profil — authentifié (admin) | `200` | `200` | 65ms | admin | ✅ |
| 11 | `GET` | `/api/auth/profile/` | Profil — non authentifié | `401` | `401` | 46ms | none | ✅ |
| 12 | `PATCH` | `/api/auth/profile/` | Modifier profil (PATCH) | `200` | `200` | 68ms | admin | ✅ |
| 13 | `POST` | `/api/auth/change-password/` | Changement MDP — non authentifié | `401` | `401` | 45ms | none | ✅ |
| 14 | `POST` | `/api/auth/change-password/` | Changement MDP — ancien MDP incorrect | `400` | `400` | 331ms | admin | ✅ |
| 15 | `GET` | `/api/auth/admin/users/` | Liste users — admin | `200` | `200` | 72ms | admin | ✅ |
| 16 | `GET` | `/api/auth/admin/users/` | Liste users — user standard (doit être 403) | `403` | `403` | 60ms | user | ✅ |
| 17 | `GET` | `/api/auth/admin/users/` | Liste users — non authentifié (doit être 401) | `401` | `401` | 45ms | none | ✅ |
| 18 | `PATCH` | `/api/auth/admin/users/6/` | Modifier user via admin | `200` | `200` | 72ms | admin | ✅ |
| 19 | `POST` | `/api/auth/login/` | Login pour test logout | `200` | `200` | 289ms | none | ✅ |
| 20 | `POST` | `/api/auth/logout/` | Déconnexion — valide | `200` | `200` | 75ms | ephemeral | ✅ |
| 21 | `POST` | `/api/auth/logout/` | Déconnexion — non authentifié | `401` | `401` | 46ms | none | ✅ |

### 🏢 Espaces — 13/15 (87%)

| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |
|---|---------|----------|-------------|---------|------|-------|------|--------|
| 1 | `GET` | `/api/spaces/` | Liste espaces — public | `200` | `200` | 99ms | none | ✅ |
| 2 | `GET` | `/api/spaces/` | Filtre par type meeting_room | `200` | `200` | 72ms | none | ✅ |
| 3 | `GET` | `/api/spaces/` | Filtre disponibilité | `200` | `200` | 93ms | none | ✅ |
| 4 | `GET` | `/api/spaces/` | Filtre capacité min 5 | `200` | `200` | 65ms | none | ✅ |
| 5 | `GET` | `/api/spaces/` | Recherche textuelle | `200` | `200` | 76ms | none | ✅ |
| 6 | `GET` | `/api/spaces/` | Tri par prix/heure desc | `200` | `200` | 81ms | none | ✅ |
| 7 | `GET` | `/api/spaces/` | Pagination page 1 | `200` | `200` | 93ms | none | ✅ |
| 8 | `GET` | `/api/spaces/1/` | Détail espace existant | `200` | `200` | 74ms | none | ✅ |
| 9 | `GET` | `/api/spaces/99999/` | Détail espace inexistant | `404` | `404` | 60ms | none | ✅ |
| 10 | `GET` | `/api/spaces/1/availability/` | Vérifier disponibilité — paramètres valides | `200` | `200` | 60ms | none | ✅ |
| 11 | `GET` | `/api/spaces/1/availability/` | Disponibilité — paramètres manquants | `400` | `400` | 64ms | none | ✅ |
| 12 | `POST` | `/api/spaces/create/` | Créer espace — admin | `201` | `415` | 64ms | admin | ❌ |
| 13 | `POST` | `/api/spaces/create/` | Créer espace — user (403) | `403` | `403` | 63ms | user | ✅ |
| 14 | `POST` | `/api/spaces/create/` | Créer espace — non auth (401) | `401` | `401` | 45ms | none | ✅ |
| 15 | `POST` | `/api/spaces/create/` | Créer espace — payload invalide | `400` | `415` | 67ms | admin | ❌ |

### 📅 Réservations — 7/8 (88%)

| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |
|---|---------|----------|-------------|---------|------|-------|------|--------|
| 1 | `GET` | `/api/reservations/` | Liste réservations — non auth (401) | `401` | `401` | 49ms | none | ✅ |
| 2 | `GET` | `/api/reservations/` | Liste réservations — user auth | `200` | `200` | 76ms | user | ✅ |
| 3 | `GET` | `/api/reservations/` | Liste réservations — admin (tout voir) | `200` | `200` | 96ms | admin | ✅ |
| 4 | `POST` | `/api/reservations/create/` | Créer réservation — non auth (401) | `401` | `401` | 45ms | none | ✅ |
| 5 | `POST` | `/api/reservations/create/` | Créer réservation — user auth | `201` | `400` | 61ms | user | ❌ |
| 6 | `POST` | `/api/reservations/create/` | Créer réservation — dates manquantes | `400` | `400` | 61ms | user | ✅ |
| 7 | `POST` | `/api/reservations/create/` | Créer réservation — dates passées | `400` | `400` | 67ms | user | ✅ |
| 8 | `GET` | `/api/reservations/99999/` | Détail réservation inexistante (404) | `404` | `404` | 69ms | user | ✅ |

### 💳 Paiements — 14/15 (93%)

| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |
|---|---------|----------|-------------|---------|------|-------|------|--------|
| 1 | `POST` | `/api/payments/create/` | Créer paiement — non auth (401) | `401` | `401` | 48ms | none | ✅ |
| 2 | `POST` | `/api/payments/create/` | Créer paiement — méthode invalide | `400` | `400` | 74ms | user | ✅ |
| 3 | `POST` | `/api/payments/create/` | Créer paiement — réservation inexistante | `404` | `400` | 65ms | user | ❌ |
| 4 | `GET` | `/api/payments/` | Liste paiements — non auth (401) | `401` | `401` | 45ms | none | ✅ |
| 5 | `GET` | `/api/payments/` | Liste paiements — user | `200` | `200` | 78ms | user | ✅ |
| 6 | `GET` | `/api/payments/` | Liste paiements — admin | `200` | `200` | 88ms | admin | ✅ |
| 7 | `GET` | `/api/payments/` | Filtre paiements par statut | `200` | `200` | 68ms | user | ✅ |
| 8 | `GET` | `/api/payments/` | Filtre paiements par méthode | `200` | `200` | 69ms | user | ✅ |
| 9 | `GET` | `/api/payments/99999/` | Détail paiement inexistant (404) | `404` | `404` | 63ms | user | ✅ |
| 10 | `GET` | `/api/payments/stats/` | Stats paiements — admin | `200` | `200` | 85ms | admin | ✅ |
| 11 | `GET` | `/api/payments/stats/` | Stats paiements — user (403) | `403` | `403` | 63ms | user | ✅ |
| 12 | `GET` | `/api/payments/stats/` | Stats paiements — non auth (401) | `401` | `401` | 46ms | none | ✅ |
| 13 | `POST` | `/api/payments/webhook/` | Webhook Stripe — sans signature (400) | `400` | `400` | 47ms | none | ✅ |
| 14 | `POST` | `/api/payments/webhook/` | Webhook Stripe — signature invalide (400) | `400` | `400` | 44ms | none | ✅ |
| 15 | `GET` | `/api/payments/webhook/` | Webhook — méthode GET (405) | `405` | `405` | 45ms | none | ✅ |

### 🔔 Notifications — 3/5 (60%)

| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |
|---|---------|----------|-------------|---------|------|-------|------|--------|
| 1 | `GET` | `/api/notifications/` | Liste notifications — non auth (401) | `401` | `401` | 45ms | none | ✅ |
| 2 | `GET` | `/api/notifications/` | Liste notifications — user | `200` | `200` | 67ms | user | ✅ |
| 3 | `PUT` | `/api/notifications/read/` | Marquer tout comme lu — user | `200` | `405` | 58ms | user | ❌ |
| 4 | `PUT` | `/api/notifications/read/` | Marquer tout comme lu — non auth (401) | `401` | `401` | 45ms | none | ✅ |
| 5 | `PUT` | `/api/notifications/99999/read/` | Marquer notification inexistante (404) | `404` | `405` | 65ms | user | ❌ |

### 👑 Admin — 6/6 (100%)

| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |
|---|---------|----------|-------------|---------|------|-------|------|--------|
| 1 | `GET` | `/api/admin/dashboard/` | Dashboard — admin | `200` | `200` | 91ms | admin | ✅ |
| 2 | `GET` | `/api/admin/dashboard/` | Dashboard — user (403) | `403` | `403` | 65ms | user | ✅ |
| 3 | `GET` | `/api/admin/dashboard/` | Dashboard — non auth (401) | `401` | `401` | 48ms | none | ✅ |
| 4 | `GET` | `/api/admin/export/reservations/` | Export CSV réservations — admin | `200` | `200` | 71ms | admin | ✅ |
| 5 | `GET` | `/api/admin/export/reservations/` | Export CSV — user (403) | `403` | `403` | 59ms | user | ✅ |
| 6 | `GET` | `/api/admin/export/reservations/` | Export CSV — non auth (401) | `401` | `401` | 45ms | none | ✅ |

### 🛡️ Robustesse — 9/13 (69%)

| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |
|---|---------|----------|-------------|---------|------|-------|------|--------|
| 1 | `DELETE` | `/api/auth/login/` | DELETE sur login (405) | `405` | `405` | 44ms | none | ✅ |
| 2 | `PUT` | `/api/spaces/` | PUT sur liste espaces (405) | `405` | `405` | 63ms | user | ✅ |
| 3 | `PATCH` | `/api/spaces/` | PATCH sur liste espaces (405) | `405` | `405` | 62ms | user | ✅ |
| 4 | `GET` | `/api/auth/profile/` | Profile — token malformé (401) | `401` | `401` | 45ms | none | ✅ |
| 5 | `GET` | `/api/spaces/` | Espaces — token invalide tolère (200 ou 401) | `200` | `401` | 45ms | none | ⚠️ |
| 6 | `POST` | `/api/spaces/create/` | Payload — champs vides | `400` | `415` | 65ms | admin | ❌ |
| 7 | `POST` | `/api/spaces/create/` | Payload — string au lieu d'int pour capacity | `400` | `415` | 68ms | admin | ❌ |
| 8 | `POST` | `/api/auth/register/` | Injection SQL dans email | `400` | `400` | 71ms | none | ✅ |
| 9 | `GET` | `/api/spaces/abc/` | ID non-entier pour space (404) | `404` | `404` | 69ms | none | ✅ |
| 10 | `GET` | `/api/reservations/0/` | ID=0 pour réservation (404) | `404` | `404` | 64ms | user | ✅ |
| 11 | `GET` | `/api/payments/-1/` | ID négatif pour paiement (404) | `404` | `404` | 51ms | user | ✅ |
| 12 | `GET` | `/api/inexistant/` | Route inexistante (404) | `404` | `404` | 50ms | none | ✅ |
| 13 | `GET` | `/api/` | Racine API (200 ou 404) | `200` | `404` | 49ms | none | ❌ |

## 🔍 Détail des échecs et erreurs

### 1. ❌ `GET /api/docs/`

- **Description :** Swagger UI accessible
- **Catégorie :** infra
- **Statut attendu :** `200`
- **Statut reçu :** `406`
- **Temps :** 14.7ms
- **Auth utilisée :** none
- **Réponse :**
```json
{
  "raw": "406 Not Acceptable"
}
```

### 2. ❌ `GET /api/redoc/`

- **Description :** ReDoc accessible
- **Catégorie :** infra
- **Statut attendu :** `200`
- **Statut reçu :** `406`
- **Temps :** 45.9ms
- **Auth utilisée :** none
- **Réponse :**
```json
{
  "raw": "406 Not Acceptable"
}
```

### 3. ❌ `POST /api/auth/login/`

- **Description :** Connexion — mauvais mot de passe
- **Catégorie :** auth
- **Statut attendu :** `401`
- **Statut reçu :** `400`
- **Temps :** 336.6ms
- **Auth utilisée :** none
- **Réponse :**
```json
{
  "non_field_errors": [
    "Email ou mot de passe incorrect."
  ]
}
```

### 4. ❌ `POST /api/auth/login/`

- **Description :** Connexion — email inexistant
- **Catégorie :** auth
- **Statut attendu :** `401`
- **Statut reçu :** `400`
- **Temps :** 323.5ms
- **Auth utilisée :** none
- **Réponse :**
```json
{
  "non_field_errors": [
    "Email ou mot de passe incorrect."
  ]
}
```

### 5. ❌ `POST /api/spaces/create/`

- **Description :** Créer espace — admin
- **Catégorie :** espaces
- **Statut attendu :** `201`
- **Statut reçu :** `415`
- **Temps :** 63.6ms
- **Auth utilisée :** admin
- **Réponse :**
```json
{
  "detail": "Type de média « application/json » non supporté."
}
```

### 6. ❌ `POST /api/spaces/create/`

- **Description :** Créer espace — payload invalide
- **Catégorie :** espaces
- **Statut attendu :** `400`
- **Statut reçu :** `415`
- **Temps :** 67.2ms
- **Auth utilisée :** admin
- **Réponse :**
```json
{
  "detail": "Type de média « application/json » non supporté."
}
```

### 7. ❌ `POST /api/reservations/create/`

- **Description :** Créer réservation — user auth
- **Catégorie :** réservations
- **Statut attendu :** `201`
- **Statut reçu :** `400`
- **Temps :** 60.9ms
- **Auth utilisée :** user
- **Réponse :**
```json
{
  "space_id": [
    "Ce champ est obligatoire."
  ]
}
```

### 8. ❌ `POST /api/payments/create/`

- **Description :** Créer paiement — réservation inexistante
- **Catégorie :** paiements
- **Statut attendu :** `404`
- **Statut reçu :** `400`
- **Temps :** 65.2ms
- **Auth utilisée :** user
- **Réponse :**
```json
{
  "reservation_id": [
    "Réservation introuvable."
  ]
}
```

### 9. ❌ `PUT /api/notifications/read/`

- **Description :** Marquer tout comme lu — user
- **Catégorie :** notifications
- **Statut attendu :** `200`
- **Statut reçu :** `405`
- **Temps :** 58.0ms
- **Auth utilisée :** user
- **Réponse :**
```json
{
  "detail": "Méthode « PUT » non autorisée."
}
```

### 10. ❌ `PUT /api/notifications/99999/read/`

- **Description :** Marquer notification inexistante (404)
- **Catégorie :** notifications
- **Statut attendu :** `404`
- **Statut reçu :** `405`
- **Temps :** 64.7ms
- **Auth utilisée :** user
- **Réponse :**
```json
{
  "detail": "Méthode « PUT » non autorisée."
}
```

### 11. ⚠️ `GET /api/spaces/`

- **Description :** Espaces — token invalide tolère (200 ou 401)
- **Catégorie :** robustesse
- **Statut attendu :** `200`
- **Statut reçu :** `401`
- **Temps :** 45.0ms
- **Auth utilisée :** none
- **Réponse :**
```json
{
  "detail": "Le type de jeton fourni n'est pas valide",
  "code": "token_not_valid",
  "messages": [
    {
      "token_class": "AccessToken",
      "token_type": "access",
      "message": "Le jeton est invalide ou expiré"
    }
  ]
}
```

### 12. ❌ `POST /api/spaces/create/`

- **Description :** Payload — champs vides
- **Catégorie :** robustesse
- **Statut attendu :** `400`
- **Statut reçu :** `415`
- **Temps :** 64.6ms
- **Auth utilisée :** admin
- **Réponse :**
```json
{
  "detail": "Type de média « application/json » non supporté."
}
```

### 13. ❌ `POST /api/spaces/create/`

- **Description :** Payload — string au lieu d'int pour capacity
- **Catégorie :** robustesse
- **Statut attendu :** `400`
- **Statut reçu :** `415`
- **Temps :** 68.3ms
- **Auth utilisée :** admin
- **Réponse :**
```json
{
  "detail": "Type de média « application/json » non supporté."
}
```

### 14. ❌ `GET /api/`

- **Description :** Racine API (200 ou 404)
- **Catégorie :** robustesse
- **Statut attendu :** `200`
- **Statut reçu :** `404`
- **Temps :** 49.0ms
- **Auth utilisée :** none
- **Réponse :**
```json
{
  "raw": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n  <meta http-equiv=\"content-type\" content=\"text/html; charset=utf-8\">\n  <title>Page not found at /api/</title>\n  <meta name=\"robots\" content=\"NONE,NOARCHIVE\">\n  <style type=\"text/css\">\n    html * { padding:0; margin:0; }\n    body * { padding:10px 20px; }\n    body * * { padding:0; }\n    body { font:small sans-serif; background:#eee; color:#000; }\n    body>div { border-bottom:1px solid #ddd; }\n    h1 { font-weight:normal; margin-bottom:.4em; }\n    h1 span { "
}
```

## ⚡ Performances

### 🐢 Top 10 endpoints les plus lents

| Rang | Endpoint | Méthode | Temps |
|------|----------|---------|-------|
| 1 | `/api/schema/` | `GET` | 392ms 🟢 |
| 2 | `/api/auth/login/` | `POST` | 337ms 🟢 |
| 3 | `/api/auth/login/` | `POST` | 332ms 🟢 |
| 4 | `/api/auth/change-password/` | `POST` | 331ms 🟢 |
| 5 | `/api/auth/login/` | `POST` | 324ms 🟢 |
| 6 | `/api/auth/register/` | `POST` | 319ms 🟢 |
| 7 | `/api/auth/login/` | `POST` | 289ms 🟢 |
| 8 | `/api/auth/login/` | `POST` | 284ms 🟢 |
| 9 | `/api/spaces/` | `GET` | 99ms 🟢 |
| 10 | `/api/reservations/` | `GET` | 96ms 🟢 |

### ⚡ Top 5 endpoints les plus rapides

| Rang | Endpoint | Méthode | Temps |
|------|----------|---------|-------|
| 1 | `/api/docs/` | `GET` | 15ms |
| 2 | `/api/auth/login/` | `DELETE` | 44ms |
| 3 | `/api/payments/webhook/` | `POST` | 44ms |
| 4 | `/api/notifications/read/` | `PUT` | 45ms |
| 5 | `/api/notifications/` | `GET` | 45ms |

## 📊 Distribution des codes HTTP retournés

| Code HTTP | Occurrences | Signification |
|-----------|-------------|---------------|
| `200` | 29 | OK |
| `201` | 1 | Created |
| `400` | 14 | Bad Request |
| `401` | 17 | Unauthorized |
| `403` | 5 | Forbidden |
| `404` | 8 | Not Found |
| `405` | 6 | Method Not Allowed |
| `406` | 2 | — |
| `415` | 4 | — |

## 🗺️ Couverture des endpoints

**34 endpoints uniques testés** :

- `/api/` — `GET`
- `/api/admin/dashboard/` — `GET`
- `/api/admin/export/reservations/` — `GET`
- `/api/auth/admin/users/` — `GET`
- `/api/auth/admin/users/6/` — `PATCH`
- `/api/auth/change-password/` — `POST`
- `/api/auth/login/` — `DELETE` `POST`
- `/api/auth/logout/` — `POST`
- `/api/auth/profile/` — `GET` `PATCH`
- `/api/auth/register/` — `POST`
- `/api/auth/token/refresh/` — `POST`
- `/api/docs/` — `GET`
- `/api/inexistant/` — `GET`
- `/api/notifications/` — `GET`
- `/api/notifications/99999/read/` — `PUT`
- `/api/notifications/read/` — `PUT`
- `/api/payments/` — `GET`
- `/api/payments/-1/` — `GET`
- `/api/payments/99999/` — `GET`
- `/api/payments/create/` — `POST`
- `/api/payments/stats/` — `GET`
- `/api/payments/webhook/` — `GET` `POST`
- `/api/redoc/` — `GET`
- `/api/reservations/` — `GET`
- `/api/reservations/0/` — `GET`
- `/api/reservations/99999/` — `GET`
- `/api/reservations/create/` — `POST`
- `/api/schema/` — `GET`
- `/api/spaces/` — `GET` `PATCH` `PUT`
- `/api/spaces/1/` — `GET`
- `/api/spaces/1/availability/` — `GET`
- `/api/spaces/99999/` — `GET`
- `/api/spaces/abc/` — `GET`
- `/api/spaces/create/` — `POST`

## 💡 Recommandations

- ✅ Aucun problème critique détecté.

## ⚙️ Configuration du test

```
BASE_URL      : http://localhost:8000
ADMIN_EMAIL   : user@example.com
USER_EMAIL    : user@example.com
TIMEOUT       : 10s
Démarré       : 20/04/2026 10:49:02
Terminé       : 20/04/2026 10:49:10
Durée totale  : 7.5s
```

---
*Rapport généré automatiquement par `test_api.py`*