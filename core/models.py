from django.db import models
from django.conf import settings


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=100, default='AbExam.uz')
    site_description = models.TextField(blank=True, default='IELTS Mock platformasi')
    announcement = models.TextField(blank=True, help_text='Sayt yuqorisida ko\'rinadigan e\'lon')
    announcement_active = models.BooleanField(default=False)
    maintenance_mode = models.BooleanField(default=False)
    maintenance_message = models.TextField(blank=True, default='Sayt texnik ishlar uchun vaqtincha to\'xtatilgan.')
    logo = models.ImageField(upload_to='site/', null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sayt sozlamalari'

    def __str__(self):
        return self.site_name

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Notification(models.Model):
    TYPE_CHOICES = (
        ('info', 'Ma\'lumot'),
        ('success', 'Muvaffaqiyat'),
        ('warning', 'Ogohlantirish'),
        ('danger', 'Xato'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='notifications', null=True, blank=True,
                             help_text='Bo\'sh qoldirilsa — barcha foydalanuvchilarga')
    title = models.CharField(max_length=200)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Xabar'
        verbose_name_plural = 'Xabarlar'

    def __str__(self):
        return self.title


class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percent = models.IntegerField(default=0, help_text='0-100 oralig\'ida')
    max_uses = models.IntegerField(default=1)
    used_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Promo kod'
        verbose_name_plural = 'Promo kodlar'

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.used_count >= self.max_uses:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True
