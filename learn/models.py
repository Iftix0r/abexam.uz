from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class LearnerProfile(models.Model):
    """XP, streak and chosen level for the English course.

    Lesson content itself lives in data/learn/*.json (see learn/content.py),
    so only the learner's own state is kept in the database.
    """
    LEVELS = (('A1', 'A1'), ('A2', 'A2'), ('B1', 'B1'), ('B2', 'B2'))

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learner')
    level = models.CharField(max_length=2, choices=LEVELS, blank=True)
    xp = models.PositiveIntegerField(default=0)
    streak = models.PositiveIntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    last_active = models.DateField(null=True, blank=True)
    daily_goal = models.PositiveSmallIntegerField(default=30, help_text='Kunlik XP maqsadi')

    class Meta:
        verbose_name = "O'quvchi profili"
        verbose_name_plural = "O'quvchi profillari"

    def __str__(self):
        return f"{self.user} · {self.xp} XP"

    @property
    def current_streak(self):
        # A streak shown on the page must already be broken if the learner
        # skipped yesterday — it's only reset in the DB on the next activity.
        if not self.last_active:
            return 0
        if self.last_active >= timezone.localdate() - timedelta(days=1):
            return self.streak
        return 0


class DailyXP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_xp')
    date = models.DateField()
    xp = models.PositiveIntegerField(default=0)

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
