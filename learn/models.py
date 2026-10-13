from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class LearnerProfile(models.Model):
    """XP, streak and chosen level for the English course.

    Lesson content itself lives in data/learn/*.json (see learn/content.py),
    so only the learner's own state is kept in the database.
    """
    LEVELS = (('A1', 'A1'), ('A2', 'A2'), ('B1', 'B1'), ('B2', 'B2'), ('C1', 'C1'), ('C2', 'C2'))

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learner')
    level = models.CharField(max_length=2, choices=LEVELS, blank=True)
    xp = models.PositiveIntegerField(default=0)
    streak = models.PositiveIntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    last_active = models.DateField(null=True, blank=True)
    daily_goal = models.PositiveSmallIntegerField(default=30, help_text='Kunlik XP maqsadi')
    # Duolingo-style "streak freeze": one is earned every 7 days of streak
    # (max 2) and spent automatically on a missed day.
    streak_freezes = models.PositiveSmallIntegerField(default=0)
    # Unlocked achievement tiers, e.g. ["lessons:1", "streak:7"] (see gamification.py).
    badges = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "O'quvchi profili"
        verbose_name_plural = "O'quvchi profillari"

    def __str__(self):
        return f"{self.user} · {self.xp} XP"

    @property
    def current_streak(self):
        # A streak shown on the page must already be broken if the learner
        # skipped more days than their freezes cover — it's only updated in
        # the DB on the next activity.
        if not self.last_active:
            return 0
        missed = (timezone.localdate() - self.last_active).days - 1
        return self.streak if missed <= self.streak_freezes else 0


class DailyXP(models.Model):
    """One learner's day: XP plus the counters behind the daily quests."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_xp')
    date = models.DateField()
    xp = models.PositiveIntegerField(default=0)
    lessons = models.PositiveSmallIntegerField(default=0)
    perfect = models.PositiveSmallIntegerField(default=0, help_text='90%+ natijali darslar')
    reviews = models.PositiveSmallIntegerField(default=0)
    stories = models.PositiveSmallIntegerField(default=0)
    practice = models.PositiveSmallIntegerField(default=0)
    tutor = models.PositiveSmallIntegerField(default=0)
    chest = models.BooleanField(default=False, help_text="Kunlik topshiriqlar sandig'i ochilganmi")

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-date']
        verbose_name = 'Kunlik XP'
        verbose_name_plural = 'Kunlik XP'


class LessonProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson_slug = models.CharField(max_length=100)
    best_score = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'lesson_slug')
        verbose_name = 'Dars natijasi'
        verbose_name_plural = 'Dars natijalari'

    def __str__(self):
        return f"{self.user} · {self.lesson_slug} · {self.best_score}%"


class Mistake(models.Model):
    """An exercise the learner got wrong — served again in mixed practice
    until they answer it right twice in a row."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learn_mistakes')
    lesson_slug = models.CharField(max_length=100)
    step_index = models.PositiveSmallIntegerField()
    wrong_count = models.PositiveIntegerField(default=1)
    right_streak = models.PositiveSmallIntegerField(default=0)
    last_wrong_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'lesson_slug', 'step_index')
        verbose_name = 'Xato mashq'
        verbose_name_plural = 'Xato mashqlar'

    def __str__(self):
        return f"{self.user} · {self.lesson_slug}#{self.step_index}"


class ApiToken(models.Model):
    """Bearer token for the mobile app (see learn/api.py).

    Only a SHA-256 of the key is stored, so a database leak doesn't hand out
    working tokens; the plain key is shown to the app once, at login.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learn_api_tokens')
    key_hash = models.CharField(max_length=64, unique=True)
    device = models.CharField(max_length=100, blank=True, help_text='Telefon modeli, masalan: Samsung SM-A515F')
    platform = models.CharField(max_length=40, blank=True, help_text='Android 14 / iOS 17.4')
    app_version = models.CharField(max_length=20, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Ilova tokeni'
        verbose_name_plural = 'Ilova tokenlari'

    def __str__(self):
        return f"{self.user} · {self.device or 'ilova'}"


class LessonDraft(models.Model):
    """A half-finished lesson, so it can be resumed on another device.

    `data` uses the website player's format (templates/learn/lesson.html):
    {sig, queue, pos, firstTry: {idx: bool}, retried: [idx], mistakes: [{idx, right}], at}.
    It is removed when the lesson is completed.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_drafts')
    lesson_slug = models.CharField(max_length=100)
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'lesson_slug')
        verbose_name = 'Tugallanmagan dars'
        verbose_name_plural = 'Tugallanmagan darslar'


class AppRelease(models.Model):
    """A mobile app build offered for download; the newest one is "current"."""
    version = models.CharField(max_length=20, help_text='Masalan: 1.4.0')
    build = models.PositiveIntegerField(help_text="Build raqami (pubspec.yaml: version: 1.4.0+7 → 7)")
    apk = models.FileField(upload_to='app/', blank=True)
    url = models.URLField(blank=True, help_text="APK yuklanmasa: tashqi havola (Telegram, Google Drive...)")
    notes = models.TextField(blank=True, help_text="Nima yangi (har qator — bitta band)")
    force_update = models.BooleanField(default=False, help_text="Eski versiyada ishlashni to'xtatadi")
    downloads = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-build']
        verbose_name = 'Ilova versiyasi'
        verbose_name_plural = 'Ilova versiyalari'

    def __str__(self):
        return f"{self.version} ({self.build})"

    @classmethod
    def latest(cls):
        return cls.objects.order_by('-build').first()

    @property
    def available(self):
        return bool(self.apk or self.url)


class Checkpoint(models.Model):
    """Unit test or level exam (see checkpoints.py).

    Passing one also "tests out" of its lessons, Duolingo-style: lessons not
    done yet are marked done, so a learner who already knows the material
    can jump ahead.
    """
    KINDS = (('unit', "Bo'lim testi"), ('level', 'Daraja imtihoni'))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learn_checkpoints')
    kind = models.CharField(max_length=5, choices=KINDS)
    key = models.CharField(max_length=100, help_text="Bo'lim slugi yoki daraja kodi")
    best_score = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    passed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'kind', 'key')
        verbose_name = 'Test natijasi'
        verbose_name_plural = 'Test natijalari'

    @property
    def passed(self):
        return self.passed_at is not None
