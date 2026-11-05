import re
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def validate_phone(value):
    if value and not re.match(r'^\+?[\d\s\-()]{7,15}$', value):
        raise ValidationError("To'g'ri telefon raqam kiriting (masalan: +998901234567)")


def age_on(birth_date, day):
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


def avatar_upload_to(instance, filename):
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    if extension in ('jpeg', 'jpg'):
        extension = 'jpg'
    return f"avatars/{uuid.uuid4().hex}.{extension}"


class User(AbstractUser):
    phone_number = models.CharField(
        max_length=15, unique=True, null=True, blank=True,
        validators=[validate_phone],
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    avatar = models.ImageField(upload_to=avatar_upload_to, null=True, blank=True)
    is_active_student = models.BooleanField(default=True)
    bio = models.TextField(max_length=500, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    premium_until = models.DateTimeField(null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    region = models.CharField(max_length=40, blank=True, db_index=True)
    district = models.CharField(max_length=40, blank=True)

    def __str__(self):
        return self.username

    @property
    def needs_details(self):
        return not (self.birth_date and self.region and self.district)

    @property
    def age(self):
        if not self.birth_date:
            return None
        return age_on(self.birth_date, timezone.localdate())

    @property
    def display_name(self):
        """Ism familiya; signups' usernames are just their phone digits."""
        return self.get_full_name() or self.username

    @property
    def has_own_username(self):
        """False when the username was generated from the phone number."""
        digits = (self.phone_number or '').lstrip('+')
        return not digits or not self.username.startswith(digits)

    @property
    def is_premium(self):
        return bool(self.premium_until and self.premium_until > timezone.now())

    @property
    def premium_days_left(self):
        if not self.is_premium:
            return 0
        return (self.premium_until - timezone.now()).days + 1

    @property
    def public_name(self):
        """For lists other students see. Never the username of a phone signup,
        which is their phone number."""
        return self.get_full_name() or (self.username if self.has_own_username else 'Talaba')

    # Telegram-style letter avatar: up to two initials on a colour that stays
    # the same for a user (picked from the pk).
    AVATAR_COLORS = ('#e17076', '#faa774', '#a695e7', '#7bc862', '#6ec9cb', '#65aadd', '#ee7aae')

    @property
    def initials(self):
        words = (self.get_full_name() or self.username).split()
        return ''.join(w[0] for w in words[:2]).upper() or '?'

    @property
    def avatar_color(self):
        return self.AVATAR_COLORS[(self.pk or 0) % len(self.AVATAR_COLORS)]

    class Meta:
        verbose_name = 'Foydalanuvchi'
        verbose_name_plural = 'Foydalanuvchilar'


class Vocabulary(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vocabulary')
    english = models.CharField(max_length=255)
    translation = models.CharField(max_length=255)
    example = models.CharField(max_length=300, blank=True)
    lesson_slug = models.CharField(max_length=100, blank=True, help_text="Qaysi darsdan qo'shilgan")
    # Spaced repetition (SM-2 style, see learn/srs.py). due_at is empty for a
    # word that has never been reviewed — it counts as a new card.
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    interval_days = models.FloatField(default=0)
    ease = models.FloatField(default=2.5)
    reps = models.PositiveIntegerField(default=0)
    lapses = models.PositiveIntegerField(default=0)
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
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_accuracy = models.FloatField(null=True, blank=True)
    location_captured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def location_text(self):
        if self.latitude is None or self.longitude is None:
            return 'Saqlanmagan'
        return f"{self.latitude:.6f}, {self.longitude:.6f}"

    def __str__(self):
        return f"{self.username_attempt} | {self.ip} | {self.status}"

    class Meta:
        verbose_name = 'Login log'
        verbose_name_plural = 'Login loglar'
        ordering = ['-created_at']


class StudyGroup(models.Model):
    """A class of students (e.g. "Ertalabki IELTS") — staff filter results,
    live exams and analytics by it and compare its members."""
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    members = models.ManyToManyField(User, related_name='study_groups', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Guruh'
        verbose_name_plural = 'Guruhlar'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def initials(self):
        return ''.join(word[0] for word in self.name.split()[:2]).upper() or '?'

    @property
    def avatar_color(self):
        return User.AVATAR_COLORS[(self.pk or 0) % len(User.AVATAR_COLORS)]
