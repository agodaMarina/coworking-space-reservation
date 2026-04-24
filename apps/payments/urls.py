from django.urls import path
from .views import (
    PaymentCreateView,
    PaymentListView,
    PaymentDetailView,
    PaymentConfirmView,
    PaymentStatsView,
    PaymentRefundView,
    InvoiceDownloadView,
    StripeWebhookView,
    PaymentStripeConfirmView,
    FedaPayWebhookView,
)

app_name = 'payments'

urlpatterns = [
    path('',                         PaymentListView.as_view(),          name='payment-list'),
    path('create/',                  PaymentCreateView.as_view(),        name='payment-create'),
    path('<int:pk>/',                PaymentDetailView.as_view(),        name='payment-detail'),
    path('<int:pk>/confirm/',        PaymentConfirmView.as_view(),       name='payment-confirm'),
    path('<int:pk>/stripe-confirm/', PaymentStripeConfirmView.as_view(), name='payment-stripe-confirm'),
    path('stats/',                   PaymentStatsView.as_view(),         name='payment-stats'),
    path('<int:pk>/refund/',         PaymentRefundView.as_view(),        name='payment-refund'),
    path('<int:pk>/invoice/',        InvoiceDownloadView.as_view(),      name='invoice-download'),
    # Webhooks — pas d'authentification JWT (signatures HMAC)
    path('webhook/',                 StripeWebhookView.as_view(),        name='stripe-webhook'),
    path('fedapay-webhook/',         FedaPayWebhookView.as_view(),       name='fedapay-webhook'),
]

