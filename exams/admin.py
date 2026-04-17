from django.contrib import admin
from .models import Exam, Section, Question, UserResult, UserAnswer


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    fields = ('order', 'text', 'question_type', 'correct_answer', 'options', 'word_limit', 'explanation')
    ordering = ('order',)


class SectionInline(admin.StackedInline):
    model = Section
    extra = 0
    show_change_link = True
    fields = ('title', 'section_type', 'order', 'duration_minutes', 'audio_file', 'content')
    ordering = ('order',)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'exam_type', 'show_price', 'duration_minutes', 'sections_count', 'is_active', 'created_at')
    list_filter = ('exam_type', 'is_active')
    search_fields = ('title',)
    list_editable = ('is_active',)
    inlines = [SectionInline]
    readonly_fields = ('created_at', 'sections_count')

    def show_price(self, obj):
        return 'Bepul' if obj.price == 0 else f"{obj.price} so'm"
    show_price.short_description = 'Narxi'
    show_price.admin_order_field = 'price'

    def sections_count(self, obj):
        return obj.sections.count()
    sections_count.short_description = "Bo'limlar"


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'exam', 'section_type', 'order', 'duration_minutes')
    list_filter = ('section_type',)
    search_fields = ('title',)
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('short_text', 'section', 'question_type', 'order', 'word_limit')
    list_filter = ('question_type',)
    search_fields = ('text',)

    def short_text(self, obj):
        return obj.text[:60] + '...' if len(obj.text) > 60 else obj.text
    short_text.short_description = 'Savol'


@admin.register(UserResult)
class UserResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'exam', 'score', 'listening_score', 'reading_score', 'writing_score', 'speaking_score', 'completed_at')
    list_filter = ('exam',)
    search_fields = ('user__username',)
    readonly_fields = ('user', 'exam', 'score', 'listening_score', 'reading_score', 'writing_score', 'speaking_score', 'completed_at')

    def has_add_permission(self, request):
        return False


@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ('result', 'question', 'short_answer', 'is_correct')
    list_filter = ('is_correct',)
    readonly_fields = ('result', 'question', 'user_answer', 'is_correct')

    def short_answer(self, obj):
        return obj.user_answer[:60] if obj.user_answer else '—'
    short_answer.short_description = 'Javob'

    def has_add_permission(self, request):
        return False
