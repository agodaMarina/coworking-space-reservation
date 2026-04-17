# API de Réservation d'Espaces de Coworking

## Description

Ce projet est une API REST développée avec Django pour un système de réservation d'espaces de coworking. Il permet la gestion des espaces, des réservations, des paiements, des notifications et des comptes utilisateurs.

## Fonctionnalités

- **Gestion des espaces** : Création et gestion des espaces de coworking (bureaux individuels, espaces ouverts, salles de réunion, etc.)
- **Système de réservations** : Réservation d'espaces avec gestion des conflits
- **Paiements intégrés** : Intégration Stripe pour les paiements sécurisés
- **Authentification JWT** : Système d'authentification basé sur JSON Web Tokens
- **Notifications** : Système de notifications pour les réservations et paiements
- **API REST** : Interface RESTful complète avec documentation Swagger/OpenAPI
- **Gestion des utilisateurs** : Comptes utilisateurs avec rôles (admin, client, etc.)

## Technologies utilisées

- **Backend** : Django 5.0.6, Django REST Framework
- **Base de données** : PostgreSQL
- **Authentification** : Django REST Framework Simple JWT
- **Paiements** : Stripe
- **Tâches asynchrones** : Celery + Redis
- **Images** : Django ImageKit + Pillow
- **Documentation** : DRF Spectacular (Swagger/OpenAPI)
- **Sécurité** : CORS, rate limiting, HTTPS en production

## Prérequis

- Python 3.12
- PostgreSQL (via Docker recommandé)
- Redis (pour Celery)
- Git

## Installation

### 1. Cloner le repository

```bash
git clone <url-du-repository>
cd PROJET_DJANGO
```

### 2. Créer et activer l'environnement virtuel

```bash
python3 -m venv env
source env/bin/activate  # Sur Linux/Mac
# ou env\Scripts\activate sur Windows
```

### 3. Installer les dépendances

```bash
pip install -r requirements/development.txt
```

### 4. Configuration de la base de données

#### Via Docker (recommandé)

Assurez-vous que Docker est installé et lancez le conteneur PostgreSQL :

```bash
# Le conteneur kc26-postgres doit être en cours d'exécution
docker ps
```

Si le conteneur n'existe pas, créez-le :

```bash
docker run --name kc26-postgres -e POSTGRES_DB=keycloak -e POSTGRES_USER=keycloak -e POSTGRES_PASSWORD=keycloak -p 5432:5432 -d postgres:16-alpine
```

Créez la base de données pour le projet :

```bash
docker exec -t kc26-postgres psql -U keycloak -d keycloak -c "CREATE DATABASE coworking_db;"
```

#### Configuration des variables d'environnement

Copiez le fichier `.env.example` vers `.env` et modifiez les valeurs :

```bash
cp .env.example .env
```

Modifiez `.env` avec vos configurations :

```env
SECRET_KEY=votre-cle-secrete-unique
DEBUG=True

DB_NAME=coworking_db
DB_USER=keycloak
DB_PASSWORD=keycloak
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://localhost:6379/0

STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=votre@email.com
EMAIL_HOST_PASSWORD=votre-mot-de-passe-app
DEFAULT_FROM_EMAIL=noreply@coworking.com

CORS_ALLOWED_ORIGINS=http://localhost:4200
ALLOWED_HOSTS=*
```

### 5. Appliquer les migrations

```bash
python manage.py migrate --settings=config.settings.development
```

### 6. Créer un superutilisateur (optionnel)

```bash
python manage.py createsuperuser --settings=config.settings.development
```

## Démarrage du serveur

### Serveur de développement

```bash
python manage.py runserver --settings=config.settings.development
```

Le serveur sera accessible à `http://127.0.0.1:8000/`

### Avec Celery (pour les tâches asynchrones)

Dans un terminal séparé :

```bash
celery -A config worker --loglevel=info
```

### Avec Redis (assurez-vous que Redis est en cours d'exécution)

```bash
redis-server
```

## Tests

### Exécuter tous les tests

```bash
python manage.py test --settings=config.settings.development
```

### Tests avec couverture

```bash
coverage run manage.py test --settings=config.settings.development
coverage report
```

## Qualité du code

### Linting et formatage

```bash
# Installation des outils de développement
pip install black flake8 isort

# Formatage du code
black .
isort .

# Vérification du linting
flake8 .
```

### Vérification des types

```bash
pip install mypy
mypy .
```

## Documentation API

### Accès à Swagger/OpenAPI

Une fois le serveur lancé, accédez à la documentation interactive :

- Swagger UI : `http://127.0.0.1:8000/api/schema/swagger-ui/`
- ReDoc : `http://127.0.0.1:8000/api/schema/redoc/`
- Schéma OpenAPI : `http://127.0.0.1:8000/api/schema/`

### Points d'API principaux

- **Authentification** : `/api/auth/`
- **Espaces** : `/api/spaces/`
- **Réservations** : `/api/reservations/`
- **Paiements** : `/api/payments/`
- **Comptes** : `/api/accounts/`
- **Notifications** : `/api/notifications/`

## Structure du projet

```
PROJET_DJANGO/
├── apps/                    # Applications Django
│   ├── accounts/           # Gestion des comptes utilisateurs
│   ├── spaces/             # Gestion des espaces
│   ├── reservations/       # Système de réservations
│   ├── payments/           # Intégration paiements
│   └── notifications/      # Système de notifications
├── config/                 # Configuration Django
│   ├── settings/           # Paramètres par environnement
│   ├── urls.py             # Routes principales
│   └── wsgi.py             # Configuration WSGI
├── docs/                   # Documentation
├── requirements/           # Dépendances Python
├── static/                 # Fichiers statiques
├── media/                  # Médias uploadés
├── templates/              # Templates Django
├── manage.py               # Script de gestion Django
└── .env                    # Variables d'environnement
```

## Déploiement

### Configuration de production

Utilisez les paramètres de production :

```bash
python manage.py runserver --settings=config.settings.production
```

Assurez-vous de configurer :
- `DEBUG=False`
- `ALLOWED_HOSTS` avec vos domaines
- Variables d'environnement pour la base de données, Stripe, email
- Serveur web (Nginx + Gunicorn recommandé)
- HTTPS obligatoire

### Variables d'environnement de production

```env
DEBUG=False
ALLOWED_HOSTS=votre-domaine.com,www.votre-domaine.com
SECRET_KEY=votre-cle-secrete-production

# Base de données PostgreSQL
DB_NAME=coworking_prod
DB_USER=votre_user_prod
DB_PASSWORD=votre_password_prod
DB_HOST=votre_host_prod
DB_PORT=5432

# Redis
REDIS_URL=redis://votre-redis-host:6379/0

# Stripe (clés de production)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email
EMAIL_HOST=votre-smtp-host
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=votre-email@domaine.com
EMAIL_HOST_PASSWORD=votre-mot-de-passe
DEFAULT_FROM_EMAIL=noreply@votre-domaine.com

# CORS
CORS_ALLOWED_ORIGINS=https://votre-domaine.com,https://www.votre-domaine.com
```

## Développement

### Branches

- `main` : Code de production
- `develop` : Développement actif
- `feature/*` : Nouvelles fonctionnalités

### Commits

Suivez les conventions de commit :

```
feat: ajout nouvelle fonctionnalité
fix: correction de bug
docs: mise à jour documentation
style: formatage du code
refactor: refactorisation du code
test: ajout ou modification de tests
chore: tâches diverses
```

### Hooks Git

Installez les hooks de pre-commit :

```bash
pip install pre-commit
pre-commit install
```

## Support et contribution

### Signaler un bug

Utilisez les issues GitHub pour signaler les bugs.

### Contribuer

1. Forkez le projet
2. Créez une branche feature (`git checkout -b feature/nouvelle-fonctionnalite`)
3. Commitez vos changements (`git commit -am 'feat: ajout nouvelle fonctionnalité'`)
4. Pushez la branche (`git push origin feature/nouvelle-fonctionnalite`)
5. Ouvrez une Pull Request

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## Contact

Pour toute question, contactez l'équipe de développement à [votre-email@domaine.com]

---

Développé avec ❤️ pour la communauté coworking</content>
<filePath>README.md