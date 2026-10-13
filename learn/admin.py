from django.contrib import admin

from .models import ApiToken, AppRelease, DailyXP, LearnerProfile, LessonDraft, LessonProgress, Mistake


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


@admin.register(Mistake)
class MistakeAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson_slug', 'step_index', 'wrong_count', 'right_streak', 'last_wrong_at')
    search_fields = ('user__username', 'lesson_slug')


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    # Deleting a row signs that device out of the app.
    list_display = ('user', 'device', 'created_at', 'last_used_at')
    search_fields = ('user__username', 'device')
    readonly_fields = ('user', 'key_hash', 'device', 'created_at', 'last_used_at')


@admin.register(AppRelease)
class AppReleaseAdmin(admin.ModelAdmin):
    list_display = ('version', 'build', 'force_update', 'downloads', 'created_at')


@admin.register(LessonDraft)
class LessonDraftAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson_slug', 'updated_at')
    search_fields = ('user__username', 'lesson_slug')
