from django.contrib import admin

from .models import DailyXP, LearnerProfile, LessonProgress


@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'level', 'xp', 'streak', 'best_streak', 'last_active', 'daily_goal')
    list_filter = ('level',)
    search_fields = ('user__username',)


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson_slug', 'best_score', 'attempts', 'completed_at')
    search_fields = ('user__username', 'lesson_slug')


@admin.register(DailyXP)
class DailyXPAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'xp')
    date_hierarchy = 'date'
