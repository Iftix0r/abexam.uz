from django.contrib import admin
from django.utils.html import format_html
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'show_amount', 'method', 'show_status', 'created_at')
    list_filter = ('status', 'method')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def show_amount(self, obj):
        return format_html('<b style="color:#22c55e">+{} so\'m</b>', obj.amount)
    show_amount.short_description = 'Summa'
    show_amount.admin_order_field = 'amount'

    def show_status(self, obj):
        colors = {'success': '#22c55e', 'pending': '#eab308', 'failed': '#ef4444'}
        return format_html('<span style="color:{}">{}</span>', colors.get(obj.status, '#aaa'), obj.get_status_display())
    show_status.short_description = 'Holat'
    show_status.admin_order_field = 'status'
