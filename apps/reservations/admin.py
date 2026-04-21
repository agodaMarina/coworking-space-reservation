from django.contrib import admin
from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'space', 'start_datetime', 'end_datetime', 'status', 'total_price']
    list_filter = ['status', 'billing_type', 'is_recurring']
    search_fields = ['user__email', 'space__name']
    ordering = ['-created_at']