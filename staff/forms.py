from django import forms
from .models import (Announcement, DailyReport, KnowledgeDocument, KPIRecord, LeaveRequest,
                     Meeting, OnboardingItem, StaffProfile, Suggestion, Task)


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'field-control')


class TaskForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ('title', 'description', 'assignee', 'department', 'reviewer', 'starts_at', 'due_at',
                  'priority', 'expected_result', 'attachment')
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'due_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'expected_result': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {'title': 'Vazifa nomi', 'description': 'Batafsil tavsif', 'assignee': "Mas'ul xodim",
                  'department': "Bo'lim", 'reviewer': 'Tekshiruvchi', 'starts_at': 'Boshlanish vaqti',
                  'due_at': 'Yakunlash muddati', 'priority': 'Muhimlik', 'expected_result': 'Kutilayotgan natija',
                  'attachment': 'Material yoki fayl'}


class TaskSubmitForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ('result_text', 'result_file')
        widgets = {'result_text': forms.Textarea(attrs={'rows': 5})}
        labels = {'result_text': 'Bajarilgan ish haqida', 'result_file': 'Natija fayli'}


class DailyReportForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = DailyReport
        fields = ('completed', 'unfinished', 'problems', 'tomorrow_plan', 'needs_help')
        widgets = {
            'completed': forms.Textarea(attrs={'rows': 3}),
            'unfinished': forms.Textarea(attrs={'rows': 3}),
            'problems': forms.Textarea(attrs={'rows': 3}),
            'tomorrow_plan': forms.Textarea(attrs={'rows': 3}),
            'needs_help': forms.Textarea(attrs={'rows': 3}),
        }


class LeaveRequestForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ('kind', 'start_date', 'end_date', 'reason')
        widgets = {'start_date': forms.DateInput(attrs={'type': 'date'}),
                   'end_date': forms.DateInput(attrs={'type': 'date'}), 'reason': forms.Textarea(attrs={'rows': 4})}
        labels = {'kind': "So'rov turi", 'start_date': 'Boshlanish sanasi', 'end_date': 'Tugash sanasi',
                  'reason': 'Sabab'}


class AnnouncementForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ('title', 'body', 'kind', 'branch', 'department', 'requires_ack', 'is_pinned')
        widgets = {'body': forms.Textarea(attrs={'rows': 5})}


class SuggestionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Suggestion
        fields = ('title', 'body', 'is_confidential')
        widgets = {'body': forms.Textarea(attrs={'rows': 5})}
        labels = {'title': 'Mavzu', 'body': 'Taklif yoki muammo', 'is_confidential': 'Maxfiy murojaat'}


class StaffProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = StaffProfile
        fields = ('role', 'position', 'job_title', 'department', 'branch', 'manager', 'hired_at', 'work_start', 'work_end',
                  'work_days', 'is_approved', 'notifications_enabled')
        widgets = {'hired_at': forms.DateInput(attrs={'type': 'date'}),
                   'work_start': forms.TimeInput(attrs={'type': 'time'}),
                   'work_end': forms.TimeInput(attrs={'type': 'time'})}
        labels = {'role': 'Tizimdagi rol', 'position': 'Lavozim turi', 'job_title': 'Qo‘shimcha lavozim nomi', 'department': "Bo'lim", 'branch': 'Filial',
                  'manager': "Mas'ul rahbar", 'hired_at': 'Ishga kirgan sana', 'work_start': 'Ish boshlanishi',
                  'work_end': 'Ish tugashi', 'work_days': 'Ish kunlari', 'is_approved': 'Tasdiqlangan',
                  'notifications_enabled': 'Bildirishnomalar yoqilgan'}


class MeetingForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ('title', 'starts_at', 'location', 'agenda', 'participants')
        widgets = {'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
                   'agenda': forms.Textarea(attrs={'rows': 4}),
                   'participants': forms.SelectMultiple(attrs={'size': 8})}
        labels = {'title': 'Yig‘ilish mavzusi', 'starts_at': 'Sana va vaqt', 'location': 'Joy',
                  'agenda': 'Kun tartibi', 'participants': 'Ishtirokchilar'}


class KPIRecordForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = KPIRecord
        fields = ('employee', 'period', 'metric', 'target', 'actual', 'note')
        widgets = {'period': forms.DateInput(attrs={'type': 'date'})}
        labels = {'employee': 'Xodim', 'period': 'Davr', 'metric': 'Ko‘rsatkich',
                  'target': 'Reja', 'actual': 'Natija', 'note': 'Izoh'}


class KnowledgeDocumentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = KnowledgeDocument
        fields = ('title', 'description', 'department', 'file', 'link', 'is_required')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class OnboardingItemForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = OnboardingItem
        fields = ('employee', 'title', 'description', 'due_date')
        widgets = {'description': forms.Textarea(attrs={'rows': 3}),
                   'due_date': forms.DateInput(attrs={'type': 'date'})}
