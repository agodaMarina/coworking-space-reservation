# DOCUMENT DE SPÉCIFICATIONS TECHNIQUES
## Coworking Space Booking Platform — Refactoring Réservation & Paiement v2.0

> **Stack :** Angular 21 · Django 5 · Stripe · FedaPay  
> **Date :** Avril 2026 · Lomé, Togo

---

## Table des matières

1. [Contexte et Objectifs](#1-contexte-et-objectifs)
2. [Backend Django — Modifications & Instructions](#2-backend-django--modifications--instructions)
3. [Frontend Angular — Modifications & Instructions](#3-frontend-angular--modifications--instructions)
4. [Checklist d'Implémentation Ordonnée](#4-checklist-dimplémentation-ordonnée)
5. [Diagramme du Nouveau Flux](#5-diagramme-du-nouveau-flux-réservation--paiement)

---

## 1. Contexte et Objectifs

### 1.1 Nouveau paradigme de réservation

Le flux actuel permet à l'utilisateur de réserver et payer directement. Le nouveau paradigme introduit une **étape de validation administrative obligatoire** avant le paiement :

1. L'utilisateur soumet une demande de réservation (statut : `pending`)
2. L'admin reçoit une notification (email + in-app) et confirme ou rejette
3. L'utilisateur reçoit une notification de confirmation et peut accéder au paiement
4. Après paiement, l'admin reçoit une notification et l'espace est marqué comme réservé

### 1.2 Périmètre des modifications

| Domaine | Type | Priorité |
|---|---|---|
| Flux réservation + paiement | Refactoring logique métier | **CRITIQUE** |
| Notifications email + in-app | Nouvelle fonctionnalité | **CRITIQUE** |
| Dashboard client — Espaces | Amélioration UI | HAUTE |
| Dashboard client — Paiements | Amélioration UI | HAUTE |
| Dashboard admin — Réservations | Correction + amélioration | HAUTE |
| Dashboard admin — Paiements | Correction affichage | HAUTE |
| Dashboard admin — Amenities | Affichage icônes | MOYENNE |
| Génération facture PDF | Nouvelle fonctionnalité | HAUTE |
| Formulaire booking website | Adaptation nouveau flux | HAUTE |

---

## 2. Backend Django — Modifications & Instructions

### 2.1 Nouveau flux — Modèle Reservation

Le modèle `Reservation` doit être adapté pour distinguer la confirmation admin de la confirmation de paiement. Les transitions de statut sont révisées :

| Statut | Déclencheur | Notification envoyée |
|---|---|---|
| `pending` | Utilisateur crée la réservation | Admin : email + in-app |
| `confirmed` | Admin confirme la réservation | Utilisateur : email + in-app |
| `rejected` | Admin rejette la réservation | Utilisateur : email + in-app |
| `payment_pending` | Utilisateur initie le paiement | Aucune |
| `paid` | Paiement confirmé (Stripe/FedaPay/Local) | Admin : email + in-app |
| `cancelled` | Utilisateur ou admin annule | Les deux parties |
| `completed` | Fin de la période (Celery Beat) | Aucune |

#### `apps/reservations/models.py`

- [ ] Ajouter les statuts `payment_pending` et `paid` dans `STATUS_CHOICES`
- [ ] Ajouter le champ `confirmed_at = models.DateTimeField(null=True, blank=True)`
- [ ] Ajouter le champ `confirmed_by = models.ForeignKey(User, null=True, on_delete=SET_NULL, related_name='confirmed_reservations')`

```python
STATUS_CHOICES = [
    ('pending', 'En attente'),
    ('confirmed', 'Confirmée'),
    ('rejected', 'Rejetée'),
    ('payment_pending', 'Paiement en cours'),
    ('paid', 'Payée'),
    ('cancelled', 'Annulée'),
    ('completed', 'Terminée'),
]
```

#### `apps/reservations/views.py`

- [ ] `CreateReservationView` : à la création, déclencher la tâche Celery `send_reservation_request_to_admin(reservation_id)`
- [ ] `UpdateReservationView` (admin) : lors du passage à `confirmed`, déclencher `send_reservation_confirmed_to_user(reservation_id)`. Lors du passage à `rejected`, déclencher `send_reservation_rejected_to_user(reservation_id)`
- [ ] Créer un endpoint `POST /api/reservations/{id}/initiate-payment/` accessible uniquement si `statut = confirmed`, qui passe le statut à `payment_pending` et retourne l'ID de réservation
- [ ] Bloquer la création de paiement si la réservation n'est pas en statut `confirmed` ou `payment_pending`

```python
# Dans PaymentCreateView — validation à ajouter :
if reservation.status not in ['confirmed', 'payment_pending']:
    return Response(
        {'error': 'La réservation doit être confirmée par l\'admin avant le paiement.'},
        status=400
    )
```

#### `apps/reservations/serializers.py`

- [ ] Ajouter les champs `confirmed_at` et `confirmed_by` dans `ReservationSerializer`
- [ ] Ajouter un champ calculé `can_pay` (bool) : `True` si statut est `confirmed` ou `payment_pending`
- [ ] Exposer `status_display` avec le libellé lisible

```python
class ReservationSerializer(serializers.ModelSerializer):
    can_pay = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    def get_can_pay(self, obj):
        return obj.status in ['confirmed', 'payment_pending']
```

---

### 2.2 Système de notifications

Implémenter un système double : **notifications in-app** (modèle `Notification`) + **emails via Gmail SMTP** avec Celery.

#### `config/.env`

- [ ] Configurer les variables Gmail SMTP :

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=votre_email@gmail.com
EMAIL_HOST_PASSWORD=votre_app_password_google
DEFAULT_FROM_EMAIL=CoworkSpace <votre_email@gmail.com>
```

> **Important :** utiliser un **App Password Google** (Compte Google → Sécurité → Mots de passe des applications), pas le mot de passe principal du compte.

#### `apps/notifications/models.py`

- [ ] Ajouter les types manquants dans `NOTIFICATION_TYPES` :

```python
'reservation_request'    # Nouvelle demande (pour admin)
'reservation_confirmed'  # Réservation confirmée (pour user)
'reservation_rejected'   # Réservation rejetée (pour user)
'payment_received'       # Paiement reçu (pour admin)
```

#### `apps/notifications/tasks.py`

- [ ] Créer la tâche `send_reservation_request_to_admin(reservation_id)` : notification in-app + email à tous les admins
- [ ] Créer la tâche `send_reservation_confirmed_to_user(reservation_id)` : notification in-app + email utilisateur
- [ ] Créer la tâche `send_reservation_rejected_to_user(reservation_id)` : notification in-app + email utilisateur
- [ ] Créer la tâche `send_payment_confirmed_to_admin(payment_id)` : notification in-app + email admin

```python
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

@shared_task
def send_reservation_request_to_admin(reservation_id):
    reservation = Reservation.objects.select_related('user', 'space').get(id=reservation_id)
    admin_users = User.objects.filter(role='admin')

    for admin in admin_users:
        # Notification in-app
        Notification.objects.create(
            user=admin,
            type='reservation_request',
            title='Nouvelle demande de réservation',
            message=f'Demande de {reservation.user.full_name} pour {reservation.space.name}',
            reservation=reservation
        )
        # Email
        send_mail(
            subject='[CoworkSpace] Nouvelle demande de réservation',
            message='',
            html_message=render_to_string(
                'emails/admin_reservation_request.html',
                {'reservation': reservation}
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin.email],
            fail_silently=False,
        )

@shared_task
def send_reservation_confirmed_to_user(reservation_id):
    reservation = Reservation.objects.select_related('user', 'space').get(id=reservation_id)
    Notification.objects.create(
        user=reservation.user,
        type='reservation_confirmed',
        title='Réservation confirmée !',
        message=f'Votre réservation pour {reservation.space.name} a été confirmée. Vous pouvez procéder au paiement.',
        reservation=reservation
    )
    send_mail(
        subject='[CoworkSpace] Votre réservation est confirmée',
        message='',
        html_message=render_to_string(
            'emails/user_reservation_confirmed.html',
            {'reservation': reservation}
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[reservation.user.email],
        fail_silently=False,
    )

@shared_task
def send_payment_confirmed_to_admin(payment_id):
    payment = Payment.objects.select_related('user', 'reservation__space').get(id=payment_id)
    admin_users = User.objects.filter(role='admin')
    for admin in admin_users:
        Notification.objects.create(
            user=admin,
            type='payment_received',
            title='Paiement reçu',
            message=f'Paiement de {payment.amount} XOF reçu de {payment.user.full_name} pour {payment.reservation.space.name}',
        )
        send_mail(
            subject='[CoworkSpace] Paiement reçu',
            message='',
            html_message=render_to_string('emails/admin_payment_received.html', {'payment': payment}),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin.email],
            fail_silently=False,
        )
```

#### Templates email à créer dans `templates/emails/`

- [ ] `admin_reservation_request.html` — notifie l'admin d'une nouvelle demande
- [ ] `user_reservation_confirmed.html` — notifie l'utilisateur que sa réservation est confirmée
- [ ] `user_reservation_rejected.html` — notifie l'utilisateur du rejet
- [ ] `admin_payment_received.html` — notifie l'admin du paiement

Chaque template doit inclure : logo, nom de l'utilisateur, espace concerné, dates, montant, lien vers le dashboard.

---

### 2.3 Génération de facture PDF

Remplacer la génération `.txt` par une génération PDF avec **WeasyPrint**.

#### Installation

```bash
pip install weasyprint
pip freeze > requirements/development.txt
```

#### `apps/payments/views.py` — `PaymentInvoiceView`

- [ ] Modifier la vue pour générer un PDF :

```python
from weasyprint import HTML
from django.template.loader import render_to_string
from django.http import HttpResponse

class PaymentInvoiceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        payment = get_object_or_404(Payment, id=pk, user=request.user)
        if payment.status != 'completed':
            return Response(
                {'error': 'Facture disponible uniquement pour les paiements complétés'},
                status=400
            )
        html_content = render_to_string(
            'invoices/invoice.html',
            {'payment': payment, 'request': request}
        )
        pdf = HTML(string=html_content, base_url=request.build_absolute_uri()).write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="facture-{payment.id}.pdf"'
        return response
```

#### `templates/invoices/invoice.html`

- [ ] Créer le template HTML de facture incluant :
  - Logo CoworkSpace
  - Numéro de facture (référence transaction)
  - Informations client (nom, email)
  - Détails de l'espace (nom, adresse)
  - Période de réservation
  - Montant en FCFA + méthode de paiement
  - Date de paiement
  - Pied de page avec mentions légales

---

### 2.4 Modification de `apps/payments/views.py` — Post-paiement

- [ ] Après confirmation Stripe (`stripe-confirm`) ou webhook FedaPay : passer `reservation.status = 'paid'` et appeler `reservation.save()`
- [ ] Déclencher la tâche `send_payment_confirmed_to_admin.delay(payment.id)`

```python
# Dans stripe-confirm et dans le webhook FedaPay, après payment.status = 'completed' :
reservation = payment.reservation
reservation.status = 'paid'
reservation.save()
send_payment_confirmed_to_admin.delay(payment.id)
```

---

## 3. Frontend Angular — Modifications & Instructions

### 3.1 Mise à jour `reservations.service.ts`

- [ ] Mettre à jour l'interface `Reservation` :

```typescript
interface Reservation {
  id: number;
  status: 'pending' | 'confirmed' | 'rejected' | 'payment_pending' | 'paid' | 'cancelled' | 'completed';
  status_display: string;
  can_pay: boolean;         // true si confirmed ou payment_pending
  confirmed_at: string | null;
  confirmed_by: any | null;
  space_detail: any;
  start_datetime: string;
  end_datetime: string;
  total_price: number;
  billing_type: 'hourly' | 'daily';
  is_recurring: boolean;
  notes: string;
}
```

- [ ] Ajouter la méthode `initiatePayment(reservationId: number)` :

```typescript
initiatePayment(reservationId: number): Observable<any> {
  return this.post(`/reservations/${reservationId}/initiate-payment/`, {});
}
```

---

### 3.2 Page Booking — Website

**Fichier :** `src/app/features/booking/booking.component.ts`

Le formulaire doit soumettre une demande de réservation sans paiement immédiat.

- [ ] **Supprimer** tout le bloc de sélection de méthode de paiement du formulaire
- [ ] **Supprimer** les imports et références à `PaymentService` dans ce composant
- [ ] Modifier le texte du bouton de soumission : `'Envoyer la demande de réservation'`
- [ ] Après succès, afficher le message suivant :

```
✅ Votre demande a été envoyée avec succès.
L'admin validera votre réservation sous 24h.
Vous recevrez un email de confirmation dès validation.
```

- [ ] Ajouter un lien `'Suivre mes réservations'` pointant vers `/dashboard/reservations`
- [ ] Le formulaire multi-step conserve : sélection espace, dates, type de facturation, récurrence, notes spéciales

---

### 3.3 Dashboard Client — Module Espaces

**Fichier :** `src/app/features/dashboard/client/spaces.component.ts`

- [ ] **Retirer** le bouton/action `'Close'` du tableau
- [ ] Appliquer le pipe `currency` sur les colonnes prix :

```html
{{ space.price_per_hour | currency:'XOF':'symbol':'1.0-0' }}
{{ space.price_per_day | currency:'XOF':'symbol':'1.0-0' }}
```

- [ ] Ajouter un handler `(click)` sur chaque ligne du tableau PrimeNG :

```typescript
onRowClick(space: Space) {
  this.selectedSpace.set(space);
  this.showDetailModal.set(true);
}
```

```html
<p-table [value]="spaces()" (onRowClick)="onRowClick($event.data)" [rowHover]="true">
```

- [ ] La **modal de détails** doit afficher : nom, type, capacité, adresse, prix/h, prix/jour, amenities (icônes PrimeIcons), photos si disponibles
- [ ] Dans la modal, ajouter un bouton `'Réserver cet espace'` qui navigue vers `/booking?spaceId={id}`

```typescript
bookSpace(spaceId: number) {
  this.router.navigate(['/booking'], { queryParams: { spaceId } });
}
```

- [ ] Dans `booking.component.ts`, lire le `queryParam` `spaceId` au `ngOnInit` et pré-remplir le champ espace du formulaire

---

### 3.4 Dashboard Client — Module Paiements

**Fichier :** `src/app/features/dashboard/client/payments.component.ts`

- [ ] Appliquer `styleClass="p-datatable-gridlines p-datatable-sm"` sur `<p-table>`
- [ ] Appliquer le pipe `currency` sur la colonne montant : `{{ payment.amount | currency:'XOF':'symbol':'1.0-0' }}`
- [ ] Définir les alignements de colonnes :

| Colonne | Alignement |
|---|---|
| Référence | Gauche |
| Espace | Gauche |
| Montant | Droite |
| Méthode | Centre |
| Statut | Centre |
| Date | Centre |
| Actions | Centre |

- [ ] Ajouter une colonne **Actions** avec un bouton `'Facture PDF'` (icône `pi-file-pdf`) visible uniquement si `payment.status === 'completed'` :

```html
<p-button
  *ngIf="payment.status === 'completed'"
  icon="pi pi-file-pdf"
  label="Facture"
  severity="secondary"
  size="small"
  (onClick)="downloadInvoice(payment.id)">
</p-button>
```

```typescript
downloadInvoice(paymentId: number): void {
  this.http.get(`/api/payments/${paymentId}/invoice/`, {
    responseType: 'blob',
    headers: this.authHeaders()
  }).subscribe(blob => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `facture-${paymentId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  });
}
```

---

### 3.5 Dashboard Client — Module Réservations

**Fichier :** `src/app/features/dashboard/client/reservations.component.ts`

- [ ] Afficher le statut de chaque réservation avec un **badge coloré** :

| Statut | Label affiché | Couleur badge |
|---|---|---|
| `pending` | En attente de confirmation | Jaune / warning |
| `confirmed` | Confirmée — Paiement possible | Bleu / info |
| `payment_pending` | Paiement en cours | Orange |
| `paid` | Payée | Vert / success |
| `rejected` | Rejetée | Rouge / danger |
| `cancelled` | Annulée | Gris |
| `completed` | Terminée | Violet |

- [ ] Afficher une **bannière informative** pour les réservations `pending` :

```html
<p-message
  *ngIf="reservation.status === 'pending'"
  severity="info"
  text="En attente de validation admin. Vous recevrez un email dès confirmation.">
</p-message>
```

- [ ] Afficher le bouton `'Procéder au paiement'` uniquement si `reservation.can_pay === true` :

```html
<p-button
  *ngIf="reservation.can_pay"
  label="Procéder au paiement"
  icon="pi pi-credit-card"
  (onClick)="openPaymentModal(reservation)">
</p-button>
```

- [ ] Ce bouton appelle `reservationsService.initiatePayment(reservation.id)` puis ouvre une `p-dialog` contenant le composant de paiement (carte, mobile money, cash, virement)

---

### 3.6 Dashboard Admin — Module Réservations

**Fichier :** `src/app/features/dashboard/admin/reservations.component.ts`

- [ ] Colonnes du tableau : ID · Client (nom + email) · Espace · Période · Facturation · Montant · Statut · Actions
- [ ] Corriger les largeurs de colonnes avec `[style]` :

```html
<p-column field="id" header="ID" [style]="{'width': '5%'}"></p-column>
<p-column field="user" header="Client" [style]="{'width': '18%'}"></p-column>
<p-column field="space" header="Espace" [style]="{'width': '15%'}"></p-column>
<p-column field="period" header="Période" [style]="{'width': '20%'}"></p-column>
<p-column field="total_price" header="Montant" [style]="{'width': '10%'}"></p-column>
<p-column field="status" header="Statut" [style]="{'width': '12%'}"></p-column>
<p-column header="Actions" [style]="{'width': '15%'}"></p-column>
```

- [ ] Appliquer `currency` : `{{ reservation.total_price | currency:'XOF':'symbol':'1.0-0' }}`
- [ ] Boutons d'action **contextuels selon le statut** :

```html
<!-- Si pending -->
<p-button *ngIf="reservation.status === 'pending'"
  label="Confirmer" icon="pi pi-check" severity="success" size="small"
  (onClick)="updateStatus(reservation.id, 'confirmed')">
</p-button>
<p-button *ngIf="reservation.status === 'pending'"
  label="Rejeter" icon="pi pi-times" severity="danger" size="small"
  (onClick)="updateStatus(reservation.id, 'rejected')">
</p-button>

<!-- Si confirmed -->
<p-button *ngIf="reservation.status === 'confirmed'"
  label="Annuler" icon="pi pi-ban" severity="secondary" size="small"
  (onClick)="updateStatus(reservation.id, 'cancelled')">
</p-button>
```

```typescript
updateStatus(reservationId: number, status: string): void {
  this.reservationsService.updateReservation(reservationId, { status }).subscribe({
    next: () => {
      this.toastService.showSuccess(`Réservation ${status === 'confirmed' ? 'confirmée' : 'mise à jour'}`);
      this.loadReservations();
    },
    error: () => this.toastService.showError('Une erreur est survenue')
  });
}
```

---

### 3.7 Dashboard Admin — Module Paiements

**Fichier :** `src/app/features/dashboard/admin/payments.component.ts`

- [ ] Colonnes : ID · Utilisateur · Espace · Montant · Méthode · Statut · Date paiement · Actions
- [ ] Appliquer `currency` : `{{ payment.amount | currency:'XOF':'symbol':'1.0-0' }}`
- [ ] Corriger les **badges de statut** :

| Statut | Couleur |
|---|---|
| `pending` | Jaune |
| `completed` | Vert |
| `failed` | Rouge |
| `refunded` | Orange |
| `cancelled` | Gris |

- [ ] Pour les paiements `cash`/`bank_transfer` en `pending` : afficher boutons `'Valider'` et `'Rejeter'` appelant `PATCH /api/payments/{id}/confirm/`
- [ ] Pour les paiements `completed` : afficher bouton `'Voir facture'`

---

### 3.8 Dashboard Admin — Module Amenities

**Fichier :** `src/app/features/dashboard/admin/amenities.component.ts`

- [ ] Ajouter une colonne **Icône** dans le tableau :

```html
<p-column header="Icône" [style]="{'width': '8%', 'text-align': 'center'}">
  <ng-template pTemplate="body" let-amenity>
    <i [class]="'pi pi-' + (amenity.icon_key || 'circle')"
       style="font-size: 1.3rem; color: #2563eb;">
    </i>
  </ng-template>
</p-column>
```

- [ ] Dans le formulaire d'ajout/édition : ajouter un champ `icon_key` avec preview en temps réel :

```html
<div class="icon-preview">
  <label>Clé d'icône PrimeIcons</label>
  <p-inputText [(ngModel)]="form.icon_key" placeholder="ex: wifi, desktop, users"></p-inputText>
  <div class="preview" *ngIf="form.icon_key">
    <i [class]="'pi pi-' + form.icon_key" style="font-size: 1.5rem"></i>
    <span>{{ form.icon_key }}</span>
  </div>
</div>
```

---

### 3.9 Notifications in-app — Header

**Fichier :** `src/app/core/services/notifications.service.ts`

- [ ] Créer ou enrichir le service :

```typescript
@Injectable({ providedIn: 'root' })
export class NotificationsService {
  private readonly unreadCount = signal(0);
  readonly unreadCount$ = this.unreadCount.asReadonly();

  getNotifications(): Observable<Notification[]> {
    return this.get<Notification[]>('/notifications/');
  }

  getUnreadCount(): Observable<{ count: number }> {
    return this.get<{ count: number }>('/notifications/stats/');
  }

  markAllRead(): Observable<any> {
    return this.post('/notifications/read/', {});
  }

  startPolling(): void {
    interval(30000).pipe(
      startWith(0),
      switchMap(() => this.getUnreadCount())
    ).subscribe(({ count }) => this.unreadCount.set(count));
  }
}
```

**Fichier :** `src/app/shared/components/header/header.component.ts`

- [ ] Ajouter une cloche avec badge dans la navigation :

```html
<div class="notification-bell" (click)="toggleNotifications()">
  <i class="pi pi-bell" style="font-size: 1.3rem"></i>
  <span class="badge" *ngIf="notifService.unreadCount$() > 0">
    {{ notifService.unreadCount$() }}
  </span>
</div>

<p-overlayPanel #notifPanel>
  <div class="notif-header">
    <span>Notifications</span>
    <p-button label="Tout marquer lu" size="small" (onClick)="markAllRead()"></p-button>
  </div>
  <div *ngFor="let notif of notifications()" class="notif-item" [class.unread]="!notif.is_read">
    <span class="notif-title">{{ notif.title }}</span>
    <span class="notif-msg">{{ notif.message }}</span>
    <span class="notif-time">{{ notif.created_at | date:'short' }}</span>
  </div>
</p-overlayPanel>
```

- [ ] Démarrer le polling dans `ngOnInit` : `this.notifService.startPolling()`

---

## 4. Checklist d'Implémentation Ordonnée

### Phase 1 — Backend (à faire en premier)

- [ ] Ajouter les statuts `payment_pending` et `paid` dans `Reservation.STATUS_CHOICES`
- [ ] Ajouter les champs `confirmed_at` et `confirmed_by` au modèle `Reservation`
- [ ] Créer et appliquer les migrations : `python manage.py makemigrations && python manage.py migrate`
- [ ] Ajouter les types de notification manquants dans `Notification.NOTIFICATION_TYPES`
- [ ] Créer les 4 tâches Celery dans `apps/notifications/tasks.py`
- [ ] Créer les 4 templates email HTML dans `templates/emails/`
- [ ] Configurer les variables SMTP Gmail dans `.env` (avec App Password Google)
- [ ] Créer l'endpoint `POST /api/reservations/{id}/initiate-payment/`
- [ ] Modifier `PaymentCreateView` pour valider le statut de réservation
- [ ] Modifier la logique post-paiement : `reservation.status = 'paid'` + tâche notification admin
- [ ] Installer WeasyPrint : `pip install weasyprint`
- [ ] Modifier `PaymentInvoiceView` pour générer du PDF
- [ ] Créer le template `templates/invoices/invoice.html`
- [ ] Mettre à jour `ReservationSerializer` : champs `confirmed_at`, `confirmed_by`, `can_pay`, `status_display`

### Phase 2 — Frontend (après validation backend)

- [ ] Mettre à jour l'interface `Reservation` dans `reservations.service.ts`
- [ ] Ajouter la méthode `initiatePayment()` dans `reservations.service.ts`
- [ ] Modifier `booking.component.ts` : retirer paiement, adapter message de succès
- [ ] Dashboard client — Espaces : retirer Close, pipe currency, modal au clic, bouton réserver
- [ ] Dashboard client — Paiements : alignement tableau, bouton facture PDF
- [ ] Dashboard client — Réservations : badges statut, bouton paiement conditionnel, modal paiement
- [ ] Dashboard admin — Réservations : boutons Confirmer/Rejeter, pipe currency, largeurs colonnes
- [ ] Dashboard admin — Paiements : correction affichage, pipe currency, badges statut
- [ ] Dashboard admin — Amenities : afficher icônes PrimeIcons
- [ ] Créer/enrichir `notifications.service.ts` avec polling 30s
- [ ] Modifier `header.component.ts` : cloche + badge + overlay panel notifications

### Phase 3 — Tests & Validation

- [ ] Tester le flux complet : demande → confirmation admin → paiement → notification
- [ ] Tester l'envoi email via Gmail SMTP (vérifier la réception dans la boîte)
- [ ] Tester la génération PDF et le téléchargement de facture
- [ ] Tester les notifications in-app et le polling
- [ ] Vérifier l'affichage des tableaux admin et client : alignement, currency pipe, badges

---

## 5. Diagramme du Nouveau Flux Réservation + Paiement

```
UTILISATEUR                    SYSTÈME                        ADMIN
    |                             |                              |
    |-- POST /reservations/ ----> |                              |
    |   (status: pending)         |-- notification email ------> |
    |                             |-- notification in-app ------> |
    |                             |                              |
    |                             |    ADMIN CONFIRME            |
    |                             | <-- PATCH /reservations/id/--|
    |                             |    (status: confirmed)       |
    | <-- notification email ---- |                              |
    | <-- notification in-app --- |                              |
    |                             |                              |
    |-- POST /initiate-payment/ ->|                              |
    |   (status: payment_pending) |                              |
    |                             |                              |
    |-- POST /payments/create/ -->|                              |
    |   (méthode au choix)        |                              |
    |                             |                              |
    |  [Stripe.js / FedaPay / Local]                             |
    |                             |                              |
    |-- POST /stripe-confirm/ --> |                              |
    |   (ou webhook FedaPay)      |-- (status: paid)             |
    |                             |-- notification email ------> |
    |                             |-- notification in-app ------> |
    | <-- { paid: true } ---------|                              |
    |                             |                              |
    |   [Celery Beat à échéance]  |                              |
    |                             |-- (status: completed)        |
```

### États bloquants

| Règle | Description |
|---|---|
| Paiement impossible | Si `status` n'est pas `confirmed` ou `payment_pending` |
| Confirmation admin impossible | Si `status` n'est pas `pending` |
| Annulation client contrainte | Minimum 24h avant le début (inchangé) |
| Un seul paiement actif | Par réservation — vérification côté backend |

---

*Document généré — Avril 2026 · Coworking Space, Lomé, Togo*
