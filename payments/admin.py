from django.contrib import admin
from .models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'reason', 'amount', 'status', 'transaction_code', 'paid_at', 'created_at']
    list_filter = ['status']
    search_fields = ['user__email', 'reason', 'transaction_code']
    readonly_fields = ['id', 'created_at', 'updated_at']
