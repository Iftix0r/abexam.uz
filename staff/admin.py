from django.contrib import admin
from .models import Announcement, Branch, DailyReport, Department, LeaveRequest, StaffProfile, StaffTelegramAccount, Suggestion, Task, TaskEvent


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'job_title', 'department', 'branch', 'is_approved')
    list_filter = ('role', 'is_approved', 'department', 'branch')
    search_fields = ('user__first_name', 'user__last_name', 'user__username', 'job_title')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'assignee', 'status', 'priority', 'due_at')
    list_filter = ('status', 'priority', 'department')
    search_fields = ('title', 'description', 'assignee__user__first_name', 'assignee__user__last_name')


admin.site.register([Branch, Department, StaffTelegramAccount, TaskEvent, DailyReport, LeaveRequest, Announcement, Suggestion])
