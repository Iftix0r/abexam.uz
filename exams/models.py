import os
from datetime import timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models.signals import post_delete
from django.dispatch import receiver
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
    is_reviewed = models.BooleanField(default=False, help_text='Mutaxassis tomonidan ko\'rib chiqilgan')
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
    image = models.ImageField(upload_to='exams/images/', blank=True, null=True)
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

class UserResultQuerySet(models.QuerySet):
    def graded(self):
        return self.filter(status=UserResult.STATUS_GRADED)

    def pending(self):
        return self.filter(status=UserResult.STATUS_PENDING)


class UserResult(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_GRADED = 'graded'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Tekshirilmoqda'),
        (STATUS_GRADED, 'Baholangan'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    score = models.FloatField(default=0.0)
    listening_score = models.FloatField(default=0.0)
    reading_score = models.FloatField(default=0.0)
    writing_score = models.FloatField(default=0.0)
    speaking_score = models.FloatField(default=0.0)
    writing_feedback = models.JSONField(null=True, blank=True)
    speaking_feedback = models.JSONField(null=True, blank=True)
    # Writing is graded by staff by hand: until then the whole result is
    # held back from the student (status=pending), not just the writing band.
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_GRADED, db_index=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='graded_results')
    graded_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    objects = UserResultQuerySet.as_manager()

    def __str__(self):
        return f"{self.user.username} - {self.exam.title} ({self.score})"

    @property
    def is_pending(self):
        return self.status == self.STATUS_PENDING

    @staticmethod
    def _band_pct(band):
        return round(band / 9 * 100) if band else 0

    def score_pct(self):
        return self._band_pct(self.score)

    def listening_pct(self):
        return self._band_pct(self.listening_score)

    def reading_pct(self):
        return self._band_pct(self.reading_score)

    def writing_pct(self):
        return self._band_pct(self.writing_score)

    def speaking_pct(self):
        return self._band_pct(self.speaking_score)

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


# The exam page autosaves every 20s and heartbeats every minute, so an
# unsubmitted attempt not seen for this long has stopped (closed tab, lost
# connection).
ATTEMPT_ONLINE_WINDOW = timedelta(minutes=2)


class ExamAttempt(models.Model):
    """Server-side copy of an attempt, autosaved from the exam page while it
    is being taken. It lets staff watch a running exam live and turn the
    answers into a result if the student's own submit never got through
    (the browser's localStorage draft is otherwise the only copy)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exam_attempts')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    # Generated by the browser once per attempt; also makes submit retries idempotent.
    client_id = models.CharField(max_length=64)
    answers = models.JSONField(default=dict, blank=True)
    answered_count = models.IntegerField(default=0)
    current_section = models.CharField(max_length=20, blank=True)
    # submitted_at is the "done" marker: result is SET_NULL, so deleting the
    # result alone doesn't make the attempt look unsent again.
    result = models.ForeignKey(UserResult, on_delete=models.SET_NULL, null=True, blank=True, related_name='attempts')
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    # Live-monitoring details reported by the exam page.
    time_left = models.IntegerField(null=True, blank=True, help_text="Joriy bo'lim taymeridagi soniyalar")
    leave_count = models.IntegerField(default=0, help_text='Test oynasidan necha marta chiqqan')
    away_seconds = models.IntegerField(default=0)
    pasted_chars = models.IntegerField(default=0, help_text="Writing'ga joylangan (paste) belgilar")
    ip = models.GenericIPAddressField(null=True, blank=True)
    # Staff → student messages / extra time, picked up by the page on its
    # next autosave: [{"id": n, "type": "message"|"extra_time", ...}].
    commands = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        unique_together = ('user', 'exam', 'client_id')
        ordering = ['-last_seen_at']
        verbose_name = 'Urinish'
        verbose_name_plural = 'Urinishlar'

    def __str__(self):
        return f"{self.user.username} - {self.exam.title} ({self.answered_count})"

    @property
    def is_submitted(self):
        return self.submitted_at is not None

    def add_command(self, **command):
        """Queues a command for the exam page; ids only grow, so the page
        applies each one exactly once. Only the latest few are kept."""
        command['id'] = max((c['id'] for c in self.commands), default=0) + 1
        self.commands = (self.commands + [command])[-10:]


def _delete_file(path):
    if path and os.path.isfile(path):
        os.remove(path)


@receiver(post_delete, sender=Section)
def section_files_cleanup(sender, instance, **kwargs):
    if instance.audio_file:
        _delete_file(instance.audio_file.path)
    if instance.image:
        _delete_file(instance.image.path)
