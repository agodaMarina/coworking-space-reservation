# Audit du projet — Coworking Space Reservation API

*Dernière mise à jour : 2026-04-22 — corrections complètes réservations*

## Vue d'ensemble

API REST Django pour la gestion d'espaces de coworking. 5 applications, ~50 endpoints, authentification JWT, paiements Stripe, tâches asynchrones Celery.

---

## Ce qui existe et fonctionne

### Authentification (`/api/auth/`)
- Inscription, connexion, déconnexion (blacklist du refresh token)
- Profil utilisateur (lecture + modification)
- Changement de mot de passe
- Rafraîchissement du token JWT
- 3 rôles : `client`, `admin`, `manager`
- Gestion admin des utilisateurs : liste, création avec rôle, modification (is_active, role, is_verified), suppression

### Espaces (`/api/spaces/`)
- CRUD complet des espaces (admin)
- 5 types : bureau individuel, open space, salle de réunion, bureau privé, salle de conférence
- Upload de photos (multipart ou base64 via `FileOrBase64Field`), suppression
- Gestion des équipements (amenities)
- Vérification de disponibilité avec plage horaire
- Accès public en lecture

### Réservations (`/api/reservations/`)
- Création avec vérification de disponibilité automatique (chevauchements détectés correctement)
- Calcul du prix horaire correct ; calcul journalier **incorrect** (voir bugs)
- Statuts : PENDING → CONFIRMED / CANCELLED / REJECTED ; COMPLETED déclaré mais jamais attribué
- Annulation par le client (PENDING ou CONFIRMED) ou l'admin — sans délai minimum
- Dashboard admin : KPIs (réservations, revenus, taux d'occupation)
- Export CSV des réservations

### Paiements (`/api/payments/`)
- Intégration Stripe (PaymentIntent, webhook HMAC, remboursements)
- Paiements locaux : espèces, mobile money, virement
- Conversion XOF ↔ EUR (655.957 XOF = 1 EUR)
- Confirmation admin pour les paiements locaux
- Remboursement partiel ou total
- Téléchargement de facture (format texte)
- Statistiques : revenus, répartition par méthode

### Notifications (`/api/notifications/`)
- Notifications en base de données (6 types)
- Envoi d'emails asynchrone via Celery (confirmation, annulation)
- Rappel 48h avant la réservation (tâche planifiable)
- Marquage lu / non lu

---

## Bugs identifiés

### CRITIQUE — Stripe non confirmable
**Fichier** : `apps/payments/urls.py`

`PaymentStripeConfirmView` est implémentée dans `views.py` mais **jamais enregistrée dans les URLs**. Il est donc impossible de confirmer un paiement Stripe côté serveur après confirmation frontend.

**Correction à apporter** :
```python
path('<int:pk>/stripe-confirm/', PaymentStripeConfirmView.as_view(), name='payment-stripe-confirm'),
```

---

### ÉLEVÉ — Email de paiement jamais envoyé
**Fichier** : `apps/notifications/tasks.py` + `apps/payments/views.py`

La tâche `send_payment_completed_email` existe mais n'est appelée nulle part dans les vues de paiement. L'utilisateur ne reçoit aucune notification lors d'un paiement confirmé.

---

## Bugs identifiés et corrigés

### ✅ CORRIGÉ — Tarification journalière incorrecte
**Fichier** : `services/availability.py`

`timedelta.days` arrondit à l'inférieur (25h = 1 jour). Remplacé par `math.ceil(total_hours / 24)`.

---

### ✅ CORRIGÉ — Statut COMPLETED jamais attribué
**Fichier** : `apps/notifications/tasks.py`, `config/celery.py`

Nouvelle tâche `mark_completed_reservations()` planifiée toutes les heures via Celery Beat. Passe en `COMPLETED` toutes les réservations `CONFIRMED` dont `end_datetime < now()`.

---

### ✅ CORRIGÉ — `space.is_available` ignoré dans les vues d'availability
**Fichiers** : `apps/spaces/views.py` — `SpaceAvailabilityGetView`, `apps/reservations/views.py` — `SpaceAvailabilityView`

Les deux vues vérifient maintenant `space.is_available` **avant** d'appeler `check_availability()`, et retournent `is_available: false` immédiatement si l'espace est désactivé.

---

### ✅ CORRIGÉ — Machine d'état non contrôlée
**Fichier** : `apps/reservations/serializers.py` — `ReservationUpdateSerializer`

`validate_status()` applique une table de transitions autorisées :
- `pending` → `confirmed`, `rejected`, `cancelled`
- `confirmed` → `cancelled`, `completed`
- `cancelled`, `completed`, `rejected` → aucune transition possible

---

### ✅ CORRIGÉ — Pas de délai minimum d'annulation
**Fichier** : `services/reservation_logic.py` — `cancel_reservation()`

Les clients (non-admin) ne peuvent plus annuler moins de 24h avant le début. Les admins gardent la capacité d'annuler à tout moment. Les statuts terminaux (`cancelled`, `completed`, `rejected`) sont tous bloqués.

---

### ✅ CORRIGÉ — Stripe non confirmable
**Fichier** : `apps/payments/urls.py`

`PaymentStripeConfirmView` est maintenant enregistrée : `POST /api/payments/<pk>/stripe-confirm/`

---

### ✅ CORRIGÉ — Email de paiement jamais envoyé
**Fichier** : `apps/payments/views.py`

`send_payment_completed_email.delay()` est maintenant appelée dans les trois points de confirmation :
- `PaymentStripeConfirmView.post()` — confirmation frontend Stripe
- `PaymentConfirmView.patch()` — validation admin paiement local
- `StripeWebhookView._handle_payment_succeeded()` — backup webhook

---

## Corrections précédentes

### ✅ Bug CORRIGÉ — Photo uploadée en double
**Fichier** : `apps/spaces/views.py` — `SpacePhotoUploadView`

Le double bloc `SpacePhoto.objects.create(...)` a été supprimé. Un seul appel subsiste, dans le bloc `try/except`. Le recalcul parasite de `next_position` en dehors du bloc a également été retiré.

---

### ✅ Nouvel endpoint — Création d'utilisateur par l'admin
**Fichiers** : `apps/accounts/admin_views.py`, `apps/accounts/serializers.py`, `apps/accounts/urls.py`

`POST /api/auth/admin/users/create/` — admin seulement.

- Nouveau serializer `AdminCreateUserSerializer` : champs email, username, prénom, nom, téléphone, rôle, mot de passe (avec confirmation).
- L'utilisateur créé par un admin est automatiquement marqué `is_verified = True`.
- Si le rôle est `ADMIN`, `is_staff = True` est positionné automatiquement.

---

### ✅ Nouvel endpoint — Suppression d'utilisateur par l'admin
**Fichiers** : `apps/accounts/admin_views.py`, `apps/accounts/urls.py`

`DELETE /api/auth/admin/users/<pk>/delete/` — admin seulement.

- Garde-fou : un admin ne peut pas supprimer son propre compte.

---

### ✅ Amélioration — Validation du numéro de téléphone
**Fichier** : `apps/accounts/serializers.py`

L'ancienne regex `^\+?1?\d{9,15}$` n'acceptait pas les formats courants (espaces, tirets, parenthèses). Remplacée par :
- Regex permissive sur les caractères : `^\+?[\d\s\-\(\)\.]{7,20}$`
- Vérification du nombre de chiffres réels : entre 7 et 15 après suppression des séparateurs.

Appliqué dans `RegisterSerializer` et `AdminCreateUserSerializer`.

---

### ✅ Amélioration — Champ photo upload typé
**Fichier** : `apps/spaces/serializers.py`

Le champ `file` du `SpacePhotoUploadSerializer` utilisait un `CharField` générique. Remplacé par un `FileOrBase64Field` dédié qui accepte explicitement un `UploadedFile` (multipart) ou une `str` (base64), et rejette tout autre type avec un message d'erreur clair.

---

## Ce qu'il faudra améliorer

### Fonctionnalités manquantes

| Priorité | Fonctionnalité | Description |
|----------|---------------|-------------|
| Haute | Réservations récurrentes | Champs présents, logique de génération d'occurrences complètement absente |
| Haute | Facture PDF | Le champ `pdf_file` existe dans le modèle `Invoice` mais la génération PDF n'est pas implémentée (uniquement fichier texte) |
| Haute | Notifications SMS | Le canal SMS est défini dans le modèle mais pas du tout implémenté |
| Moyenne | Liste réservations admin | Pas d'endpoint dédié pour lister toutes les réservations (seul le CSV existe) |
| Moyenne | Vérification email | `is_verified` existe mais aucun flux d'envoi de lien de vérification n'est implémenté |
| Basse | Réinitialisation de mot de passe | Pas de flux "mot de passe oublié" |
| Basse | Pagination configurable | Pagination fixée à 20, non paramétrable par l'utilisateur |

### Sécurité & Production

| Priorité | Point | Description |
|----------|-------|-------------|
| Haute | CORS | `CORS_ALLOW_ALL_ORIGINS = True` en dev — à restreindre en production |
| Haute | Variables Stripe | Les clés de test sont dans `.env` — pipeline CI/CD à sécuriser |
| Moyenne | Rate limiting | 100/jour (anonyme), 1000/jour (utilisateur) — à ajuster selon le trafic réel |
| Moyenne | Logs | Logging en console uniquement — ajouter un handler fichier ou service (Sentry, Datadog) |
| Basse | HTTPS | Non configuré côté Django — à gérer au niveau Nginx/proxy en production |

### Qualité du code

| Fichier | Problème |
|---------|---------|
| `apps/payments/views.py` | `PaymentStripeConfirmView` : non branché dans les URLs |
| `apps/reservations/views.py` | Logique métier directement dans les vues — à déplacer dans les services existants |
| `apps/reservations/serializers.py` | `ReservationCreateSerializer` ne valide pas `space.is_available` |
| `config/settings/development.py` | Port DB `5433` (Docker) vs `5432` (installation locale) — vérifier la cohérence |

---

## Résumé rapide

```
✅ Fonctionne     : Auth JWT, Espaces, Réservations, Paiements Stripe + locaux, Notifications email
✅ Corrigé        : Photo en double, création/suppression admin, validation téléphone,
                   tarif journalier, COMPLETED via Celery Beat, space.is_available dans availability,
                   machine d'état, délai annulation 24h, Stripe confirm routé, email paiement envoyé
🔧 À implémenter  : Logique récurrence (occurrences), PDF facture, SMS, vérification email, reset password
🔒 Production     : Restreindre CORS, configurer logs, HTTPS via proxy
```
