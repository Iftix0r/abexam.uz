from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import User, Vocabulary


class VocabularyInline(admin.TabularInline):
    model = Vocabulary
    extra = 0
    readonly_fields = ('created_at',)
    fields = ('english', 'translation', 'created_at')
    max_num = 20


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('show_avatar', 'username', 'email', 'phone_number', 'balance', 'is_active_student', 'is_staff', 'date_joined')
    list_display_links = ('show_avatar', 'username')
    list_filter = ('is_staff', 'is_active', 'is_active_student')
    search_fields = ('username', 'email', 'phone_number')
    ordering = ('-date_joined',)
    list_editable = ('is_active_student',)
    readonly_fields = ('date_joined', 'last_login')
    inlines = [VocabularyInline]

    fieldsets = (
        ("Kirish", {'fields': ('username', 'password')}),
        ('Shaxsiy', {'fields': ('first_name', 'last_name', 'email', 'phone_number', 'bio', 'avatar')}),
        ('Moliya', {'fields': ('balance',)}),
        ('Huquqlar', {'fields': ('is_active', 'is_active_student', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Sanalar', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'fields': ('username', 'password1', 'password2', 'email', 'phone_number')}),
    )

    def show_avatar(self, obj):
        if obj.avatar:
            return format_html('<img src="{}" style="width:28px;height:28px;border-radius:50%;object-fit:cover;">', obj.avatar.url)
        return format_html('<div style="width:28px;height:28px;border-radius:50%;background:#6366f1;color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;">{}</div>', obj.username[:1].upper())
    show_avatar.short_description = ''


@admin.register(Vocabulary)
class VocabularyAdmin(admin.ModelAdmin):
    list_display = ('english', 'translation', 'user', 'created_at')
    search_fields = ('english', 'user__username')
    readonly_fields = ('created_at',)
