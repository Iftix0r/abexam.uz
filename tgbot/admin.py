from django.contrib import admin

from .models import Booking, ExamDay, TelegramAccount


@admin.register(TelegramAccount)
class TelegramAccountAdmin(admin.ModelAdmin):
    list_display = ('chat_id', 'username', 'first_name', 'user', 'phone', 'is_blocked', 'last_seen_at')
    search_fields = ('username', 'first_name', 'full_name', 'phone', 'user__username')
    list_filter = ('is_blocked',)
    raw_id_fields = ('user',)


class BookingInline(admin.TabularInline):
    model = Booking
    extra = 0
    fields = ('queue_number', 'full_name', 'phone', 'center', 'status')


@admin.register(ExamDay)
class ExamDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'start_time', 'title', 'capacity', 'is_open')
    list_filter = ('is_open',)
    inlines = [BookingInline]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('queue_number', 'full_name', 'phone', 'center', 'day', 'status', 'created_at')
    list_filter = ('status', 'day')
    search_fields = ('full_name', 'phone', 'center')
    raw_id_fields = ('account',)
