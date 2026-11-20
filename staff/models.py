import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Branch(models.Model):
    name = models.CharField(max_length=120, unique=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Filial'
        verbose_name_plural = 'Filiallar'

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Bo'lim"
        verbose_name_plural = "Bo'limlar"

    def __str__(self):
        return self.name


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', 'Super Admin'
        COORDINATOR = 'coordinator', 'Koordinator'
        HEAD = 'head', "Bo'lim rahbari"
        EMPLOYEE = 'employee', 'Xodim'
        NEW = 'new', 'Yangi xodim'

    class Position(models.TextChoices):
        DIRECTOR = 'director', 'Direktor'
        COORDINATOR = 'coordinator', 'Koordinator'
        DEPARTMENT_HEAD = 'department_head', "Bo‘lim boshlig‘i"
        ADMINISTRATOR = 'administrator', 'Administrator'
        ENGLISH_TEACHER = 'english_teacher', "Ingliz tili o‘qituvchisi"
        KOREAN_TEACHER = 'korean_teacher', "Koreys tili o‘qituvchisi"
        IT_TEACHER = 'it_teacher', "IT va dasturlash o‘qituvchisi"
        TARGETOLOGIST = 'targetologist', 'Targetolog'
        MARKETER = 'marketer', 'Marketolog'
        SMM = 'smm', 'SMM mutaxassisi'
        CONTENT = 'content', 'Kontent yaratuvchi'
        VIDEOGRAPHER = 'videographer', 'Videograf'
        ACCOUNTANT = 'accountant', 'Buxgalter'
        HR = 'hr', 'HR / Kadrlar'
        TECHNICAL = 'technical', 'Texnik xodim'
        OTHER = 'other', 'Boshqa'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.NEW, db_index=True)
    position = models.CharField(max_length=30, choices=Position.choices, default=Position.OTHER, db_index=True)
    job_title = models.CharField(max_length=120, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='direct_reports')
    hired_at = models.DateField(null=True, blank=True)
    work_start = models.TimeField(default=datetime.time(9, 0))
    work_end = models.TimeField(default=datetime.time(18, 0))
    work_days = models.CharField(max_length=20, default='1,2,3,4,5', help_text='1=Dushanba, 7=Yakshanba')
    is_approved = models.BooleanField(default=False, db_index=True)
    notifications_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Xodim profili'
        verbose_name_plural = 'Xodim profillari'

    def __str__(self):
        return self.user.display_name

    @property
    def can_manage(self):
        return self.role in {self.Role.SUPER_ADMIN, self.Role.COORDINATOR, self.Role.HEAD}


class StaffTelegramAccount(models.Model):
    chat_id = models.BigIntegerField(unique=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='staff_telegram')
    username = models.CharField(max_length=64, blank=True)
    first_name = models.CharField(max_length=128, blank=True)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'@{self.username}' if self.username else (self.first_name or str(self.chat_id))


class Task(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Yangi'
        IN_PROGRESS = 'in_progress', 'Jarayonda'
        REVIEW = 'review', 'Tekshiruvda'
        DONE = 'done', 'Bajarildi'
        OVERDUE = 'overdue', 'Kechikdi'
        CANCELLED = 'cancelled', 'Bekor qilindi'

    class Priority(models.TextChoices):
        LOW = 'low', 'Past'
        MEDIUM = 'medium', "O'rta"
        HIGH = 'high', 'Muhim'
        URGENT = 'urgent', 'Shoshilinch'

    title = models.CharField(max_length=200)
    description = models.TextField()
    assignee = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='tasks')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    created_by = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='created_tasks')
    reviewer = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='review_tasks')
    starts_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    expected_result = models.TextField(blank=True)
    attachment = models.FileField(upload_to='staff/tasks/%Y/%m/', blank=True)
    result_text = models.TextField(blank=True)
    result_file = models.FileField(upload_to='staff/results/%Y/%m/', blank=True)
    review_comment = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_at', '-priority']
        verbose_name = 'Vazifa'
        verbose_name_plural = 'Vazifalar'

    def __str__(self):
        return self.title

    @property
    def is_late(self):
        return self.status not in {self.Status.DONE, self.Status.CANCELLED} and self.due_at < timezone.now()


class TaskEvent(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='events')
    actor = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, related_name='task_events')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class DailyReport(models.Model):
    employee = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='daily_reports')
    date = models.DateField(default=timezone.localdate)
    completed = models.TextField("Bajarilgan ishlar")
    unfinished = models.TextField("Tugallanmagan ishlar", blank=True)
    problems = models.TextField("Muammolar", blank=True)
    tomorrow_plan = models.TextField("Ertangi reja")
    needs_help = models.TextField("Kerakli yordam", blank=True)
    reviewed_by = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['employee', 'date'], name='unique_staff_daily_report')]
        ordering = ['-date', '-created_at']


class Attendance(models.Model):
    employee = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField(default=timezone.localdate)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    late_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['employee', 'date'], name='unique_staff_attendance')]
        ordering = ['-date', 'employee__user__first_name']

    @property
    def is_late(self):
        if not self.check_in:
            return False
        local = timezone.localtime(self.check_in)
        return local.time() > self.employee.work_start


class LeaveRequest(models.Model):
    class Kind(models.TextChoices):
        LEAVE = 'leave', "Ta'til"
        PERMISSION = 'permission', 'Ruxsat'
        SICK = 'sick', 'Kasallik'
        SHIFT = 'shift', 'Smena almashtirish'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Kutilmoqda'
        APPROVED = 'approved', 'Tasdiqlandi'
        REJECTED = 'rejected', 'Rad etildi'

    employee = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='leave_requests')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING, db_index=True)
    manager_comment = models.TextField(blank=True)
    decided_by = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_leaves')
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError("Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas.")

    class Meta:
        ordering = ['-created_at']


class Announcement(models.Model):
    class Kind(models.TextChoices):
        NEWS = 'news', 'Yangilik'
        MEETING = 'meeting', "Yig'ilish"
        SCHEDULE = 'schedule', "Jadval o'zgarishi"
        EVENT = 'event', 'Tadbir'
        RULE = 'rule', 'Ichki qoida'
        URGENT = 'urgent', 'Shoshilinch'

    title = models.CharField(max_length=200)
    body = models.TextField()
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.NEWS)
    author = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='announcements')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    requires_ack = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    published_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    read_by = models.ManyToManyField(StaffProfile, blank=True, related_name='read_announcements')

    class Meta:
        ordering = ['-is_pinned', '-published_at']


class Suggestion(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Yangi'
        REVIEW = 'review', "Ko'rib chiqilmoqda"
        RESOLVED = 'resolved', 'Hal qilindi'
        REJECTED = 'rejected', 'Rad etildi'

    author = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='suggestions')
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_confidential = models.BooleanField(default=False)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Meeting(models.Model):
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField(db_index=True)
    location = models.CharField(max_length=200)
    agenda = models.TextField(blank=True)
    decisions = models.TextField(blank=True)
    organizer = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='organized_meetings')
    participants = models.ManyToManyField(StaffProfile, related_name='meetings')
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['starts_at']

    def __str__(self):
        return self.title


class KPIRecord(models.Model):
    employee = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='kpi_records')
    period = models.DateField(help_text='Hisobot oyining birinchi kuni')
    metric = models.CharField(max_length=150)
    target = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='created_kpis')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period', 'employee__user__first_name', 'metric']

    @property
    def progress(self):
        return min(100, round(float(self.actual / self.target * 100))) if self.target else 0


class KnowledgeDocument(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    file = models.FileField(upload_to='staff/knowledge/%Y/%m/', blank=True)
    link = models.URLField(blank=True)
    is_required = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='knowledge_documents')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class OnboardingItem(models.Model):
    employee = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='onboarding_items')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name='created_onboarding_items')

    class Meta:
        ordering = ['is_done', 'due_date', 'id']
