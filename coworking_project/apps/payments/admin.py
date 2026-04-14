from django.contrib import admin
from .models import Payment, Invoice


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'reservation', 'amount', 'currency', 'method', 'status', 'paid_at']
    list_filter = ['status', 'method', 'currency']
    search_fields = ['user__email', 'transaction_id']
    ordering = ['-created_at']

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['reference', 'payment', 'created_at']
    search_fields = ['reference']
    ordering = ['-created_at']