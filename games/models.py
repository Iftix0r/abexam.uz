from django.conf import settings
from django.db import models


class GameScore(models.Model):
    """One finished round."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_scores')
    game = models.CharField(max_length=20)
    level = models.CharField(max_length=2)
    score = models.PositiveIntegerField()
    correct = models.PositiveSmallIntegerField()
    mistakes = models.PositiveSmallIntegerField(default=0)
    combo = models.PositiveSmallIntegerField(default=0, help_text='Eng uzun ketma-ket to\'g\'ri javoblar')
    perfect = models.BooleanField(default=False)
    xp = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "O'yin natijasi"
        verbose_name_plural = "O'yin natijalari"


class GameMistake(models.Model):
    """A word the student got wrong, waiting to be practised until answered right."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_mistakes')
    en = models.CharField(max_length=120)
    uz = models.CharField(max_length=200)
    level = models.CharField(max_length=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'en'], name='game_mistake_once')]
