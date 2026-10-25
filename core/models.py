from django.core.cache import cache
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
    # Exam page beeps and flashes red when the student leaves the test window
    # or pastes into Writing, so invigilators in the room notice.
    proctor_alarm = models.BooleanField(default=True)
    # Starting an exam needs its hourly password (exams/passwords.py), which
    # the invigilator reads in the panel and tells the students in the room.
    exam_password_required = models.BooleanField(default=True)
    # The exam page needs the webcam on and sends frames staff watch live
    # (exams/camera.py); the site asks for camera permission on entry.
    camera_proctoring = models.BooleanField(default=True)
    # Admin Telegram chat gets pinged when work is waiting: a payment to
    # approve, a Writing to grade, a question whose answer key looks wrong.
    telegram_work_alerts = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sayt sozlamalari'

    def __str__(self):
        return self.site_name

    _CACHE_KEY = 'site_settings_singleton'

    @classmethod
    def get(cls):
        # Read on every request (maintenance-mode middleware + the
        # announcement/notification context processor), so cache it rather
        # than hitting the DB twice per request site-wide.
        obj = cache.get(cls._CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls._CACHE_KEY, obj, 300)
        return obj

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.set(self._CACHE_KEY, self, 300)


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


class AuditLog(models.Model):
    """What a staff member did in the panel — balance changes, answer-key
    edits, grading, deletions — with who and when, for accountability."""
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    # Kept as text too, so the entry still reads right after the account is gone.
    staff_name = models.CharField(max_length=150)
    action = models.CharField(max_length=40, db_index=True)
    target = models.CharField(max_length=255, blank=True)
    target_url = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Xodim harakati'
        verbose_name_plural = 'Xodimlar harakatlari'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.staff_name}: {self.action} {self.target}"
