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
    xp = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "O'yin natijasi"
        verbose_name_plural = "O'yin natijalari"
