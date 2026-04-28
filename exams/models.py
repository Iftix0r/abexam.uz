from django.db import models
from django.conf import settings
from ckeditor.fields import RichTextField

class Exam(models.Model):
    EXAM_TYPES = (
        ('mock', 'Mock Test'),
        ('reading', 'Reading Practice'),
        ('listening', 'Listening Practice'),
        ('writing', 'Writing Practice'),
        ('speaking', 'Speaking Practice'),
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPES, default='mock')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    duration_minutes = models.IntegerField(default=60)
    is_active = models.BooleanField(default=True)
    is_ai_generated = models.BooleanField(default=False)
    ai_metadata = models.JSONField(null=True, blank=True, help_text='AI generation params: variant, topic, model')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Imtihon'
        verbose_name_plural = 'Imtihonlar'

class Section(models.Model):
    SECTION_TYPES = (
        ('listening', 'Listening'),
        ('reading', 'Reading'),
        ('writing', 'Writing'),
        ('speaking', 'Speaking'),
    )
    exam = models.ForeignKey(Exam, related_name='sections', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    section_type = models.CharField(max_length=20, choices=SECTION_TYPES)
    content = RichTextField(blank=True, null=True)
    audio_file = models.FileField(upload_to='exams/audio/', blank=True, null=True)
    extra_data = models.JSONField(null=True, blank=True, help_text='Vocabulary, etc.')
    order = models.IntegerField(default=1)
    duration_minutes = models.IntegerField(default=0, help_text='0 = umumiy exam vaqtidan foydalaniladi')

    def __str__(self):
        return f"{self.exam.title} - {self.get_section_type_display()}"

    class Meta:
        ordering = ['order']
        verbose_name = 'Bo\'lim'
        verbose_name_plural = 'Bo\'limlar'

class Question(models.Model):
    QUESTION_TYPES = (
        ('mcq', 'Multiple Choice'),
        ('tfng', 'True/False/Not Given'),
        ('gap_fill', 'Gap Fill'),
        ('matching', 'Matching'),
        ('writing_task', 'Writing Task (Essay)'),
        ('short_answer', 'Short Answer'),
    )
    section = models.ForeignKey(Section, related_name='questions', on_delete=models.CASCADE)
    text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    options = models.JSONField(default=list, blank=True, help_text='MCQ uchun: [{"key": "A", "text": "..."}, ...]')
    correct_answer = models.CharField(max_length=255, blank=True)
    explanation = models.TextField(blank=True)
    model_answer = models.TextField(blank=True, help_text='Ideal response for Writing/Speaking')
    order = models.IntegerField(default=1)
    word_limit = models.IntegerField(default=0, help_text='Writing task uchun minimum so\'z soni (0 = chegarasiz)')

    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}"

    class Meta:
        ordering = ['order']
        verbose_name = 'Savol'
        verbose_name_plural = 'Savollar'

class UserResult(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    score = models.FloatField(default=0.0)
    listening_score = models.FloatField(default=0.0)
    reading_score = models.FloatField(default=0.0)
    writing_score = models.FloatField(default=0.0)
    speaking_score = models.FloatField(default=0.0)
    writing_feedback = models.JSONField(null=True, blank=True)
    speaking_feedback = models.JSONField(null=True, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.exam.title} ({self.score})"

    def score_pct(self):
        return round(self.score / 9 * 100) if self.score else 0

    def listening_pct(self):
        return round(self.listening_score / 9 * 100) if self.listening_score else 0

    def reading_pct(self):
        return round(self.reading_score / 9 * 100) if self.reading_score else 0

    def writing_pct(self):
        return round(self.writing_score / 9 * 100) if self.writing_score else 0

    def speaking_pct(self):
        return round(self.speaking_score / 9 * 100) if self.speaking_score else 0

    class Meta:
        verbose_name = 'Natija'
        verbose_name_plural = 'Natijalar'


class UserAnswer(models.Model):
    result = models.ForeignKey(UserResult, related_name='answers', on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True)
    user_answer = models.TextField(blank=True)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = ('result', 'question')
        verbose_name = "Foydalanuvchi javobi"
        verbose_name_plural = "Foydalanuvchi javoblari"
