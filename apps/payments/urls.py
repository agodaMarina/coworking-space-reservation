from django.urls import path
from .views import (
    PaymentCreateView,
    PaymentListView,
    PaymentDetailView,
    PaymentConfirmView,
    PaymentStatsView,
    PaymentRefundView,
    InvoiceDownloadView,
)

app_name = 'payments'

urlpatterns = [
    path('',                  PaymentListView.as_view(),   name='payment-list'),
    path('create/',           PaymentCreateView.as_view(), name='payment-create'),
    path('<int:pk>/',         PaymentDetailView.as_view(), name='payment-detail'),
    path('<int:pk>/confirm/', PaymentConfirmView.as_view(), name='payment-confirm'),
    path('stats/',            PaymentStatsView.as_view(),  name='payment-stats'),
    path('<int:pk>/refund/',    PaymentRefundView.as_view(),  name='payment-refund'),
    path('<int:pk>/invoice/',   InvoiceDownloadView.as_view(), name='invoice-download')
]