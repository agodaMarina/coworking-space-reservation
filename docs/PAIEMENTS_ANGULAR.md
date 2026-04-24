# Intégration Paiements — Guide Angular

> Backend Django · API REST · Base URL : `http://localhost:8000`  
> Authentification : **JWT Bearer Token** requis sur tous les endpoints (sauf webhooks)

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Authentification](#2-authentification)
3. [Modèle Payment](#3-modèle-payment)
4. [Paiement par carte — Stripe](#4-paiement-par-carte--stripe)
5. [Paiement Mobile Money — FedaPay](#5-paiement-mobile-money--fedapay)
6. [Paiements locaux — Cash / Virement](#6-paiements-locaux--cash--virement)
7. [Endpoints de gestion](#7-endpoints-de-gestion)
8. [Gestion des erreurs](#8-gestion-des-erreurs)
9. [Service Angular complet](#9-service-angular-complet)
10. [Composant de paiement Angular](#10-composant-de-paiement-angular)

---

## 1. Vue d'ensemble

Quatre méthodes de paiement sont disponibles :

| Méthode | Valeur API | Passerelle | Flux |
|---|---|---|---|
| Carte bancaire | `card` | Stripe | Backend → `client_secret` → Stripe.js confirme |
| Mobile Money | `mobile_money` | FedaPay | Backend → `payment_url` → redirection FedaPay |
| Espèces | `cash` | Local | En attente validation admin |
| Virement bancaire | `bank_transfer` | Local | En attente validation admin |

**Devise** : Tous les montants sont en **XOF (FCFA)**. Stripe les convertit en EUR en interne (1 EUR = 655.957 XOF). FedaPay supporte XOF nativement.

---

## 2. Authentification

Chaque requête doit inclure le header :

```http
Authorization: Bearer <access_token>
```

Obtenir un token :

```http
POST /api/auth/login/
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "motdepasse"
}
```

**Réponse :**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

---

## 3. Modèle Payment

Objet retourné par tous les endpoints de paiement :

```typescript
interface Payment {
  id: number;
  user_email: string;
  reservation_info: {
    id: number;
    space: string;
    start: string;   // ISO 8601
    end: string;
  };
  amount: string;          // ex: "15000.00" (XOF)
  currency: string;        // "XOF"
  status: 'pending' | 'completed' | 'failed' | 'refunded' | 'cancelled';
  status_display: string;  // "En attente" | "Complété" | ...
  method: 'card' | 'mobile_money' | 'cash' | 'bank_transfer';
  method_display: string;
  transaction_id: string;  // "pi_xxx" (Stripe) | "FEDA-xxx" (FedaPay) | "TXN-xxx" (local)
  paid_at: string | null;  // ISO 8601
  created_at: string;
}
```

---

## 4. Paiement par carte — Stripe

### Pré-requis
Installer Stripe.js dans `index.html` ou via `@stripe/stripe-js` :
```html
<script src="https://js.stripe.com/v3/"></script>
```
ou
```bash
npm install @stripe/stripe-js
```

### Étape 1 — Créer le PaymentIntent (backend)

```http
POST /api/payments/create/
Authorization: Bearer <token>
Content-Type: application/json

{
  "reservation_id": 42,
  "method": "card"
}
```

**Réponse 201 :**
```json
{
  "message": "PaymentIntent créé. Confirmez le paiement via Stripe.js.",
  "payment": { ...Payment },
  "stripe": {
    "client_secret": "pi_3Px...._secret_...",
    "publishable_key": "pk_test_...",
    "payment_intent_id": "pi_3Px...",
    "amount_xof": "15000.00",
    "amount_eur_cents": 2286,
    "note": "1 EUR = 655.957 XOF (parité fixe CFA)"
  }
}
```

### Étape 2 — Confirmer le paiement (frontend Stripe.js)

```typescript
import { loadStripe } from '@stripe/stripe-js';

const stripe = await loadStripe(response.stripe.publishable_key);

const { error, paymentIntent } = await stripe.confirmCardPayment(
  response.stripe.client_secret,
  {
    payment_method: {
      card: cardElement,   // Stripe Elements card element
      billing_details: { name: 'Nom du client' },
    },
  }
);

if (error) {
  // Afficher l'erreur à l'utilisateur
  console.error(error.message);
} else if (paymentIntent.status === 'succeeded') {
  // Étape 3 : confirmer côté backend
  await this.confirmStripePayment(paymentId);
}
```

### Étape 3 — Confirmer côté serveur

```http
POST /api/payments/{payment_id}/stripe-confirm/
Authorization: Bearer <token>
```

**Réponse 200 :**
```json
{
  "message": "Paiement confirmé avec succès ✅",
  "stripe_status": "succeeded",
  "paid": true,
  "payment": { ...Payment }
}
```

> **Important** : Ne jamais marquer un paiement comme réussi uniquement sur la base du retour Stripe.js frontend. Cette étape de confirmation serveur est obligatoire.

### Flux complet Stripe (diagramme)

```
Angular                    Django                    Stripe
  |                          |                          |
  |-- POST /create/ -------> |                          |
  |                          |-- create PaymentIntent ->|
  |                          |<-- client_secret --------|
  |<-- { client_secret } ----|                          |
  |                          |                          |
  |-- stripe.confirmCardPayment(client_secret) -------> |
  |<-- { paymentIntent: succeeded } -------------------|
  |                          |                          |
  |-- POST /stripe-confirm/->|                          |
  |                          |-- retrieve PaymentIntent->|
  |                          |<-- { status: succeeded }--|
  |                          |-- Payment.status=completed|
  |<-- { paid: true } -------|                          |
```

---

## 5. Paiement Mobile Money — FedaPay

Supporte : **Flooz (MTN)** et **T-Money (Moov)** — Togo, Bénin et autres pays UEMOA.

### Étape 1 — Créer la transaction

```http
POST /api/payments/create/
Authorization: Bearer <token>
Content-Type: application/json

{
  "reservation_id": 42,
  "method": "mobile_money",
  "phone_number": "+22890123456",
  "operator": "mtn"
}
```

**Champs Mobile Money :**

| Champ | Type | Requis | Description |
|---|---|---|---|
| `phone_number` | string | **Oui** | Numéro avec indicatif : `+22890123456` (Togo MTN) |
| `operator` | string | Non | `"mtn"` (Flooz) ou `"moov"` (T-Money). Défaut : `"mtn"` |

**Indicatifs pays supportés :**
- Togo : `+228`
- Bénin : `+229`
- Côte d'Ivoire : `+225`
- Sénégal : `+221`
- Burkina Faso : `+226`

**Réponse 201 :**
```json
{
  "message": "Transaction Mobile Money créée. Redirigez l'utilisateur vers l'URL de paiement...",
  "payment": { ...Payment, "status": "pending", "transaction_id": "FEDA-12345" },
  "fedapay": {
    "transaction_id": "FEDA-12345",
    "operator": "Flooz (MTN)",
    "payment_url": "https://me.fedapay.com/checkout/...",
    "note": "Validez le paiement sur votre téléphone. Le statut sera mis à jour automatiquement via webhook."
  }
}
```

### Étape 2 — Rediriger vers la page FedaPay

```typescript
// Option A : redirection dans le même onglet
window.location.href = response.fedapay.payment_url;

// Option B : ouvrir dans un nouvel onglet
window.open(response.fedapay.payment_url, '_blank');

// Option C : iframe / modal (recommandé pour UX)
// Ouvrir payment_url dans un iframe ou une bottom sheet Angular Material
```

### Étape 3 — Vérifier le statut après retour

L'utilisateur est redirigé vers `FEDAPAY_CALLBACK_URL` (configuré dans `.env`) après paiement.  
Votre route Angular de callback doit récupérer le statut du paiement :

```http
GET /api/payments/{payment_id}/
Authorization: Bearer <token>
```

Vérifier `payment.status` :
- `"completed"` → paiement confirmé (webhook reçu)
- `"pending"` → en attente (polling ou message d'attente)
- `"failed"` → paiement refusé

### Flux complet FedaPay (diagramme)

```
Angular                    Django                    FedaPay
  |                          |                          |
  |-- POST /create/ -------> |                          |
  |                          |-- POST /transactions --> |
  |                          |<-- { id, receipt_url }---|
  |<-- { payment_url } ------|                          |
  |                          |                          |
  |-- redirect payment_url --------------------------> |
  |                       (utilisateur paie sur FedaPay)|
  |<-- redirect CALLBACK_URL -------------------------|
  |                          |<-- POST fedapay-webhook--|
  |                          |    (transaction.approved)|
  |                          |-- Payment.status=completed
  |                          |                          |
  |-- GET /payments/{id}/ -> |                          |
  |<-- { status: completed }-|                          |
```

### Polling du statut (optionnel)

Si l'utilisateur revient sur votre app sans que le webhook ne soit encore arrivé :

```typescript
async pollPaymentStatus(paymentId: number, maxAttempts = 10): Promise<Payment> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 3000)); // attendre 3s
    const payment = await this.getPayment(paymentId);
    if (payment.status !== 'pending') return payment;
  }
  throw new Error('Timeout: paiement en attente de confirmation');
}
```

---

## 6. Paiements locaux — Cash / Virement

Ces méthodes ne font pas appel à une API externe. Le paiement est enregistré en `pending` et nécessite une **validation manuelle par l'admin**.

### Créer un paiement cash ou virement

```http
POST /api/payments/create/
Authorization: Bearer <token>
Content-Type: application/json

{
  "reservation_id": 42,
  "method": "cash"
}
```

ou `"method": "bank_transfer"` pour un virement.

**Réponse 201 :**
```json
{
  "message": "Paiement enregistré. En attente de validation par l'administrateur.",
  "payment": { ...Payment, "status": "pending", "transaction_id": "TXN-A3F2B9C1E8D4" }
}
```

**Aucune action frontend supplémentaire requise.** L'admin valide depuis le back-office, ce qui déclenche une notification email à l'utilisateur.

---

## 7. Endpoints de gestion

### Lister les paiements de l'utilisateur connecté

```http
GET /api/payments/
Authorization: Bearer <token>
```

Filtres disponibles : `?status=pending` · `?status=completed` · `?method=mobile_money`

**Réponse 200 :**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [ ...Payment[] ]
}
```

### Détail d'un paiement

```http
GET /api/payments/{id}/
Authorization: Bearer <token>
```

### Télécharger la facture (paiements `completed` uniquement)

```http
GET /api/payments/{id}/invoice/
Authorization: Bearer <token>
```

Retourne un fichier `.txt` en `Content-Disposition: attachment`.

```typescript
downloadInvoice(paymentId: number): void {
  this.http.get(`/api/payments/${paymentId}/invoice/`, {
    responseType: 'blob',
    headers: this.authHeaders()
  }).subscribe(blob => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `facture-${paymentId}.txt`;
    a.click();
  });
}
```

---

## 8. Gestion des erreurs

### Codes HTTP

| Code | Signification | Action Angular |
|---|---|---|
| `400` | Données invalides (ex: réservation déjà payée) | Afficher `error` du corps |
| `401` | Token expiré ou absent | Rediriger vers login |
| `403` | Pas les droits | Afficher message d'accès refusé |
| `404` | Paiement / réservation introuvable | Rediriger vers liste |

### Corps d'erreur type

```json
{ "error": "Cette réservation est déjà payée.", "payment_id": 17 }
```

### TypeScript — Intercepteur d'erreur

```typescript
// payment-error.interceptor.ts
intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
  return next.handle(req).pipe(
    catchError((err: HttpErrorResponse) => {
      const message = err.error?.error || err.error?.detail || 'Erreur inattendue';
      this.snackBar.open(message, 'Fermer', { duration: 5000 });
      if (err.status === 401) this.router.navigate(['/login']);
      return throwError(() => err);
    })
  );
}
```

---

## 9. Service Angular complet

```typescript
// payment.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Payment {
  id: number;
  user_email: string;
  reservation_info: { id: number; space: string; start: string; end: string };
  amount: string;
  currency: string;
  status: 'pending' | 'completed' | 'failed' | 'refunded' | 'cancelled';
  status_display: string;
  method: 'card' | 'mobile_money' | 'cash' | 'bank_transfer';
  method_display: string;
  transaction_id: string;
  paid_at: string | null;
  created_at: string;
}

export interface CreatePaymentResponse {
  message: string;
  payment: Payment;
  stripe?: {
    client_secret: string;
    publishable_key: string;
    payment_intent_id: string;
    amount_xof: string;
    amount_eur_cents: number;
  };
  fedapay?: {
    transaction_id: string;
    operator: string;
    payment_url: string;
    note: string;
  };
}

@Injectable({ providedIn: 'root' })
export class PaymentService {
  private base = '/api/payments';

  constructor(private http: HttpClient) {}

  private headers(): HttpHeaders {
    const token = localStorage.getItem('access_token');
    return new HttpHeaders({ Authorization: `Bearer ${token}` });
  }

  // ── Création ────────────────────────────────────────────────────────────

  createCardPayment(reservationId: number): Observable<CreatePaymentResponse> {
    return this.http.post<CreatePaymentResponse>(
      `${this.base}/create/`,
      { reservation_id: reservationId, method: 'card' },
      { headers: this.headers() }
    );
  }

  createMobileMoneyPayment(
    reservationId: number,
    phoneNumber: string,
    operator: 'mtn' | 'moov' = 'mtn'
  ): Observable<CreatePaymentResponse> {
    return this.http.post<CreatePaymentResponse>(
      `${this.base}/create/`,
      { reservation_id: reservationId, method: 'mobile_money', phone_number: phoneNumber, operator },
      { headers: this.headers() }
    );
  }

  createLocalPayment(
    reservationId: number,
    method: 'cash' | 'bank_transfer'
  ): Observable<CreatePaymentResponse> {
    return this.http.post<CreatePaymentResponse>(
      `${this.base}/create/`,
      { reservation_id: reservationId, method },
      { headers: this.headers() }
    );
  }

  // ── Confirmation Stripe ──────────────────────────────────────────────────

  confirmStripePayment(paymentId: number): Observable<any> {
    return this.http.post(`${this.base}/${paymentId}/stripe-confirm/`, {}, { headers: this.headers() });
  }

  // ── Consultation ─────────────────────────────────────────────────────────

  getPayments(filters?: { status?: string; method?: string }): Observable<{ results: Payment[] }> {
    const params = filters ? new URLSearchParams(filters as any).toString() : '';
    return this.http.get<{ results: Payment[] }>(`${this.base}/?${params}`, { headers: this.headers() });
  }

  getPayment(id: number): Observable<Payment> {
    return this.http.get<Payment>(`${this.base}/${id}/`, { headers: this.headers() });
  }

  downloadInvoice(paymentId: number): void {
    this.http.get(`${this.base}/${paymentId}/invoice/`, {
      responseType: 'blob',
      headers: this.headers()
    }).subscribe(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `facture-${paymentId}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  // ── Polling statut ────────────────────────────────────────────────────────

  async pollStatus(paymentId: number, maxAttempts = 10, intervalMs = 3000): Promise<Payment> {
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, intervalMs));
      const payment = await this.getPayment(paymentId).toPromise();
      if (payment!.status !== 'pending') return payment!;
    }
    throw new Error('Délai dépassé — paiement encore en attente de confirmation.');
  }
}
```

---

## 10. Composant de paiement Angular

```typescript
// payment.component.ts
import { Component, Input, OnInit } from '@angular/core';
import { loadStripe, Stripe, StripeCardElement } from '@stripe/stripe-js';
import { PaymentService, CreatePaymentResponse } from './payment.service';

@Component({
  selector: 'app-payment',
  template: `
    <mat-card>
      <mat-card-title>Choisir un mode de paiement</mat-card-title>

      <mat-radio-group [(ngModel)]="selectedMethod">
        <mat-radio-button value="card">Carte bancaire (Stripe)</mat-radio-button>
        <mat-radio-button value="mobile_money">Mobile Money (Flooz / T-Money)</mat-radio-button>
        <mat-radio-button value="cash">Espèces</mat-radio-button>
        <mat-radio-button value="bank_transfer">Virement bancaire</mat-radio-button>
      </mat-radio-group>

      <!-- Carte Stripe -->
      <div *ngIf="selectedMethod === 'card'">
        <div id="card-element"></div>
      </div>

      <!-- Mobile Money -->
      <div *ngIf="selectedMethod === 'mobile_money'">
        <mat-form-field>
          <input matInput [(ngModel)]="phoneNumber" placeholder="+22890123456" />
        </mat-form-field>
        <mat-select [(ngModel)]="operator">
          <mat-option value="mtn">Flooz (MTN)</mat-option>
          <mat-option value="moov">T-Money (Moov)</mat-option>
        </mat-select>
      </div>

      <button mat-raised-button color="primary" (click)="pay()" [disabled]="loading">
        {{ loading ? 'Traitement...' : 'Payer ' + amount + ' FCFA' }}
      </button>

      <div *ngIf="errorMessage" class="error">{{ errorMessage }}</div>
    </mat-card>
  `
})
export class PaymentComponent implements OnInit {
  @Input() reservationId!: number;
  @Input() amount!: string;

  selectedMethod: 'card' | 'mobile_money' | 'cash' | 'bank_transfer' = 'mobile_money';
  phoneNumber = '';
  operator: 'mtn' | 'moov' = 'mtn';
  loading = false;
  errorMessage = '';

  private stripe: Stripe | null = null;
  private cardElement: StripeCardElement | null = null;

  constructor(private paymentService: PaymentService) {}

  async ngOnInit(): Promise<void> {}

  async pay(): Promise<void> {
    this.loading = true;
    this.errorMessage = '';

    try {
      switch (this.selectedMethod) {
        case 'card':          await this.payWithCard(); break;
        case 'mobile_money':  await this.payWithMobileMoney(); break;
        case 'cash':
        case 'bank_transfer': await this.payLocal(); break;
      }
    } catch (err: any) {
      this.errorMessage = err.error?.error || err.message || 'Une erreur est survenue.';
    } finally {
      this.loading = false;
    }
  }

  // ── Stripe ────────────────────────────────────────────────────────────────

  private async payWithCard(): Promise<void> {
    const res: CreatePaymentResponse = await this.paymentService
      .createCardPayment(this.reservationId).toPromise() as CreatePaymentResponse;

    const paymentId = res.payment.id;
    const { client_secret, publishable_key } = res.stripe!;

    // Initialiser Stripe au dernier moment (clé publique vient du backend)
    this.stripe = await loadStripe(publishable_key);
    const elements = this.stripe!.elements();
    this.cardElement = elements.create('card');
    this.cardElement.mount('#card-element');

    const { error } = await this.stripe!.confirmCardPayment(client_secret, {
      payment_method: { card: this.cardElement }
    });

    if (error) throw new Error(error.message);

    // Confirmer côté serveur (obligatoire)
    const confirmed = await this.paymentService.confirmStripePayment(paymentId).toPromise();
    if (confirmed.paid) {
      console.log('Paiement Stripe confirmé !', confirmed.payment);
      // naviguer vers page de succès
    }
  }

  // ── FedaPay ───────────────────────────────────────────────────────────────

  private async payWithMobileMoney(): Promise<void> {
    if (!this.phoneNumber) {
      throw new Error('Veuillez saisir votre numéro Mobile Money.');
    }

    const res: CreatePaymentResponse = await this.paymentService
      .createMobileMoneyPayment(this.reservationId, this.phoneNumber, this.operator)
      .toPromise() as CreatePaymentResponse;

    const paymentId = res.payment.id;
    const paymentUrl = res.fedapay!.payment_url;

    if (paymentUrl) {
      // Rediriger vers la page de paiement FedaPay
      // Stocker paymentId pour récupérer le statut au retour
      sessionStorage.setItem('pending_payment_id', String(paymentId));
      window.location.href = paymentUrl;
    }
  }

  // ── Local ─────────────────────────────────────────────────────────────────

  private async payLocal(): Promise<void> {
    const res = await this.paymentService
      .createLocalPayment(this.reservationId, this.selectedMethod as 'cash' | 'bank_transfer')
      .toPromise();
    console.log('Paiement local enregistré, en attente de validation admin.', res);
    // Naviguer vers page de confirmation / attente
  }
}
```

### Composant callback FedaPay

À créer sur la route `FEDAPAY_CALLBACK_URL` (ex: `/payment/callback`) :

```typescript
// payment-callback.component.ts
@Component({
  selector: 'app-payment-callback',
  template: `
    <div *ngIf="loading">Vérification du paiement...</div>
    <div *ngIf="payment?.status === 'completed'">Paiement confirmé !</div>
    <div *ngIf="payment?.status === 'failed'">Paiement refusé.</div>
    <div *ngIf="payment?.status === 'pending'">Paiement en cours de confirmation...</div>
  `
})
export class PaymentCallbackComponent implements OnInit {
  payment: any;
  loading = true;

  constructor(private paymentService: PaymentService) {}

  async ngOnInit(): Promise<void> {
    const paymentId = Number(sessionStorage.getItem('pending_payment_id'));
    if (!paymentId) { this.loading = false; return; }

    try {
      // Vérifier le statut immédiatement
      this.payment = await this.paymentService.getPayment(paymentId).toPromise();

      // Si toujours pending, poller pendant 30s
      if (this.payment.status === 'pending') {
        this.payment = await this.paymentService.pollStatus(paymentId, 10, 3000);
      }
    } catch {
      // Paiement toujours en attente après 30s → validation admin ou webhook tardif
    } finally {
      this.loading = false;
      sessionStorage.removeItem('pending_payment_id');
    }
  }
}
```

---

## Récapitulatif des URLs

| Endpoint | Méthode HTTP | Auth | Description |
|---|---|---|---|
| `POST /api/payments/create/` | POST | JWT | Créer un paiement |
| `GET /api/payments/` | GET | JWT | Mes paiements |
| `GET /api/payments/{id}/` | GET | JWT | Détail d'un paiement |
| `POST /api/payments/{id}/stripe-confirm/` | POST | JWT | Confirmer Stripe (après Stripe.js) |
| `GET /api/payments/{id}/invoice/` | GET | JWT | Télécharger la facture |
| `POST /api/payments/webhook/` | POST | — | Webhook Stripe (usage interne) |
| `POST /api/payments/fedapay-webhook/` | POST | — | Webhook FedaPay (usage interne) |

> Les webhooks sont appelés par Stripe/FedaPay directement — ne pas les appeler depuis le frontend.

---

## Documentation interactive

Swagger UI disponible sur : `http://localhost:8000/api/docs/`  
ReDoc disponible sur : `http://localhost:8000/api/redoc/`
