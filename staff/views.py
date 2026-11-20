from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (AnnouncementForm, DailyReportForm, LeaveRequestForm, StaffProfileForm,
                    GoalForm, KnowledgeDocumentForm, KPIRecordForm, MeetingForm, OnboardingItemForm,
                    SuggestionForm, TaskForm, TaskSubmitForm)
from .models import (Announcement, Attendance, DailyReport, Department, Goal, KnowledgeDocument,
                     KPIRecord, LeaveRequest, Meeting, OnboardingItem, StaffProfile,
                     Suggestion, Task, TaskEvent)
from .services import notify_group, notify_profiles, notify_task, notify_user


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        profile = StaffProfile.objects.select_related('department', 'branch').filter(user=request.user, is_approved=True).first()
        # A real Django superuser can never lose AB Staff director access,
        # even if their Staff role was accidentally changed in the UI.
        if request.user.is_superuser:
            profile, _ = StaffProfile.objects.update_or_create(
                user=request.user,
                defaults={
                    'role': StaffProfile.Role.SUPER_ADMIN,
                    'position': StaffProfile.Position.DIRECTOR,
                    'job_title': 'Direktor',
                    'is_approved': True,
                },
            )
        if not profile:
            return render(request, 'staff/pending.html', status=403)
        request.staff_profile = profile
        return view(request, *args, **kwargs)
    return wrapped


def visible_tasks(profile):
    qs = Task.objects.select_related('assignee__user', 'department', 'reviewer__user', 'created_by__user')
    if profile.role == StaffProfile.Role.SUPER_ADMIN:
        return qs
    if profile.role == StaffProfile.Role.COORDINATOR:
        return qs.filter(Q(created_by=profile) | Q(assignee__manager=profile) | Q(assignee=profile)).distinct()
    if profile.role == StaffProfile.Role.HEAD:
        return qs.filter(Q(department=profile.department) | Q(assignee=profile)).distinct()
    return qs.filter(Q(assignee=profile) | Q(reviewer=profile)).distinct()


@staff_required
def dashboard(request):
    p = request.staff_profile
    tasks = visible_tasks(p)
    now = timezone.now()
    stats = {
        'active': tasks.exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).count(),
        'done': tasks.filter(status=Task.Status.DONE).count(),
        'late': tasks.exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).filter(due_at__lt=now).count(),
        'review': tasks.filter(status=Task.Status.REVIEW).count(),
        'team': StaffProfile.objects.filter(is_approved=True).count() if p.can_manage else 0,
        'pending_leaves': LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).count() if p.can_manage else 0,
        'reports_today': DailyReport.objects.filter(date=timezone.localdate()).count() if p.can_manage else 0,
    }
    announcements = Announcement.objects.filter(Q(branch__isnull=True) | Q(branch=p.branch),
                                                 Q(department__isnull=True) | Q(department=p.department),
                                                 published_at__lte=now).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))[:4]
    return render(request, 'staff/dashboard.html', {'profile': p, 'stats': stats, 'tasks': tasks[:7],
                                                    'announcements': announcements,
                                                    'today_report': DailyReport.objects.filter(employee=p, date=timezone.localdate()).first(),
                                                    'today_attendance': Attendance.objects.filter(employee=p, date=timezone.localdate()).first()})


@staff_required
def control_center(request):
    p = request.staff_profile
    if not p.can_manage:
        return HttpResponseForbidden()
    today, now = timezone.localdate(), timezone.now()
    people = StaffProfile.objects.filter(is_approved=True).select_related(
        'user', 'user__staff_telegram', 'department', 'branch', 'manager__user')
    if p.role == StaffProfile.Role.HEAD:
        people = people.filter(department=p.department)
    elif p.role == StaffProfile.Role.COORDINATOR:
        people = people.filter(Q(manager=p) | Q(pk=p.pk))

    people_ids = list(people.values_list('pk', flat=True))
    on_leave_ids = LeaveRequest.objects.filter(
        employee_id__in=people_ids, status=LeaveRequest.Status.APPROVED,
        start_date__lte=today, end_date__gte=today).values_list('employee_id', flat=True)
    local_time = timezone.localtime(now).time()
    workday_people = [item for item in people if str(today.isoweekday()) in item.work_days.split(',')]
    attendance_expected = [item.pk for item in workday_people if local_time >= item.work_start]
    report_expected = [item.pk for item in workday_people if local_time >= item.work_end]
    missing_reports = people.filter(pk__in=report_expected).exclude(daily_reports__date=today)
    absent = people.filter(pk__in=attendance_expected).exclude(pk__in=on_leave_ids).exclude(attendance__date=today)
    overdue = visible_tasks(p).exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).filter(
        due_at__lt=now).order_by('due_at')
    pending_leaves = LeaveRequest.objects.filter(
        employee_id__in=people_ids, status=LeaveRequest.Status.PENDING).select_related('employee__user')
    pending_staff = StaffProfile.objects.filter(is_approved=False).select_related('user', 'department') \
        if p.role == StaffProfile.Role.SUPER_ADMIN else StaffProfile.objects.none()
    bot_unlinked = people.filter(user__staff_telegram__isnull=True)
    context = {
        'counts': {'overdue': overdue.count(), 'missing_reports': missing_reports.count(),
                   'absent': absent.count(), 'pending_leaves': pending_leaves.count(),
                   'pending_staff': pending_staff.count(), 'bot_unlinked': bot_unlinked.count()},
        'overdue': overdue[:20], 'missing_reports': missing_reports[:20], 'absent': absent[:20],
        'pending_leaves': pending_leaves[:20], 'pending_staff': pending_staff[:20],
        'bot_unlinked': bot_unlinked[:20], 'today': today,
    }
    return render(request, 'staff/control_center.html', context)


@staff_required
@require_POST
def control_remind(request, kind):
    p = request.staff_profile
    if not p.can_manage or kind not in {'reports', 'attendance', 'deadlines'}:
        return HttpResponseForbidden()
    today, now = timezone.localdate(), timezone.now()
    people = StaffProfile.objects.filter(is_approved=True)
    if p.role == StaffProfile.Role.HEAD:
        people = people.filter(department=p.department)
    elif p.role == StaffProfile.Role.COORDINATOR:
        people = people.filter(Q(manager=p) | Q(pk=p.pk))
    if kind == 'reports':
        targets = people.exclude(daily_reports__date=today)
        sent = notify_profiles(targets, '✅ Kunlik hisobot eslatmasi',
                               'Rahbaringiz bugungi hisobotni yuborishingizni so‘radi.', '/staff/report/')
    elif kind == 'attendance':
        targets = people.exclude(attendance__date=today)
        sent = notify_profiles(targets, '🕘 Davomat eslatmasi',
                               'Ishga kelish vaqtingizni Staff kabinetida belgilang.', '/staff/attendance/')
    else:
        sent = 0
        tasks = visible_tasks(p).exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).filter(due_at__lt=now)
        for task in tasks:
            sent += int(notify_user(task.assignee.user, '🔴 Kechikkan vazifa', task.title, f'/staff/tasks/{task.pk}/'))
    messages.success(request, f'{sent} ta eslatma Staff bot orqali yuborildi.')
    return redirect('staff:control_center')


@staff_required
def team_list(request):
    p = request.staff_profile
    profiles = StaffProfile.objects.select_related(
        'user', 'user__staff_telegram', 'department', 'branch', 'manager__user'
    ).annotate(
        active_tasks=Count('tasks', filter=~Q(tasks__status__in=[Task.Status.DONE, Task.Status.CANCELLED]), distinct=True),
        done_tasks=Count('tasks', filter=Q(tasks__status=Task.Status.DONE), distinct=True),
    )
    if not p.can_manage:
        profiles = profiles.filter(is_approved=True)
    elif p.role == StaffProfile.Role.HEAD:
        profiles = profiles.filter(department=p.department)
    elif p.role == StaffProfile.Role.COORDINATOR:
        profiles = profiles.filter(Q(manager=p) | Q(pk=p.pk))
    scope = profiles
    stats = {
        'total': scope.count(),
        'active': scope.filter(is_approved=True).count(),
        'pending': scope.filter(is_approved=False).count(),
        'telegram': scope.filter(user__staff_telegram__isnull=False).count(),
    }
    search = request.GET.get('q', '').strip()
    if search:
        profiles = profiles.filter(Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search) |
                                   Q(job_title__icontains=search) | Q(department__name__icontains=search) |
                                   Q(position__icontains=search))
    role = request.GET.get('role', '')
    if role in StaffProfile.Role.values:
        profiles = profiles.filter(role=role)
    department = request.GET.get('department', '')
    if department.isdigit():
        profiles = profiles.filter(department_id=department)
    status = request.GET.get('status', '')
    if status == 'active':
        profiles = profiles.filter(is_approved=True)
    elif status == 'pending':
        profiles = profiles.filter(is_approved=False)
    elif status == 'telegram':
        profiles = profiles.filter(user__staff_telegram__isnull=False)
    profiles = profiles.order_by('-is_approved', 'department__name', 'user__first_name', 'user__last_name')
    page_obj = Paginator(profiles, 24).get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)
    departments = Department.objects.filter(is_active=True)
    return render(request, 'staff/team_list.html', {
        'profiles': page_obj, 'page_obj': page_obj, 'query_params': query_params.urlencode(),
        'search': search, 'stats': stats, 'roles': StaffProfile.Role.choices,
        'departments': departments, 'selected_role': role, 'selected_department': department,
        'selected_status': status,
    })


@staff_required
def team_add(request):
    if request.staff_profile.role != StaffProfile.Role.SUPER_ADMIN:
        return HttpResponseForbidden()
    User = get_user_model()
    query = request.GET.get('q', '').strip()
    users = User.objects.filter(staff_profile__isnull=True).order_by('-date_joined')
    if query:
        users = users.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) |
                             Q(username__icontains=query) | Q(phone_number__icontains=query))
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('user_id'), staff_profile__isnull=True)
        profile = StaffProfile.objects.create(user=user, role=StaffProfile.Role.NEW,
                                              position=StaffProfile.Position.OTHER, is_approved=False)
        messages.success(request, 'Xodim Staff tizimiga qo‘shildi. Endi rol, lavozim va bo‘limini belgilang.')
        return redirect('staff:team_detail', pk=profile.pk)
    return render(request, 'staff/team_add.html', {'users': users[:50], 'search': query})


@staff_required
def team_detail(request, pk):
    viewer = request.staff_profile
    profile = get_object_or_404(StaffProfile.objects.select_related('user', 'department', 'branch', 'manager__user'), pk=pk)
    if not viewer.can_manage and profile.pk != viewer.pk:
        return HttpResponseForbidden()
    if viewer.role == StaffProfile.Role.HEAD and profile.department_id != viewer.department_id:
        return HttpResponseForbidden()
    if viewer.role == StaffProfile.Role.COORDINATOR and profile.pk != viewer.pk and profile.manager_id != viewer.pk:
        return HttpResponseForbidden()
    tasks = Task.objects.filter(assignee=profile)
    stats = {'active': tasks.exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).count(),
             'done': tasks.filter(status=Task.Status.DONE).count(),
             'late': tasks.exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).filter(due_at__lt=timezone.now()).count(),
             'reports': profile.daily_reports.count()}
    form = StaffProfileForm(request.POST or None, instance=profile) if viewer.role == StaffProfile.Role.SUPER_ADMIN else None
    if request.method == 'POST' and form and form.is_valid():
        updated = form.save(commit=False)
        if updated.user.is_superuser:
            updated.role = StaffProfile.Role.SUPER_ADMIN
            updated.position = StaffProfile.Position.DIRECTOR
            updated.is_approved = True
        updated.save()
        messages.success(request, 'Xodim profili yangilandi.')
        return redirect('staff:team_detail', pk=profile.pk)
    return render(request, 'staff/team_detail.html', {'member': profile, 'stats': stats, 'tasks': tasks[:10], 'form': form})


@staff_required
def reports(request):
    p = request.staff_profile
    if not p.can_manage:
        qs = DailyReport.objects.filter(employee=p)
    elif p.role == StaffProfile.Role.SUPER_ADMIN:
        qs = DailyReport.objects.all()
    elif p.role == StaffProfile.Role.HEAD:
        qs = DailyReport.objects.filter(employee__department=p.department)
    else:
        qs = DailyReport.objects.filter(Q(employee__manager=p) | Q(employee=p))
    qs = qs.select_related('employee__user', 'employee__department')
    date = request.GET.get('date')
    if date:
        qs = qs.filter(date=date)
    return render(request, 'staff/reports.html', {'reports': qs, 'selected_date': date})


@staff_required
def attendance(request):
    p = request.staff_profile
    today = timezone.localdate()
    item = Attendance.objects.filter(employee=p, date=today).first()
    qs = Attendance.objects.select_related('employee__user', 'employee__department')
    if not p.can_manage:
        qs = qs.filter(employee=p)
    elif p.role == StaffProfile.Role.HEAD:
        qs = qs.filter(employee__department=p.department)
    elif p.role == StaffProfile.Role.COORDINATOR:
        qs = qs.filter(Q(employee__manager=p) | Q(employee=p))
    return render(request, 'staff/attendance.html', {'today_attendance': item, 'attendance_rows': qs[:100]})


@staff_required
@require_POST
def attendance_action(request, action):
    p = request.staff_profile
    item, _ = Attendance.objects.get_or_create(employee=p, date=timezone.localdate())
    if action == 'in' and not item.check_in:
        item.check_in = timezone.now()
        item.late_reason = request.POST.get('late_reason', '')[:300]
        item.save()
        if item.is_late and p.manager:
            notify_user(p.manager.user, '🕘 Xodim kechikdi',
                        f'{p.user.display_name} — {timezone.localtime(item.check_in):%H:%M}. {item.late_reason}',
                        '/staff/attendance/')
        messages.success(request, 'Ishga kelgan vaqtingiz belgilandi.')
    elif action == 'out' and item.check_in and not item.check_out:
        item.check_out = timezone.now(); item.save()
        messages.success(request, 'Ishdan chiqqan vaqtingiz belgilandi.')
    return redirect('staff:attendance')


@staff_required
def suggestions(request):
    p = request.staff_profile
    qs = Suggestion.objects.select_related('author__user', 'author__department')
    if not p.can_manage:
        qs = qs.filter(author=p)
    elif p.role != StaffProfile.Role.SUPER_ADMIN:
        qs = qs.filter(author__department=p.department)
    return render(request, 'staff/suggestions.html', {'suggestions': qs, 'suggestion_statuses': Suggestion.Status.choices})


@staff_required
@require_POST
def suggestion_status(request, pk):
    p = request.staff_profile
    if not p.can_manage:
        return HttpResponseForbidden()
    item = get_object_or_404(Suggestion, pk=pk)
    status = request.POST.get('status')
    if status in Suggestion.Status.values:
        item.status = status; item.save(update_fields=['status'])
        messages.success(request, 'Murojaat holati yangilandi.')
    return redirect('staff:suggestions')


@staff_required
def meetings(request):
    p = request.staff_profile
    qs = Meeting.objects.filter(Q(participants=p) | Q(organizer=p)).select_related('organizer__user').distinct()
    if p.role == StaffProfile.Role.SUPER_ADMIN:
        qs = Meeting.objects.select_related('organizer__user').all()
    form = MeetingForm(request.POST or None) if p.can_manage else None
    if request.method == 'POST' and form and form.is_valid():
        item = form.save(commit=False); item.organizer = p; item.save(); form.save_m2m()
        notify_profiles(item.participants.filter(is_approved=True), '📅 Yangi yig‘ilish',
                        f'{item.title}\n{item.starts_at:%d.%m.%Y %H:%M}\n{item.location}', '/staff/meetings/')
        messages.success(request, 'Yig‘ilish yaratildi va ishtirokchilarga yuborildi.')
        return redirect('staff:meetings')
    return render(request, 'staff/meetings.html', {'meetings': qs, 'form': form})


@staff_required
@require_POST
def meeting_decisions(request, pk):
    p = request.staff_profile
    meeting = get_object_or_404(Meeting, pk=pk)
    if meeting.organizer_id != p.pk and p.role != StaffProfile.Role.SUPER_ADMIN:
        return HttpResponseForbidden()
    meeting.decisions = request.POST.get('decisions', '').strip(); meeting.save(update_fields=['decisions'])
    messages.success(request, 'Yig‘ilish qarorlari saqlandi.')
    return redirect('staff:meetings')


@staff_required
def kpi(request):
    p = request.staff_profile
    qs = KPIRecord.objects.select_related('employee__user', 'employee__department')
    if not p.can_manage:
        qs = qs.filter(employee=p)
    elif p.role == StaffProfile.Role.HEAD:
        qs = qs.filter(employee__department=p.department)
    elif p.role == StaffProfile.Role.COORDINATOR:
        qs = qs.filter(Q(employee__manager=p) | Q(employee=p))
    form = KPIRecordForm(request.POST or None) if p.can_manage else None
    if request.method == 'POST' and form and form.is_valid():
        item = form.save(commit=False); item.created_by = p; item.save()
        notify_user(item.employee.user, '📊 KPI yangilandi', f'{item.metric}: {item.actual}/{item.target}', '/staff/kpi/')
        messages.success(request, 'KPI ko‘rsatkichi saqlandi.'); return redirect('staff:kpi')
    return render(request, 'staff/kpi.html', {'records': qs[:200], 'form': form})


@staff_required
def knowledge(request):
    p = request.staff_profile
    qs = KnowledgeDocument.objects.filter(Q(department__isnull=True) | Q(department=p.department)).select_related('department')
    form = KnowledgeDocumentForm(request.POST or None, request.FILES or None) if p.can_manage else None
    if request.method == 'POST' and form and form.is_valid():
        item = form.save(commit=False); item.uploaded_by = p; item.save()
        messages.success(request, 'Hujjat bilimlar bazasiga qo‘shildi.'); return redirect('staff:knowledge')
    return render(request, 'staff/knowledge.html', {'documents': qs, 'form': form})


@staff_required
def onboarding(request):
    p = request.staff_profile
    qs = OnboardingItem.objects.select_related('employee__user')
    if not p.can_manage:
        qs = qs.filter(employee=p)
    form = OnboardingItemForm(request.POST or None) if p.can_manage else None
    if request.method == 'POST' and form and form.is_valid():
        item = form.save(commit=False); item.created_by = p; item.save()
        notify_user(item.employee.user, '🎓 Yangi moslashuv vazifasi', item.title, '/staff/onboarding/')
        messages.success(request, 'Onboarding vazifasi qo‘shildi.'); return redirect('staff:onboarding')
    return render(request, 'staff/onboarding.html', {'items': qs, 'form': form})


@staff_required
@require_POST
def onboarding_done(request, pk):
    item = get_object_or_404(OnboardingItem, pk=pk, employee=request.staff_profile)
    item.is_done = True; item.completed_at = timezone.now(); item.save(update_fields=['is_done', 'completed_at'])
    return redirect('staff:onboarding')


@staff_required
def goals(request):
    p = request.staff_profile
    qs = Goal.objects.select_related('owner__user', 'department').prefetch_related('tasks')
    if not p.can_manage:
        qs = qs.filter(Q(owner=p) | Q(department=p.department)).distinct()
    elif p.role == StaffProfile.Role.HEAD:
        qs = qs.filter(department=p.department)
    elif p.role == StaffProfile.Role.COORDINATOR:
        qs = qs.filter(Q(owner__manager=p) | Q(owner=p)).distinct()
    form = GoalForm(request.POST or None) if p.can_manage else None
    if request.method == 'POST' and form and form.is_valid():
        item = form.save(commit=False); item.created_by = p; item.save(); form.save_m2m()
        notify_user(item.owner.user, '🎯 Yangi maqsad', f'{item.title}\nMuddat: {item.target_date:%d.%m.%Y}', '/staff/goals/')
        messages.success(request, 'Maqsad yaratildi.'); return redirect('staff:goals')
    return render(request, 'staff/goals.html', {'goals': qs, 'form': form})


@staff_required
def task_list(request):
    tasks = visible_tasks(request.staff_profile)
    status = request.GET.get('status')
    if status in Task.Status.values:
        tasks = tasks.filter(status=status)
    if request.GET.get('period') == 'today':
        tasks = tasks.filter(due_at__date=timezone.localdate())
    return render(request, 'staff/task_list.html', {'tasks': tasks, 'selected_status': status,
                                                    'statuses': Task.Status.choices})


@staff_required
def task_create(request):
    p = request.staff_profile
    if not p.can_manage:
        return HttpResponseForbidden('Vazifa yaratish huquqi yo‘q.')
    initial = {}
    if request.GET.get('assignee', '').isdigit():
        initial['assignee'] = request.GET['assignee']
    form = TaskForm(request.POST or None, request.FILES or None, initial=initial)
    allowed = StaffProfile.objects.filter(is_approved=True)
    if p.role == StaffProfile.Role.HEAD:
        allowed = allowed.filter(department=p.department)
    elif p.role == StaffProfile.Role.COORDINATOR:
        allowed = allowed.filter(Q(manager=p) | Q(pk=p.pk))
    form.fields['assignee'].queryset = allowed.select_related('user')
    form.fields['reviewer'].queryset = StaffProfile.objects.filter(is_approved=True).select_related('user')
    if request.method == 'POST' and form.is_valid():
        task = form.save(commit=False)
        task.created_by = p
        task.save()
        TaskEvent.objects.create(task=task, actor=p, to_status=task.status, comment='Vazifa yaratildi')
        notify_task(task)
        messages.success(request, 'Vazifa yaratildi va xodimga bildirishnoma yuborildi.')
        return redirect('staff:task_detail', pk=task.pk)
    return render(request, 'staff/form.html', {'form': form, 'title': 'Yangi vazifa', 'button': 'Vazifa yaratish'})


@staff_required
def task_detail(request, pk):
    task = get_object_or_404(visible_tasks(request.staff_profile), pk=pk)
    return render(request, 'staff/task_detail.html', {'task': task, 'submit_form': TaskSubmitForm()})


@staff_required
@require_POST
def task_action(request, pk, action):
    p = request.staff_profile
    task = get_object_or_404(visible_tasks(p), pk=pk)
    old = task.status
    comment = request.POST.get('comment', '').strip()
    if action == 'start' and task.assignee_id == p.pk and task.status == Task.Status.NEW:
        task.status = Task.Status.IN_PROGRESS
    elif action == 'submit' and task.assignee_id == p.pk and task.status in {Task.Status.NEW, Task.Status.IN_PROGRESS}:
        form = TaskSubmitForm(request.POST, request.FILES, instance=task)
        if not form.is_valid():
            messages.error(request, 'Natija matnini tekshiring.')
            return redirect('staff:task_detail', pk=pk)
        task = form.save(commit=False)
        task.status = Task.Status.REVIEW
        notify_user((task.reviewer or task.created_by).user, '🟡 Vazifa tekshiruvda', task.title, f'/staff/tasks/{task.pk}/')
    elif action == 'approve' and (p.pk in {task.reviewer_id, task.created_by_id} or p.role == StaffProfile.Role.SUPER_ADMIN):
        task.status = Task.Status.DONE
        task.completed_at = timezone.now()
        notify_user(task.assignee.user, '✅ Vazifa tasdiqlandi', task.title, f'/staff/tasks/{task.pk}/')
    elif action == 'return' and (p.pk in {task.reviewer_id, task.created_by_id} or p.role == StaffProfile.Role.SUPER_ADMIN):
        task.status = Task.Status.IN_PROGRESS
        task.review_comment = comment
        notify_user(task.assignee.user, '↩️ Vazifa qayta ishlashga yuborildi', f'{task.title}\n{comment}', f'/staff/tasks/{task.pk}/')
    else:
        return HttpResponseForbidden('Bu amal uchun ruxsat yo‘q.')
    task.save()
    TaskEvent.objects.create(task=task, actor=p, from_status=old, to_status=task.status, comment=comment)
    messages.success(request, "Vazifa holati yangilandi.")
    return redirect('staff:task_detail', pk=pk)


@staff_required
def report_create(request):
    p = request.staff_profile
    report = DailyReport.objects.filter(employee=p, date=timezone.localdate()).first()
    form = DailyReportForm(request.POST or None, instance=report)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.employee = p
        item.date = timezone.localdate()
        item.save()
        if p.manager:
            notify_user(p.manager.user, '✅ Yangi kunlik hisobot',
                        f'{p.user.display_name} bugungi hisobotini yubordi.', '/staff/reports/')
        messages.success(request, 'Kunlik hisobotingiz saqlandi.')
        return redirect('staff:dashboard')
    return render(request, 'staff/form.html', {'form': form, 'title': 'Kunlik hisobot', 'button': 'Hisobotni saqlash'})


@staff_required
def leave_list(request):
    p = request.staff_profile
    qs = LeaveRequest.objects.select_related('employee__user', 'decided_by__user')
    if not p.can_manage:
        qs = qs.filter(employee=p)
    elif p.role != StaffProfile.Role.SUPER_ADMIN:
        qs = qs.filter(Q(employee=p) | Q(employee__manager=p) | Q(employee__department=p.department)).distinct()
    return render(request, 'staff/leave_list.html', {'leaves': qs, 'form': LeaveRequestForm()})


@staff_required
@require_POST
def leave_create(request):
    form = LeaveRequestForm(request.POST)
    if form.is_valid():
        leave = form.save(commit=False); leave.employee = request.staff_profile; leave.save()
        recipients = StaffProfile.objects.filter(role=StaffProfile.Role.SUPER_ADMIN, is_approved=True)
        if request.staff_profile.manager:
            recipients = StaffProfile.objects.filter(pk=request.staff_profile.manager_id)
        notify_profiles(recipients, '🏖 Yangi ruxsat so‘rovi', request.staff_profile.user.display_name, '/staff/leaves/')
        messages.success(request, "So'rovingiz yuborildi.")
    else:
        messages.error(request, "So'rov ma'lumotlarini tekshiring.")
    return redirect('staff:leave_list')


@staff_required
@require_POST
def leave_decide(request, pk, decision):
    p = request.staff_profile
    if not p.can_manage or decision not in {'approve', 'reject'}:
        return HttpResponseForbidden()
    leave = get_object_or_404(LeaveRequest.objects.select_related('employee__user'), pk=pk)
    if p.role != StaffProfile.Role.SUPER_ADMIN and leave.employee.manager_id != p.pk and leave.employee.department_id != p.department_id:
        return HttpResponseForbidden()
    leave.status = LeaveRequest.Status.APPROVED if decision == 'approve' else LeaveRequest.Status.REJECTED
    leave.manager_comment = request.POST.get('comment', '')
    leave.decided_by = p; leave.save()
    notify_user(leave.employee.user, "🏖 So'rov natijasi", leave.get_status_display(), '/staff/leaves/')
    return redirect('staff:leave_list')


@staff_required
def announcements(request):
    p = request.staff_profile
    qs = Announcement.objects.filter(Q(branch__isnull=True) | Q(branch=p.branch), Q(department__isnull=True) | Q(department=p.department))
    form = AnnouncementForm(request.POST or None) if p.can_manage else None
    if request.method == 'POST' and form and form.is_valid():
        item = form.save(commit=False); item.author = p; item.save()
        recipients = StaffProfile.objects.filter(is_approved=True)
        if item.branch_id:
            recipients = recipients.filter(branch=item.branch)
        if item.department_id:
            recipients = recipients.filter(department=item.department)
        sent = notify_profiles(recipients.exclude(pk=p.pk), '📢 ' + item.title, item.body[:500], '/staff/announcements/')
        group_sent = False
        if not item.branch_id and not item.department_id:
            group_sent = notify_group('📢 ' + item.title, item.body[:1000])
        group_text = ' AbChat guruhiga ham yuborildi.' if group_sent else ''
        messages.success(request, f"E'lon joylandi. Staff bot orqali {sent} xodimga yuborildi.{group_text}")
        return redirect('staff:announcements')
    return render(request, 'staff/announcements.html', {'announcements': qs, 'form': form})


@staff_required
@require_POST
def announcement_ack(request, pk):
    item = get_object_or_404(Announcement, pk=pk)
    item.read_by.add(request.staff_profile)
    return redirect('staff:announcements')


@staff_required
def suggestion_create(request):
    form = SuggestionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False); item.author = request.staff_profile; item.save()
        messages.success(request, 'Murojaatingiz qabul qilindi.')
        return redirect('staff:dashboard')
    return render(request, 'staff/form.html', {'form': form, 'title': 'Taklif yoki muammo', 'button': 'Yuborish'})
