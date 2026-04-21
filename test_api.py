#!/usr/bin/env python
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          COWORKING API — SCRIPT DE TEST COMPLET DES ENDPOINTS               ║
║          Génère un rapport Markdown détaillé de l'état du backend           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage :
    # Depuis la racine du projet Django
    python test_api.py

    # Avec un serveur custom
    BASE_URL=http://localhost:8000 python test_api.py

    # Ou comme management command si déplacé dans management/commands/
    python manage.py test_endpoints

Pré-requis :
    pip install requests tabulate colorama

Le rapport est généré dans : api_test_report.md
"""

import os
import sys
import json
import time
import datetime
import traceback
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# ── Dépendances externes ─────────────────────────────────────────────────────
try:
    import requests
    from requests.exceptions import ConnectionError, Timeout, RequestException
except ImportError:
    print("❌ 'requests' manquant. Installez-le : pip install requests")
    sys.exit(1)

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class Fore:
        GREEN = RED = YELLOW = CYAN = MAGENTA = WHITE = RESET = ""
    class Style:
        BRIGHT = DIM = RESET_ALL = ""

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
REPORT_FILE = Path("api_test_report.md")
TIMEOUT = 10  # secondes

# Credentials de test — adaptez si nécessaire
ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL",    "user@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Passw0rd1234")
USER_EMAIL     = os.environ.get("USER_EMAIL",     "user@example.com")
USER_PASSWORD  = os.environ.get("USER_PASSWORD",  "Passw0rd1234")

# ════════════════════════════════════════════════════════════════════════════
# STRUCTURES DE DONNÉES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class TestResult:
    """Résultat d'un test d'endpoint."""
    endpoint: str
    method: str
    description: str
    expected_status: int
    actual_status: Optional[int] = None
    response_time_ms: float = 0.0
    response_body: Optional[dict] = None
    error: Optional[str] = None
    auth_used: str = "none"          # none | user | admin
    category: str = "général"
    passed: bool = False

    @property
    def status_icon(self) -> str:
        if self.error:
            return "💥"
        if self.passed:
            return "✅"
        # Tolérance : 401/403 sur endpoint public = warning, pas échec dur
        if self.actual_status in (401, 403) and self.expected_status not in (401, 403):
            return "⚠️"
        return "❌"

    @property
    def response_summary(self) -> str:
        if self.error:
            return f"ERREUR: {self.error[:120]}"
        if not self.response_body:
            return "— réponse vide —"
        body = self.response_body
        # Extraire les champs les plus utiles
        if isinstance(body, dict):
            keys = list(body.keys())[:6]
            preview = {k: str(body[k])[:60] for k in keys}
            return json.dumps(preview, ensure_ascii=False)
        if isinstance(body, list):
            return f"[{len(body)} éléments] {str(body[:1])[:100]}"
        return str(body)[:150]


@dataclass
class TestSuite:
    """Conteneur de tous les résultats."""
    results: list = field(default_factory=list)
    start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    end_time: Optional[datetime.datetime] = None
    admin_token: Optional[str] = None
    user_token: Optional[str] = None
    # IDs créés pendant les tests (pour les appels dépendants)
    created_space_id: Optional[int] = None
    created_reservation_id: Optional[int] = None
    created_payment_id: Optional[int] = None
    created_user_id: Optional[int] = None

    def add(self, result: TestResult):
        self.results.append(result)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed and not r.error)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.error)

    @property
    def warnings(self) -> int:
        return sum(
            1 for r in self.results
            if not r.passed and not r.error
            and r.actual_status in (401, 403)
            and r.expected_status not in (401, 403)
        )

    @property
    def success_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total else 0

    @property
    def avg_response_time(self) -> float:
        times = [r.response_time_ms for r in self.results if r.response_time_ms > 0]
        return sum(times) / len(times) if times else 0

    def by_category(self) -> dict:
        cats = {}
        for r in self.results:
            cats.setdefault(r.category, []).append(r)
        return cats


# ════════════════════════════════════════════════════════════════════════════
# CLIENT HTTP
# ════════════════════════════════════════════════════════════════════════════

class APIClient:
    """Wrapper requests avec gestion JWT et mesure de temps."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _headers(self, token: Optional[str] = None, extra: dict = None) -> dict:
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        if extra:
            h.update(extra)
        return h

    def request(
        self,
        method: str,
        path: str,
        token: Optional[str] = None,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
        raw_body: Optional[bytes] = None,
    ) -> tuple[Optional[int], Optional[dict], float, Optional[str]]:
        """
        Effectue une requête et retourne (status, body, time_ms, error).
        """
        url = f"{self.base_url}{path}"
        headers = self._headers(token, extra_headers)

        start = time.perf_counter()
        try:
            if raw_body is not None:
                # Pour le webhook Stripe (payload brut)
                resp = self.session.request(
                    method.upper(),
                    url,
                    data=raw_body,
                    headers=headers,
                    params=params,
                    timeout=TIMEOUT,
                )
            else:
                resp = self.session.request(
                    method.upper(),
                    url,
                    json=body,
                    headers=headers,
                    params=params,
                    timeout=TIMEOUT,
                )

            elapsed_ms = (time.perf_counter() - start) * 1000

            try:
                response_body = resp.json()
            except Exception:
                response_body = {"raw": resp.text[:500]} if resp.text else None

            return resp.status_code, response_body, elapsed_ms, None

        except ConnectionError:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return None, None, elapsed_ms, f"Connexion refusée — le serveur est-il lancé sur {self.base_url} ?"
        except Timeout:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return None, None, elapsed_ms, f"Timeout après {TIMEOUT}s"
        except RequestException as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return None, None, elapsed_ms, str(e)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return None, None, elapsed_ms, f"Erreur inattendue : {traceback.format_exc()[:300]}"


# ════════════════════════════════════════════════════════════════════════════
# RUNNER DE TESTS
# ════════════════════════════════════════════════════════════════════════════

class EndpointTester:

    def __init__(self, base_url: str):
        self.client = APIClient(base_url)
        self.suite = TestSuite()

    # ── Utilitaire principal ──────────────────────────────────────────────────

    def run(
        self,
        method: str,
        path: str,
        description: str,
        expected_status: int,
        category: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
        token: Optional[str] = None,
        auth_label: str = "none",
        extra_headers: Optional[dict] = None,
        raw_body: Optional[bytes] = None,
    ) -> TestResult:

        status_code, response_body, elapsed, error = self.client.request(
            method, path, token, body, params, extra_headers, raw_body
        )

        passed = (
            not error
            and status_code is not None
            and status_code == expected_status
        )

        result = TestResult(
            endpoint=path,
            method=method.upper(),
            description=description,
            expected_status=expected_status,
            actual_status=status_code,
            response_time_ms=elapsed,
            response_body=response_body,
            error=error,
            auth_used=auth_label,
            category=category,
            passed=passed,
        )

        self.suite.add(result)
        self._print_live(result)
        return result

    def _print_live(self, r: TestResult):
        icon = r.status_icon
        status_str = str(r.actual_status) if r.actual_status else "N/A"
        color = Fore.GREEN if r.passed else (Fore.YELLOW if "⚠️" in icon else Fore.RED)
        print(
            f"  {icon} {color}{r.method:<7}{Style.RESET_ALL if HAS_COLOR else ''} "
            f"{r.endpoint:<55} "
            f"[{status_str}/{r.expected_status}] "
            f"{r.response_time_ms:>7.1f}ms"
        )

    # ── Helpers auth ─────────────────────────────────────────────────────────

    def _admin(self) -> tuple[Optional[str], str]:
        return self.suite.admin_token, "admin"

    def _user(self) -> tuple[Optional[str], str]:
        return self.suite.user_token, "user"

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 0 — Vérification serveur
    # ════════════════════════════════════════════════════════════════════════

    def test_server_health(self):
        print(f"\n{Fore.CYAN}{'═'*65}")
        print("  PHASE 0 — Vérification serveur")
        print(f"{'═'*65}{Style.RESET_ALL if HAS_COLOR else ''}")

        r = self.run("GET", "/api/docs/", "Swagger UI accessible", 200, "infra")
        if r.error:
            print(f"\n{Fore.RED}  ⛔ SERVEUR INACCESSIBLE — {r.error}")
            print(f"  Lancez le serveur : python manage.py runserver{Style.RESET_ALL if HAS_COLOR else ''}")
            return False

        self.run("GET", "/api/schema/", "Schéma OpenAPI (JSON)", 200, "infra")
        self.run("GET", "/api/redoc/", "ReDoc accessible", 200, "infra")
        return True

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Authentification
    # ════════════════════════════════════════════════════════════════════════

    def test_auth(self):
        print(f"\n{Fore.CYAN}{'═'*65}")
        print("  PHASE 1 — Authentification (/api/auth/)")
        print(f"{'═'*65}{Style.RESET_ALL if HAS_COLOR else ''}")

        cat = "auth"

        # ── 1.1 Inscription d'un user de test ─────────────────────────────────
        ts = int(time.time())
        new_user_payload = {
            "email":            f"testuser_{ts}@coworking.com",
            "username":         f"testuser_{ts}",
            "first_name":       "Test",
            "last_name":        "User",
            "phone":            "+22890000001",
            "password":         "TestPass1234!",
            "password_confirm": "TestPass1234!",
        }
        r = self.run("POST", "/api/auth/register/", "Inscription nouvel utilisateur", 201, cat, body=new_user_payload)
        if r.passed and r.response_body:
            self.suite.created_user_id = r.response_body.get("user", {}).get("id")
            # Stocker le token user depuis l'inscription
            tokens = r.response_body.get("tokens", {})
            if tokens.get("access"):
                self.suite.user_token = tokens["access"]

        # ── 1.2 Inscription avec données invalides ────────────────────────────
        self.run("POST", "/api/auth/register/", "Inscription — email manquant", 400, cat,
                 body={"username": "x", "password": "pass", "password_confirm": "pass"})

        self.run("POST", "/api/auth/register/", "Inscription — mots de passe différents", 400, cat,
                 body={**new_user_payload, "email": f"other_{ts}@test.com",
                       "username": f"other_{ts}", "password_confirm": "MISMATCH"})

        # ── 1.3 Connexion admin ───────────────────────────────────────────────
        r = self.run("POST", "/api/auth/login/", "Connexion admin", 200, cat,
                     body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        if r.passed and r.response_body:
            tokens = r.response_body.get("tokens", {})
            self.suite.admin_token = tokens.get("access")
            print(f"    {Fore.GREEN}  → Token admin obtenu ✓{Style.RESET_ALL if HAS_COLOR else ''}")

        # ── 1.4 Connexion user (si pas déjà fait via register) ────────────────
        if not self.suite.user_token:
            r = self.run("POST", "/api/auth/login/", "Connexion utilisateur standard", 200, cat,
                         body={"email": USER_EMAIL, "password": USER_PASSWORD})
            if r.passed and r.response_body:
                self.suite.user_token = r.response_body.get("tokens", {}).get("access")
                print(f"    {Fore.GREEN}  → Token user obtenu ✓{Style.RESET_ALL if HAS_COLOR else ''}")

        # ── 1.5 Connexion avec mauvaises credentials ──────────────────────────
        self.run("POST", "/api/auth/login/", "Connexion — mauvais mot de passe", 401, cat,
                 body={"email": ADMIN_EMAIL, "password": "MAUVAIS_MDP"})

        self.run("POST", "/api/auth/login/", "Connexion — email inexistant", 401, cat,
                 body={"email": "inexistant@test.com", "password": "pass"})

        # ── 1.6 Rafraîchissement token ────────────────────────────────────────
        # On essaie d'abord avec le token admin pour obtenir un refresh token
        r2 = self.run("POST", "/api/auth/login/", "Re-login pour refresh token", 200, cat,
                      body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        if r2.passed and r2.response_body:
            refresh = r2.response_body.get("tokens", {}).get("refresh")
            if refresh:
                self.run("POST", "/api/auth/token/refresh/", "Rafraîchissement token — valide", 200, cat,
                         body={"refresh": refresh})

        self.run("POST", "/api/auth/token/refresh/", "Rafraîchissement token — invalide", 401, cat,
                 body={"refresh": "invalid.token.here"})

        # ── 1.7 Profil utilisateur ────────────────────────────────────────────
        tok, lbl = self._admin()
        self.run("GET", "/api/auth/profile/", "Profil — authentifié (admin)", 200, cat, token=tok, auth_label=lbl)
        self.run("GET", "/api/auth/profile/", "Profil — non authentifié", 401, cat)

        tok, lbl = self._admin()
        self.run("PATCH", "/api/auth/profile/", "Modifier profil (PATCH)", 200, cat,
                 body={"first_name": "AdminModifié"}, token=tok, auth_label=lbl)

        # ── 1.8 Changement de mot de passe ────────────────────────────────────
        tok, lbl = self._admin()
        self.run("POST", "/api/auth/change-password/", "Changement MDP — non authentifié", 401, cat)
        self.run("POST", "/api/auth/change-password/", "Changement MDP — ancien MDP incorrect", 400, cat,
                 body={"old_password": "MAUVAIS", "new_password": "NewPass1234!", "new_password_confirm": "NewPass1234!"},
                 token=tok, auth_label=lbl)

        # ── 1.9 Administration utilisateurs ───────────────────────────────────
        tok, lbl = self._admin()
        self.run("GET", "/api/auth/admin/users/", "Liste users — admin", 200, cat, token=tok, auth_label=lbl)

        tok_u, lbl_u = self._user()
        self.run("GET", "/api/auth/admin/users/", "Liste users — user standard (doit être 403)", 403, cat,
                 token=tok_u, auth_label=lbl_u)

        self.run("GET", "/api/auth/admin/users/", "Liste users — non authentifié (doit être 401)", 401, cat)

        if self.suite.created_user_id:
            tok, lbl = self._admin()
            self.run("PATCH", f"/api/auth/admin/users/{self.suite.created_user_id}/",
                     "Modifier user via admin", 200, cat,
                     body={"is_verified": True}, token=tok, auth_label=lbl)

        # ── 1.10 Déconnexion ──────────────────────────────────────────────────
        # On crée un token frais pour le déconnecter sans invalider notre session
        r3 = self.run("POST", "/api/auth/login/", "Login pour test logout", 200, cat,
                      body={"email": USER_EMAIL or ADMIN_EMAIL, "password": USER_PASSWORD or ADMIN_PASSWORD})
        if r3.passed and r3.response_body:
            refresh_to_kill = r3.response_body.get("tokens", {}).get("refresh")
            access_to_kill  = r3.response_body.get("tokens", {}).get("access")
            if refresh_to_kill and access_to_kill:
                self.run("POST", "/api/auth/logout/", "Déconnexion — valide", 200, cat,
                         body={"refresh": refresh_to_kill},
                         token=access_to_kill, auth_label="ephemeral")

        self.run("POST", "/api/auth/logout/", "Déconnexion — non authentifié", 401, cat)

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 2 — Espaces
    # ════════════════════════════════════════════════════════════════════════

    def test_spaces(self):
        print(f"\n{Fore.CYAN}{'═'*65}")
        print("  PHASE 2 — Espaces (/api/spaces/)")
        print(f"{'═'*65}{Style.RESET_ALL if HAS_COLOR else ''}")

        cat = "espaces"

        # ── 2.1 Liste publique ────────────────────────────────────────────────
        r = self.run("GET", "/api/spaces/", "Liste espaces — public", 200, cat)
        if r.passed and isinstance(r.response_body, dict):
            results = r.response_body.get("results", [])
            if results and isinstance(results, list):
                self.suite.created_space_id = results[0].get("id")

        # Filtres
        self.run("GET", "/api/spaces/", "Filtre par type meeting_room", 200, cat,
                 params={"space_type": "meeting_room"})
        self.run("GET", "/api/spaces/", "Filtre disponibilité", 200, cat,
                 params={"is_available": "true"})
        self.run("GET", "/api/spaces/", "Filtre capacité min 5", 200, cat,
                 params={"capacity": "5"})
        self.run("GET", "/api/spaces/", "Recherche textuelle", 200, cat,
                 params={"search": "salle"})
        self.run("GET", "/api/spaces/", "Tri par prix/heure desc", 200, cat,
                 params={"ordering": "-price_per_hour"})
        self.run("GET", "/api/spaces/", "Pagination page 1", 200, cat,
                 params={"page": "1", "page_size": "5"})

        # ── 2.2 Détail ────────────────────────────────────────────────────────
        if self.suite.created_space_id:
            sid = self.suite.created_space_id
            self.run("GET", f"/api/spaces/{sid}/", "Détail espace existant", 200, cat)

        self.run("GET", "/api/spaces/99999/", "Détail espace inexistant", 404, cat)

        # ── 2.3 Disponibilité ────────────────────────────────────────────────
        if self.suite.created_space_id:
            sid = self.suite.created_space_id
            self.run("GET", f"/api/spaces/{sid}/availability/",
                     "Vérifier disponibilité — paramètres valides", 200, cat,
                     params={
                         "start_datetime": "2025-06-20T10:00:00Z",
                         "end_datetime":   "2025-06-20T12:00:00Z",
                         "billing_type":   "hourly",
                     })
            self.run("GET", f"/api/spaces/{sid}/availability/",
                     "Disponibilité — paramètres manquants", 400, cat)

        # ── 2.4 Créer un espace (admin) ───────────────────────────────────────
        tok, lbl = self._admin()
        space_payload = {
            "name":          f"Espace Test {int(time.time())}",
            "space_type":    "meeting_room",
            "description":   "Créé par le script de test automatisé",
            "capacity":      8,
            "price_per_hour": "3000.00",
            "price_per_day":  "20000.00",
            "address":       "Lomé, Togo",
            "is_available":  True,
        }
        r = self.run("POST", "/api/spaces/create/", "Créer espace — admin", 201, cat,
                     body=space_payload, token=tok, auth_label=lbl)
        if r.passed and r.response_body:
            new_space_id = r.response_body.get("id")
            if new_space_id:
                self.suite.created_space_id = self.suite.created_space_id or new_space_id

                # ── 2.5 Modifier l'espace ──────────────────────────────────────
                self.run("PUT", f"/api/spaces/{new_space_id}/update/",
                         "Modifier espace (PUT) — admin", 200, cat,
                         body={**space_payload, "capacity": 12}, token=tok, auth_label=lbl)

                self.run("PATCH", f"/api/spaces/{new_space_id}/update/",
                         "Modifier espace (PATCH) — admin", 200, cat,
                         body={"capacity": 15}, token=tok, auth_label=lbl)

                # ── 2.6 Upload photo ───────────────────────────────────────────
                # Note : multipart/form-data — test basique avec corps vide
                self.run("POST", f"/api/spaces/{new_space_id}/photos/",
                         "Upload photo — sans fichier (400 attendu)", 400, cat,
                         token=tok, auth_label=lbl)

                # ── 2.7 Supprimer l'espace ─────────────────────────────────────
                self.run("DELETE", f"/api/spaces/{new_space_id}/delete/",
                         "Supprimer espace — admin", 204, cat,
                         token=tok, auth_label=lbl)

        # ── 2.8 Permissions ───────────────────────────────────────────────────
        tok_u, lbl_u = self._user()
        self.run("POST", "/api/spaces/create/", "Créer espace — user (403)", 403, cat,
                 body=space_payload, token=tok_u, auth_label=lbl_u)
        self.run("POST", "/api/spaces/create/", "Créer espace — non auth (401)", 401, cat,
                 body=space_payload)

        # Payload invalide
        tok, lbl = self._admin()
        self.run("POST", "/api/spaces/create/", "Créer espace — payload invalide", 400, cat,
                 body={"name": ""}, token=tok, auth_label=lbl)

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 3 — Réservations
    # ════════════════════════════════════════════════════════════════════════

    def test_reservations(self):
        print(f"\n{Fore.CYAN}{'═'*65}")
        print("  PHASE 3 — Réservations (/api/reservations/)")
        print(f"{'═'*65}{Style.RESET_ALL if HAS_COLOR else ''}")

        cat = "réservations"
        tok_u, lbl_u = self._user()
        tok_a, lbl_a = self._admin()

        # ── 3.1 Liste des réservations ────────────────────────────────────────
        self.run("GET", "/api/reservations/", "Liste réservations — non auth (401)", 401, cat)
        self.run("GET", "/api/reservations/", "Liste réservations — user auth", 200, cat,
                 token=tok_u, auth_label=lbl_u)
        self.run("GET", "/api/reservations/", "Liste réservations — admin (tout voir)", 200, cat,
                 token=tok_a, auth_label=lbl_a)

        # ── 3.2 Créer une réservation ─────────────────────────────────────────
        if not self.suite.created_space_id:
            # Récupérer un space ID depuis la liste
            status_code, body, _, _ = self.client.request("GET", "/api/spaces/", token=None)
            if body and isinstance(body, dict):
                results = body.get("results", [])
                if results:
                    self.suite.created_space_id = results[0].get("id")

        self.run("POST", "/api/reservations/create/", "Créer réservation — non auth (401)", 401, cat,
                 body={"space": 1, "start_datetime": "2025-07-01T09:00:00Z",
                       "end_datetime": "2025-07-01T11:00:00Z", "billing_type": "hourly"})

        if self.suite.created_space_id:
            res_payload = {
                "space":          self.suite.created_space_id,
                "start_datetime": "2025-07-15T09:00:00Z",
                "end_datetime":   "2025-07-15T11:00:00Z",
                "billing_type":   "hourly",
                "notes":          "Réservation de test automatisé",
            }
            r = self.run("POST", "/api/reservations/create/",
                         "Créer réservation — user auth", 201, cat,
                         body=res_payload, token=tok_u, auth_label=lbl_u)
            if r.passed and r.response_body:
                self.suite.created_reservation_id = (
                    r.response_body.get("id")
                    or r.response_body.get("reservation", {}).get("id")
                )

            # Payload invalide
            self.run("POST", "/api/reservations/create/", "Créer réservation — dates manquantes", 400, cat,
                     body={"space": self.suite.created_space_id, "billing_type": "hourly"},
                     token=tok_u, auth_label=lbl_u)

            # Dates passées
            self.run("POST", "/api/reservations/create/", "Créer réservation — dates passées", 400, cat,
                     body={**res_payload, "start_datetime": "2020-01-01T09:00:00Z",
                           "end_datetime": "2020-01-01T11:00:00Z"},
                     token=tok_u, auth_label=lbl_u)

        # ── 3.3 Détail + modifier + annuler ───────────────────────────────────
        if self.suite.created_reservation_id:
            rid = self.suite.created_reservation_id

            self.run("GET", f"/api/reservations/{rid}/",
                     "Détail réservation — propriétaire", 200, cat,
                     token=tok_u, auth_label=lbl_u)
            self.run("GET", f"/api/reservations/{rid}/",
                     "Détail réservation — non auth (401)", 401, cat)

            self.run("PATCH", f"/api/reservations/{rid}/update/",
                     "Modifier réservation (PATCH)", 200, cat,
                     body={"notes": "Notes modifiées par test"},
                     token=tok_u, auth_label=lbl_u)

            self.run("PUT", f"/api/reservations/{rid}/update/",
                     "Modifier réservation (PUT)", 200, cat,
                     body={
                         "space":          self.suite.created_space_id,
                         "start_datetime": "2025-07-15T10:00:00Z",
                         "end_datetime":   "2025-07-15T12:00:00Z",
                         "billing_type":   "hourly",
                         "notes":          "Notes PUT",
                     },
                     token=tok_u, auth_label=lbl_u)

            # Annuler
            r_cancel = self.run("POST", f"/api/reservations/{rid}/cancel/",
                                "Annuler réservation — propriétaire", 200, cat,
                                token=tok_u, auth_label=lbl_u)

        self.run("GET", "/api/reservations/99999/",
                 "Détail réservation inexistante (404)", 404, cat,
                 token=tok_u, auth_label=lbl_u)

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 4 — Paiements
    # ════════════════════════════════════════════════════════════════════════

    def test_payments(self):
        print(f"\n{Fore.CYAN}{'═'*65}")
        print("  PHASE 4 — Paiements (/api/payments/)")
        print(f"{'═'*65}{Style.RESET_ALL if HAS_COLOR else ''}")

        cat = "paiements"
        tok_u, lbl_u = self._user()
        tok_a, lbl_a = self._admin()

        # On a besoin d'une réservation valide — en créer une fraîche si absente
        if not self.suite.created_reservation_id and self.suite.created_space_id:
            ts = int(time.time())
            payload = {
                "space":          self.suite.created_space_id,
                "start_datetime": f"2025-08-0{(ts % 9) + 1}T09:00:00Z",
                "end_datetime":   f"2025-08-0{(ts % 9) + 1}T11:00:00Z",
                "billing_type":   "hourly",
                "notes":          "Réservation pour test paiement",
            }
            sc, body, _, _ = self.client.request("POST", "/api/reservations/create/",
                                                  token=tok_u, body=payload)
            if sc == 201 and body:
                self.suite.created_reservation_id = body.get("id") or body.get("reservation", {}).get("id")

        # ── 4.1 Créer paiement — non auth ────────────────────────────────────
        self.run("POST", "/api/payments/create/", "Créer paiement — non auth (401)", 401, cat,
                 body={"reservation": 1, "amount": "5000.00", "method": "cash"})

        # ── 4.2 Créer paiement cash (local) ──────────────────────────────────
        if self.suite.created_reservation_id:
            rid = self.suite.created_reservation_id
            r = self.run("POST", "/api/payments/create/",
                         "Créer paiement cash — user (pending)", 201, cat,
                         body={"reservation_id": rid, "method": "cash"},
                         token=tok_u, auth_label=lbl_u)
            if r.passed and r.response_body:
                pay = r.response_body.get("payment", r.response_body)
                self.suite.created_payment_id = pay.get("id")

        # ── 4.3 Créer paiement carte (Stripe) ────────────────────────────────
        # On s'attend à 201 si le serveur tourne et que Stripe est configuré,
        # ou à 400 si la clé Stripe n'est pas renseignée (test mode sans clé)
        if self.suite.created_reservation_id:
            rid = self.suite.created_reservation_id
            self.run("POST", "/api/payments/create/",
                     "Créer paiement carte Stripe (201 ou 400 si clé absente)", 201, cat,
                     body={"reservation_id": rid, "method": "card"},
                     token=tok_u, auth_label=lbl_u)

        # ── 4.4 Payload invalide ──────────────────────────────────────────────
        self.run("POST", "/api/payments/create/", "Créer paiement — méthode invalide", 400, cat,
                 body={"reservation_id": 1, "method": "bitcoin"},
                 token=tok_u, auth_label=lbl_u)

        self.run("POST", "/api/payments/create/", "Créer paiement — réservation inexistante", 404, cat,
                 body={"reservation_id": 99999, "method": "cash"},
                 token=tok_u, auth_label=lbl_u)

        # ── 4.5 Liste des paiements ───────────────────────────────────────────
        self.run("GET", "/api/payments/", "Liste paiements — non auth (401)", 401, cat)
        self.run("GET", "/api/payments/", "Liste paiements — user", 200, cat,
                 token=tok_u, auth_label=lbl_u)
        self.run("GET", "/api/payments/", "Liste paiements — admin", 200, cat,
                 token=tok_a, auth_label=lbl_a)
        self.run("GET", "/api/payments/", "Filtre paiements par statut", 200, cat,
                 params={"status": "pending"}, token=tok_u, auth_label=lbl_u)
        self.run("GET", "/api/payments/", "Filtre paiements par méthode", 200, cat,
                 params={"method": "cash"}, token=tok_u, auth_label=lbl_u)

        # ── 4.6 Détail ────────────────────────────────────────────────────────
        if self.suite.created_payment_id:
            pid = self.suite.created_payment_id
            self.run("GET", f"/api/payments/{pid}/", "Détail paiement — propriétaire", 200, cat,
                     token=tok_u, auth_label=lbl_u)
            self.run("GET", f"/api/payments/{pid}/", "Détail paiement — non auth (401)", 401, cat)

            # ── 4.7 Stripe confirm ─────────────────────────────────────────────
            self.run("POST", f"/api/payments/{pid}/stripe-confirm/",
                     "Stripe confirm — paiement cash (400 attendu)", 400, cat,
                     token=tok_u, auth_label=lbl_u)

            # ── 4.8 Confirm admin (méthode locale) ────────────────────────────
            self.run("PATCH", f"/api/payments/{pid}/confirm/",
                     "Confirm admin — paiement cash → completed", 200, cat,
                     body={"status": "completed"},
                     token=tok_a, auth_label=lbl_a)

            # ── 4.9 Facture ───────────────────────────────────────────────────
            self.run("GET", f"/api/payments/{pid}/invoice/",
                     "Télécharger facture — paiement complété", 200, cat,
                     token=tok_u, auth_label=lbl_u)

            # ── 4.10 Remboursement ─────────────────────────────────────────────
            self.run("POST", f"/api/payments/{pid}/refund/",
                     "Remboursement — non admin (403)", 403, cat,
                     body={"amount": "1000.00"},
                     token=tok_u, auth_label=lbl_u)

            self.run("POST", f"/api/payments/{pid}/refund/",
                     "Remboursement total — admin", 200, cat,
                     token=tok_a, auth_label=lbl_a)

            # Déjà remboursé
            self.run("POST", f"/api/payments/{pid}/refund/",
                     "Remboursement — déjà remboursé (400)", 400, cat,
                     token=tok_a, auth_label=lbl_a)

        self.run("GET", "/api/payments/99999/", "Détail paiement inexistant (404)", 404, cat,
                 token=tok_u, auth_label=lbl_u)

        # ── 4.11 Statistiques ─────────────────────────────────────────────────
        self.run("GET", "/api/payments/stats/", "Stats paiements — admin", 200, cat,
                 token=tok_a, auth_label=lbl_a)
        self.run("GET", "/api/payments/stats/", "Stats paiements — user (403)", 403, cat,
                 token=tok_u, auth_label=lbl_u)
        self.run("GET", "/api/payments/stats/", "Stats paiements — non auth (401)", 401, cat)

        # ── 4.12 Webhook Stripe ───────────────────────────────────────────────
        self.run("POST", "/api/payments/webhook/",
                 "Webhook Stripe — sans signature (400)", 400, cat,
                 raw_body=b'{"type":"test"}')

        self.run("POST", "/api/payments/webhook/",
                 "Webhook Stripe — signature invalide (400)", 400, cat,
                 raw_body=b'{"type":"test"}',
                 extra_headers={"Stripe-Signature": "t=bad,v1=invalid"})

        self.run("GET", "/api/payments/webhook/",
                 "Webhook — méthode GET (405)", 405, cat)

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 5 — Notifications
    # ════════════════════════════════════════════════════════════════════════

    def test_notifications(self):
        print(f"\n{Fore.CYAN}{'═'*65}")
        print("  PHASE 5 — Notifications (/api/notifications/)")
        print(f"{'═'*65}{Style.RESET_ALL if HAS_COLOR else ''}")

        cat = "notifications"
        tok_u, lbl_u = self._user()
        tok_a, lbl_a = self._admin()

        # ── 5.1 Liste ─────────────────────────────────────────────────────────
        self.run("GET", "/api/notifications/", "Liste notifications — non auth (401)", 401, cat)
        r = self.run("GET", "/api/notifications/", "Liste notifications — user", 200, cat,
                     token=tok_u, auth_label=lbl_u)

        notif_id = None
        if r.passed and r.response_body:
            body = r.response_body
            results = body.get("results", body) if isinstance(body, dict) else body
            if isinstance(results, list) and results:
                notif_id = results[0].get("id")

        # ── 5.2 Marquer tout comme lu ─────────────────────────────────────────
        self.run("PUT", "/api/notifications/read/",
                 "Marquer tout comme lu — user", 200, cat,
                 token=tok_u, auth_label=lbl_u)
        self.run("PUT", "/api/notifications/read/",
                 "Marquer tout comme lu — non auth (401)", 401, cat)

        # ── 5.3 Marquer une notification spécifique ───────────────────────────
        if notif_id:
            self.run("PUT", f"/api/notifications/{notif_id}/read/",
                     f"Marquer notification #{notif_id} comme lue", 200, cat,
                     token=tok_u, auth_label=lbl_u)

        self.run("PUT", "/api/notifications/99999/read/",
                 "Marquer notification inexistante (404)", 404, cat,
                 token=tok_u, auth_label=lbl_u)

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 6 — Administration
    # ════════════════════════════════════════════════════════════════════════

    def test_admin(self):
        print(f"\n{Fore.CYAN}{'═'*65}")
        print("  PHASE 6 — Administration (/api/admin/)")
        print(f"{'═'*65}{Style.RESET_ALL if HAS_COLOR else ''}")

        cat = "admin"
        tok_a, lbl_a = self._admin()
        tok_u, lbl_u = self._user()

        # ── 6.1 Dashboard ─────────────────────────────────────────────────────
        self.run("GET", "/api/admin/dashboard/", "Dashboard — admin", 200, cat,
                 token=tok_a, auth_label=lbl_a)
        self.run("GET", "/api/admin/dashboard/", "Dashboard — user (403)", 403, cat,
                 token=tok_u, auth_label=lbl_u)
        self.run("GET", "/api/admin/dashboard/", "Dashboard — non auth (401)", 401, cat)

        # ── 6.2 Export CSV ────────────────────────────────────────────────────
        self.run("GET", "/api/admin/export/reservations/", "Export CSV réservations — admin", 200, cat,
                 token=tok_a, auth_label=lbl_a)
        self.run("GET", "/api/admin/export/reservations/", "Export CSV — user (403)", 403, cat,
                 token=tok_u, auth_label=lbl_u)
        self.run("GET", "/api/admin/export/reservations/", "Export CSV — non auth (401)", 401, cat)

    # ════════════════════════════════════════════════════════════════════════
    # PHASE 7 — Tests de robustesse & edge cases
    # ════════════════════════════════════════════════════════════════════════

    def test_robustness(self):
        print(f"\n{Fore.CYAN}{'═'*65}")
        print("  PHASE 7 — Robustesse & Edge Cases")
        print(f"{'═'*65}{Style.RESET_ALL if HAS_COLOR else ''}")

        cat = "robustesse"
        tok_u, lbl_u = self._user()

        # ── 7.1 Méthodes HTTP non autorisées ─────────────────────────────────
        self.run("DELETE", "/api/auth/login/", "DELETE sur login (405)", 405, cat)
        self.run("PUT",    "/api/spaces/",     "PUT sur liste espaces (405)", 405, cat,
                 token=tok_u, auth_label=lbl_u)
        self.run("PATCH",  "/api/spaces/",     "PATCH sur liste espaces (405)", 405, cat,
                 token=tok_u, auth_label=lbl_u)

        # ── 7.2 Token invalide / expiré ───────────────────────────────────────
        self.run("GET", "/api/auth/profile/", "Profile — token malformé (401)", 401, cat,
                 token="not.a.valid.jwt.token")
        self.run("GET", "/api/spaces/", "Espaces — token invalide tolère (200 ou 401)", 200, cat,
                 token="invalid_token")

        # ── 7.3 Injections / payloads extrêmes ────────────────────────────────
        tok_a, lbl_a = self._admin()
        self.run("POST", "/api/spaces/create/", "Payload — champs vides", 400, cat,
                 body={}, token=tok_a, auth_label=lbl_a)
        self.run("POST", "/api/spaces/create/", "Payload — string au lieu d'int pour capacity", 400, cat,
                 body={"name": "Test", "space_type": "desk", "capacity": "abc",
                       "price_per_hour": "100", "price_per_day": "500"},
                 token=tok_a, auth_label=lbl_a)
        self.run("POST", "/api/auth/register/", "Injection SQL dans email", 400, cat,
                 body={"email": "'; DROP TABLE users; --", "username": "hacker",
                       "password": "pass", "password_confirm": "pass"})

        # ── 7.4 IDs invalides ────────────────────────────────────────────────
        self.run("GET",    "/api/spaces/abc/",        "ID non-entier pour space (404)", 404, cat)
        self.run("GET",    "/api/reservations/0/",    "ID=0 pour réservation (404)", 404, cat,
                 token=tok_u, auth_label=lbl_u)
        self.run("GET",    "/api/payments/-1/",       "ID négatif pour paiement (404)", 404, cat,
                 token=tok_u, auth_label=lbl_u)

        # ── 7.5 Endpoints inexistants ────────────────────────────────────────
        self.run("GET", "/api/inexistant/", "Route inexistante (404)", 404, cat)
        self.run("GET", "/api/",           "Racine API (200 ou 404)", 200, cat)

    # ════════════════════════════════════════════════════════════════════════
    # EXÉCUTION GLOBALE
    # ════════════════════════════════════════════════════════════════════════

    def run_all(self) -> TestSuite:
        print(f"\n{'═'*65}")
        print(f"  COWORKING API — TEST COMPLET DES ENDPOINTS")
        print(f"  Cible : {BASE_URL}")
        print(f"  Démarré : {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"{'═'*65}")

        server_ok = self.test_server_health()
        if not server_ok:
            self.suite.end_time = datetime.datetime.now()
            return self.suite

        self.test_auth()
        self.test_spaces()
        self.test_reservations()
        self.test_payments()
        self.test_notifications()
        self.test_admin()
        self.test_robustness()

        self.suite.end_time = datetime.datetime.now()
        return self.suite


# ════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION DU RAPPORT MARKDOWN
# ════════════════════════════════════════════════════════════════════════════

def generate_report(suite: TestSuite) -> str:
    duration = (suite.end_time - suite.start_time).total_seconds() if suite.end_time else 0

    lines = []
    a = lines.append

    # ── En-tête ───────────────────────────────────────────────────────────────
    a("# 📊 Rapport de Tests — Coworking API")
    a("")
    a(f"> Généré le **{suite.start_time.strftime('%d/%m/%Y à %H:%M:%S')}**")
    a(f"> Durée totale : **{duration:.1f}s**  |  Cible : `{BASE_URL}`")
    a("")

    # ── Résumé global ─────────────────────────────────────────────────────────
    a("## 📈 Résumé global")
    a("")
    a("| Indicateur | Valeur |")
    a("|---|---|")
    a(f"| Tests exécutés | **{suite.total}** |")
    a(f"| ✅ Réussis | **{suite.passed}** |")
    a(f"| ❌ Échoués | **{suite.failed}** |")
    a(f"| 💥 Erreurs réseau/connexion | **{suite.errors}** |")
    a(f"| ⚠️  Avertissements (auth inattendue) | **{suite.warnings}** |")
    a(f"| 🎯 Taux de réussite | **{suite.success_rate:.1f}%** |")
    a(f"| ⏱️  Temps moyen de réponse | **{suite.avg_response_time:.1f}ms** |")
    a("")

    # Barre de progression ASCII
    filled = int(suite.success_rate / 5)  # 20 blocs = 100%
    bar = "█" * filled + "░" * (20 - filled)
    a(f"```")
    a(f"Progression  [{bar}] {suite.success_rate:.1f}%")
    a(f"```")
    a("")

    # ── Résultats par catégorie ────────────────────────────────────────────────
    a("## 📂 Résultats par catégorie")
    a("")

    CATEGORY_ICONS = {
        "infra": "🏗️", "auth": "🔐", "espaces": "🏢",
        "réservations": "📅", "paiements": "💳", "notifications": "🔔",
        "admin": "👑", "robustesse": "🛡️", "général": "📋",
    }

    for cat, results in suite.by_category().items():
        icon = CATEGORY_ICONS.get(cat, "📋")
        cat_passed = sum(1 for r in results if r.passed)
        cat_total = len(results)
        cat_rate = cat_passed / cat_total * 100 if cat_total else 0

        a(f"### {icon} {cat.capitalize()} — {cat_passed}/{cat_total} ({cat_rate:.0f}%)")
        a("")
        a("| # | Méthode | Endpoint | Description | Attendu | Réel | Temps | Auth | Statut |")
        a("|---|---------|----------|-------------|---------|------|-------|------|--------|")

        for i, r in enumerate(results, 1):
            method_fmt  = f"`{r.method}`"
            endpoint_fmt = f"`{r.endpoint}`"
            actual_str  = str(r.actual_status) if r.actual_status else "N/A"
            time_str    = f"{r.response_time_ms:.0f}ms"
            icon_status = r.status_icon

            desc_short = r.description[:55] + ("…" if len(r.description) > 55 else "")
            a(f"| {i} | {method_fmt} | {endpoint_fmt} | {desc_short} | `{r.expected_status}` | `{actual_str}` | {time_str} | {r.auth_used} | {icon_status} |")

        a("")

    # ── Détail des échecs ──────────────────────────────────────────────────────
    failures = [r for r in suite.results if not r.passed]
    if failures:
        a("## 🔍 Détail des échecs et erreurs")
        a("")

        for i, r in enumerate(failures, 1):
            a(f"### {i}. {r.status_icon} `{r.method} {r.endpoint}`")
            a("")
            a(f"- **Description :** {r.description}")
            a(f"- **Catégorie :** {r.category}")
            a(f"- **Statut attendu :** `{r.expected_status}`")
            a(f"- **Statut reçu :** `{r.actual_status or 'N/A'}`")
            a(f"- **Temps :** {r.response_time_ms:.1f}ms")
            a(f"- **Auth utilisée :** {r.auth_used}")
            if r.error:
                a(f"- **Erreur :** {r.error}")
            if r.response_body:
                preview = json.dumps(r.response_body, ensure_ascii=False, indent=2)[:600]
                a(f"- **Réponse :**")
                a(f"```json")
                a(preview)
                a(f"```")
            a("")

    # ── Performances ───────────────────────────────────────────────────────────
    a("## ⚡ Performances")
    a("")
    timed = sorted(
        [r for r in suite.results if r.response_time_ms > 0],
        key=lambda r: r.response_time_ms,
        reverse=True
    )

    a("### 🐢 Top 10 endpoints les plus lents")
    a("")
    a("| Rang | Endpoint | Méthode | Temps |")
    a("|------|----------|---------|-------|")
    for i, r in enumerate(timed[:10], 1):
        flag = " 🔴" if r.response_time_ms > 2000 else (" 🟡" if r.response_time_ms > 500 else " 🟢")
        a(f"| {i} | `{r.endpoint}` | `{r.method}` | {r.response_time_ms:.0f}ms{flag} |")
    a("")

    a("### ⚡ Top 5 endpoints les plus rapides")
    a("")
    a("| Rang | Endpoint | Méthode | Temps |")
    a("|------|----------|---------|-------|")
    for i, r in enumerate(reversed(timed[-5:]), 1):
        a(f"| {i} | `{r.endpoint}` | `{r.method}` | {r.response_time_ms:.0f}ms |")
    a("")

    # ── Distribution des codes HTTP ────────────────────────────────────────────
    a("## 📊 Distribution des codes HTTP retournés")
    a("")
    code_counts: dict = {}
    for r in suite.results:
        key = str(r.actual_status or "ERR")
        code_counts[key] = code_counts.get(key, 0) + 1

    a("| Code HTTP | Occurrences | Signification |")
    a("|-----------|-------------|---------------|")
    HTTP_MEANINGS = {
        "200": "OK", "201": "Created", "204": "No Content",
        "400": "Bad Request", "401": "Unauthorized", "403": "Forbidden",
        "404": "Not Found", "405": "Method Not Allowed",
        "429": "Too Many Requests", "500": "Internal Server Error",
        "ERR": "Erreur réseau/connexion",
    }
    for code, count in sorted(code_counts.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
        meaning = HTTP_MEANINGS.get(code, "—")
        a(f"| `{code}` | {count} | {meaning} |")
    a("")

    # ── Couverture des endpoints ───────────────────────────────────────────────
    a("## 🗺️ Couverture des endpoints")
    a("")
    unique_endpoints = set(r.endpoint for r in suite.results)
    a(f"**{len(unique_endpoints)} endpoints uniques testés** :")
    a("")
    for ep in sorted(unique_endpoints):
        methods = set(r.method for r in suite.results if r.endpoint == ep)
        methods_str = " ".join(f"`{m}`" for m in sorted(methods))
        a(f"- `{ep}` — {methods_str}")
    a("")

    # ── Recommandations ────────────────────────────────────────────────────────
    a("## 💡 Recommandations")
    a("")

    recs = []

    # Erreurs 5xx
    server_errors = [r for r in suite.results if r.actual_status and r.actual_status >= 500]
    if server_errors:
        recs.append(
            f"🔴 **{len(server_errors)} erreur(s) serveur (5xx)** détectée(s) — "
            f"vérifiez les logs Django : `python manage.py runserver` ou `journalctl`"
        )

    # Endpoints très lents
    slow = [r for r in suite.results if r.response_time_ms > 2000]
    if slow:
        recs.append(
            f"🟡 **{len(slow)} endpoint(s) lent(s)** (>2s) — "
            f"envisagez `select_related()`, `prefetch_related()` ou du cache"
        )

    # Erreurs réseau
    if suite.errors > 0:
        recs.append(
            f"💥 **{suite.errors} erreur(s) réseau** — "
            f"vérifiez que le serveur est lancé sur `{BASE_URL}`"
        )

    # Pas de token admin
    if not suite.admin_token:
        recs.append(
            "⚠️ **Token admin non obtenu** — "
            f"vérifiez que le compte `{ADMIN_EMAIL}` existe avec le mot de passe `{ADMIN_PASSWORD}`. "
            "Créez-le : `python manage.py createsuperuser`"
        )

    # Taux de réussite faible
    if suite.success_rate < 70:
        recs.append(
            f"❌ **Taux de réussite faible ({suite.success_rate:.0f}%)** — "
            "de nombreux endpoints retournent un statut inattendu. "
            "Consultez la section 'Détail des échecs' ci-dessus."
        )
    elif suite.success_rate >= 90:
        recs.append(
            f"✅ **Excellent taux de réussite ({suite.success_rate:.0f}%)** — "
            "le backend est en bonne santé !"
        )

    if not recs:
        recs.append("✅ Aucun problème critique détecté.")

    for rec in recs:
        a(f"- {rec}")

    a("")

    # ── Configuration de test ──────────────────────────────────────────────────
    a("## ⚙️ Configuration du test")
    a("")
    a("```")
    a(f"BASE_URL      : {BASE_URL}")
    a(f"ADMIN_EMAIL   : {ADMIN_EMAIL}")
    a(f"USER_EMAIL    : {USER_EMAIL}")
    a(f"TIMEOUT       : {TIMEOUT}s")
    a(f"Démarré       : {suite.start_time.strftime('%d/%m/%Y %H:%M:%S')}")
    a(f"Terminé       : {suite.end_time.strftime('%d/%m/%Y %H:%M:%S') if suite.end_time else 'N/A'}")
    a(f"Durée totale  : {duration:.1f}s")
    a("```")
    a("")
    a("---")
    a("*Rapport généré automatiquement par `test_api.py`*")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# AFFICHAGE CONSOLE DU RÉSUMÉ FINAL
# ════════════════════════════════════════════════════════════════════════════

def print_summary(suite: TestSuite):
    duration = (suite.end_time - suite.start_time).total_seconds() if suite.end_time else 0

    print(f"\n{'═'*65}")
    print(f"  RÉSUMÉ FINAL")
    print(f"{'═'*65}")

    color = Fore.GREEN if suite.success_rate >= 90 else (Fore.YELLOW if suite.success_rate >= 70 else Fore.RED)
    print(f"  {color}Taux de réussite : {suite.success_rate:.1f}%{Style.RESET_ALL if HAS_COLOR else ''}")
    print(f"  ✅ Réussis         : {suite.passed}")
    print(f"  ❌ Échoués         : {suite.failed}")
    print(f"  💥 Erreurs réseau  : {suite.errors}")
    print(f"  ⏱️  Temps moyen     : {suite.avg_response_time:.1f}ms")
    print(f"  ⏱️  Durée totale    : {duration:.1f}s")
    print(f"  📋 Total tests     : {suite.total}")

    print(f"\n{'═'*65}")

    failures = [r for r in suite.results if not r.passed]
    if failures:
        print(f"\n  {Fore.RED}ÉCHECS DÉTECTÉS :{Style.RESET_ALL if HAS_COLOR else ''}")
        for r in failures[:15]:  # Limiter l'affichage console
            print(f"    ❌ {r.method:<7} {r.endpoint:<50} "
                  f"attendu={r.expected_status} reçu={r.actual_status or 'ERR'}")
        if len(failures) > 15:
            print(f"    ... et {len(failures) - 15} autre(s) — voir le rapport Markdown")

    print(f"\n  📄 Rapport complet : {Fore.CYAN}{REPORT_FILE}{Style.RESET_ALL if HAS_COLOR else ''}\n")


# ════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ════════════════════════════════════════════════════════════════════════════

def main():
    tester = EndpointTester(BASE_URL)
    suite  = tester.run_all()

    print_summary(suite)

    report = generate_report(suite)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"  ✅ Rapport sauvegardé dans : {REPORT_FILE.resolve()}\n")

    # Code de retour OS : 0 si ≥ 80% de réussite, 1 sinon (utile pour CI/CD)
    sys.exit(0 if suite.success_rate >= 80 else 1)


if __name__ == "__main__":
    main()
