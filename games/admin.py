from django.contrib import admin

from .models import GameScore


@admin.register(GameScore)
class GameScoreAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'level', 'score', 'correct', 'mistakes', 'xp', 'created_at')
    list_filter = ('game', 'level')
    search_fields = ('user__username',)
