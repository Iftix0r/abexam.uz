import re
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


def validate_phone(value):
    if value and not re.match(r'^\+?[\d\s\-()]{7,15}$', value):
        raise ValidationError("To'g'ri telefon raqam kiriting (masalan: +998901234567)")


class User(AbstractUser):
    phone_number = models.CharField(
        max_length=15, unique=True, null=True, blank=True,
        validators=[validate_phone],
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    is_active_student = models.BooleanField(default=True)
    bio = models.TextField(max_length=500, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = 'Foydalanuvchi'
        verbose_name_plural = 'Foydalanuvchilar'


class Vocabulary(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vocabulary')
    english = models.CharField(max_length=255)
    translation = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.english} - {self.translation}"

    class Meta:
        verbose_name = "Lug'at"
        verbose_name_plural = "Lug'atlar"
        ordering = ['-created_at']


class LoginLog(models.Model):
    STATUS_CHOICES = (
        ('success', 'Muvaffaqiyatli'),
        ('failed', 'Xato parol'),
        ('blocked', 'Bloklangan'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_logs', null=True, blank=True)
    username_attempt = models.CharField(max_length=150)
    ip = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username_attempt} | {self.ip} | {self.status}"

    class Meta:
        verbose_name = 'Login log'
        verbose_name_plural = 'Login loglar'
        ordering = ['-created_at']
