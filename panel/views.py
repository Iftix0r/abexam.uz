import csv
import json
import logging
import re
from datetime import timedelta
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction as db_transaction
from django.conf import settings
from django.db.models import Avg, Count, F, Max, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import SiteSettings, Notification, PromoCode
from core.utils import (
    daily_series, html_paragraphs_to_text, monthly_series, parse_json_body,
    text_to_html_paragraphs, validate_audio_upload, validate_image_upload,
)
from exams.models import ATTEMPT_ONLINE_WINDOW, Exam, ExamAttempt, Question, Section, UserResult
from exams import camera
from exams.passwords import GRACE_SECONDS, exam_password, seconds_until_rotation, testlar_password
from exams.testlar import testlar_folders
from exams.views import finalize_attempt
from learn.content import LEVEL_INFO, LEVELS, get_course, get_stories, validate_course
from learn.models import ApiToken, AppRelease, DailyXP, LearnerProfile, LessonDraft, LessonProgress, Mistake
from payments.models import Transaction
from users.models import LoginLog, User, Vocabulary

logger = logging.getLogger(__name__)


def is_staff(user):
    return user.is_authenticated and user.is_staff


def panel_required(view_func):
    return login_required(user_passes_test(is_staff, login_url='/login/')(view_func))


# ── Dashboard ──────────────────────────────────────────────────────────────────
@panel_required
def dashboard(request):
    now = timezone.now()
    month_ago = now - timedelta(days=30)

    # last 7 days chart data
    days_labels, days_users = daily_series(User.objects.all(), 'date_joined', 7, Count('id'))
    _, days_results = daily_series(UserResult.objects.all(), 'completed_at', 7, Count('id'))

    stats = {
        'total_users': User.objects.count(),
        'new_users': User.objects.filter(date_joined__gte=month_ago).count(),
        'total_exams': Exam.objects.filter(is_active=True).count(),
        'total_results': UserResult.objects.count(),
        'total_revenue': Transaction.objects.filter(status='success').aggregate(t=Sum('amount'))['t'] or 0,
        'month_revenue': Transaction.objects.filter(status='success', created_at__gte=month_ago).aggregate(t=Sum('amount'))['t'] or 0,
        'pending_tx': Transaction.objects.filter(status='pending').count(),
        'avg_score': UserResult.objects.graded().aggregate(a=Avg('score'))['a'] or 0,
    }
    recent_results = UserResult.objects.select_related('user', 'exam').order_by('-completed_at')[:8]
    recent_users = User.objects.order_by('-date_joined')[:6]
    recent_tx = Transaction.objects.select_related('user').order_by('-created_at')[:6]

    return render(request, 'panel/dashboard.html', {
        'stats': stats,
        'recent_results': recent_results,
        'recent_users': recent_users,
        'recent_tx': recent_tx,
        'chart_labels': json.dumps(days_labels),
        'chart_users': json.dumps(days_users),
        'chart_results': json.dumps(days_results),
    })


# ── Search ─────────────────────────────────────────────────────────────────────
@panel_required
def search(request):
    q = request.GET.get('q', '').strip()
    results = {'users': [], 'exams': []}
    if q:
        results['users'] = list(User.objects.filter(username__icontains=q).values('id', 'username', 'email')[:6])
        results['exams'] = list(Exam.objects.filter(title__icontains=q).values('id', 'title', 'exam_type')[:6])
    return JsonResponse(results)


# ── Users ──────────────────────────────────────────────────────────────────────
@panel_required
def users_list(request):
    q = request.GET.get('q', '')
    filter_by = request.GET.get('filter', '')
    users = User.objects.order_by('-date_joined')
    if q:
        users = users.filter(username__icontains=q) | users.filter(email__icontains=q)
    if filter_by == 'staff':
        users = users.filter(is_staff=True)
    elif filter_by == 'inactive':
        users = users.filter(is_active=False)
    elif filter_by == 'student':
        users = users.filter(is_active_student=True)
    return render(request, 'panel/users_list.html', {'users': users, 'q': q, 'filter': filter_by})


@panel_required
def user_detail(request, pk):
    user = get_object_or_404(User, pk=pk)
    results = UserResult.objects.filter(user=user).select_related('exam').order_by('-completed_at')
    transactions = Transaction.objects.filter(user=user).order_by('-created_at')[:10]
    stats = results.graded().aggregate(avg=Avg('score'), total=Count('id'))
    learn_done = LessonProgress.objects.filter(user=user).exclude(lesson_slug__startswith='story:')
    return render(request, 'panel/user_detail.html', {
        'obj': user, 'results': results, 'transactions': transactions, 'stats': stats,
        'learner': LearnerProfile.objects.filter(user=user).first(),
        'learn_stats': learn_done.aggregate(done=Count('id'), avg=Avg('best_score')),
        'learn_words': Vocabulary.objects.filter(user=user).count(),
        'app_tokens': ApiToken.objects.filter(user=user).order_by(F('last_used_at').desc(nulls_last=True)),
    })


@panel_required
def user_login_logs(request, pk):
    user = get_object_or_404(User, pk=pk)
    logs = LoginLog.objects.filter(user=user).order_by('-created_at')[:50]
    return render(request, 'panel/login_logs.html', {'obj': user, 'logs': logs})


@panel_required
def security_logs(request):
    # shubhali: failed yoki blocked
    logs = LoginLog.objects.filter(status__in=['failed', 'blocked']).order_by('-created_at')[:200]
    # IP lar bo'yicha guruhlab
    from django.db.models import Count as DCount
    top_ips = (LoginLog.objects.filter(status__in=['failed', 'blocked'])
               .values('ip').annotate(cnt=DCount('id')).order_by('-cnt')[:10])
    return render(request, 'panel/security_logs.html', {'logs': logs, 'top_ips': top_ips})


@panel_required
@require_POST
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    return JsonResponse({'active': user.is_active})


@panel_required
@require_POST
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        return JsonResponse({'ok': False, 'error': 'O\'zingizni o\'chira olmaysiz'})
    if user.is_superuser and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'error': 'Faqat superadmin superadminni o\'chira oladi'}, status=403)
    user.delete()
    return JsonResponse({'ok': True})


@panel_required
@require_POST
def user_add_balance(request, pk):
    user = get_object_or_404(User, pk=pk)
    data, err = parse_json_body(request, error_message="Noto'g'ri JSON", ok_field=True)
    if err:
        return err
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Noto\'g\'ri summa'}, status=400)
    note = data.get('note', "Admin tomonidan qo'shildi")
    if amount > 0:
        User.objects.filter(pk=user.pk).update(balance=F('balance') + amount)
        Transaction.objects.create(user=user, amount=amount, method='manual', status='success', description=note)
    elif amount < 0:
        User.objects.filter(pk=user.pk).update(balance=F('balance') + amount)
        User.objects.filter(pk=user.pk, balance__lt=0).update(balance=0)
    user.refresh_from_db(fields=['balance'])
    return JsonResponse({'balance': float(user.balance)})


@panel_required
@require_POST
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    data, err = parse_json_body(request, error_message="Noto'g'ri JSON", ok_field=True)
    if err:
        return err
    new_password = data.get('password', '').strip()
    if len(new_password) < 6:
        return JsonResponse({'ok': False, 'error': 'Parol kamida 6 ta belgi bo\'lishi kerak'})
    user.set_password(new_password)
    user.save()
    return JsonResponse({'ok': True})


@panel_required
@require_POST
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    data, err = parse_json_body(request, error_message="Noto'g'ri JSON", ok_field=True)
    if err:
        return err
    user.first_name = data.get('first_name', user.first_name)
    user.last_name = data.get('last_name', user.last_name)
    user.email = data.get('email', user.email)
    user.phone_number = data.get('phone_number', user.phone_number) or None
    user.is_active_student = data.get('is_active_student', user.is_active_student)
    user.save()
    return JsonResponse({'ok': True})


@panel_required
@require_POST
def user_make_staff(request, pk):
    if not request.user.is_superuser:
        return JsonResponse({'ok': False, 'error': 'Faqat superadmin xodim huquqini bera oladi'}, status=403)
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        return JsonResponse({'ok': False, 'error': 'O\'zingizni o\'zgartira olmaysiz'})
    user.is_staff = not user.is_staff
    user.save(update_fields=['is_staff'])
    return JsonResponse({'ok': True, 'is_staff': user.is_staff})


@panel_required
@require_POST
def users_bulk_action(request):
    data, err = parse_json_body(request, error_message="Noto'g'ri JSON", ok_field=True)
    if err:
        return err
    action = data.get('action')
    ids = data.get('ids', [])
    if not ids:
        return JsonResponse({'ok': False})
    users = User.objects.filter(pk__in=ids).exclude(pk=request.user.pk)
    if action == 'block':
        users.update(is_active=False)
    elif action == 'unblock':
        users.update(is_active=True)
    elif action == 'delete':
        users.filter(is_superuser=False).delete()
    return JsonResponse({'ok': True, 'count': len(ids)})


@panel_required
def users_export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="users.csv"'
    w = csv.writer(response)
    w.writerow(['ID', 'Username', 'Email', 'Telefon', 'Balans', 'Faol', 'Qo\'shilgan'])
    for u in User.objects.only('pk', 'username', 'email', 'phone_number', 'balance', 'is_active', 'date_joined').order_by('-date_joined'):
        w.writerow([u.pk, u.username, u.email, u.phone_number or '', u.balance, u.is_active, u.date_joined.strftime('%Y-%m-%d')])
    return response


# ── Exams ──────────────────────────────────────────────────────────────────────
@panel_required
def exams_list(request):
    q = request.GET.get('q', '')
    etype = request.GET.get('type', '')
    show = request.GET.get('show', '')
    all_exams = Exam.objects.annotate(
        sections_count=Count('sections', distinct=True),
        questions_count=Count('sections__questions', distinct=True),
        results_count=Count('userresult', distinct=True),
    ).order_by('-created_at')
    stats = {
        'total': all_exams.count(),
        'active': all_exams.filter(is_active=True).count(),
        'draft': all_exams.filter(is_active=False).count(),
        'results': UserResult.objects.count(),
    }
    exams = all_exams
    if q:
        exams = exams.filter(title__icontains=q)
    if etype:
        exams = exams.filter(exam_type=etype)
    if show == 'pending_review':
        exams = exams.filter(is_ai_generated=True, is_reviewed=False)
    elif show == 'active':
        exams = exams.filter(is_active=True)
    elif show == 'draft':
        exams = exams.filter(is_active=False)
    pending_review_count = Exam.objects.filter(is_ai_generated=True, is_reviewed=False).count()
    return render(request, 'panel/exams_list.html', {
        'exams': exams, 'q': q, 'etype': etype,
        'exam_types': Exam.EXAM_TYPES,
        'pending_review_count': pending_review_count,
        'show': show, 'stats': stats,
    })


@panel_required
def exam_detail(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    sections = list(exam.sections.prefetch_related('questions').all())
    # Numbers questions continuously per skill (Listening 1..N, Reading
    # 1..N, ...) instead of Question.order's raw exam-wide value — the
    # latter made e.g. Reading passage 3 display as "34-40", which looked
    # like Reading had 40 questions instead of the 20 it actually has.
    for _stype, group_iter in groupby(sections, key=lambda s: s.section_type):
        counter = 0
        for section in group_iter:
            for q in section.questions.all():
                counter += 1
                q.display_number = counter
    results = UserResult.objects.filter(exam=exam).select_related('user').order_by('-completed_at')[:20]
    stats = UserResult.objects.graded().filter(exam=exam).aggregate(avg=Avg('score'), total=Count('id'))
    return render(request, 'panel/exam_detail.html', {
        'exam': exam, 'sections': sections, 'results': results, 'stats': stats,
        'exam_password': exam_password(exam.pk), 'password_rotates_in': seconds_until_rotation(),
        'password_required': SiteSettings.get().exam_password_required,
    })


@panel_required
def exam_passwords(request):
    """Current hourly password of every active exam, for the invigilator to
    read out to the students in the room (see exams/passwords.py)."""
    exams = list(Exam.objects.filter(is_active=True).order_by('-created_at'))
    for exam in exams:
        exam.current_password = exam_password(exam.pk)
    testlar = [{'number': n, 'password': testlar_password(n)} for n in testlar_folders()]
    return render(request, 'panel/exam_passwords.html', {
        'exams': exams,
        'testlar': testlar,
        'rotates_in': seconds_until_rotation(),
        'grace_minutes': GRACE_SECONDS // 60,
        'password_required': SiteSettings.get().exam_password_required,
    })


@panel_required
def exam_create(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        exam_type = request.POST.get('exam_type', 'mock')
        price = request.POST.get('price', 0)
        duration = request.POST.get('duration_minutes', 60)
        description = request.POST.get('description', '')
        if title:
            exam = Exam.objects.create(
                title=title, exam_type=exam_type, price=price,
                duration_minutes=duration, description=description,
                # A brand-new exam has no sections/questions yet, so it can
                # never legitimately start active — same rule exam_edit and
                # exam_toggle_active enforce once content exists.
                is_active=False,
            )
            return redirect('panel:exam_detail', pk=exam.pk)
    return render(request, 'panel/exam_form.html', {'exam_types': Exam.EXAM_TYPES, 'exam': None})


def _exam_has_content(exam):
    """True if the exam has at least one section with at least one
    question — the minimum needed for a student to actually take it."""
    return Question.objects.filter(section__exam=exam).exists()


@panel_required
def exam_edit(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == 'POST':
        exam.title = request.POST.get('title', exam.title).strip()
        exam.exam_type = request.POST.get('exam_type', exam.exam_type)
        exam.price = request.POST.get('price', exam.price)
        exam.duration_minutes = request.POST.get('duration_minutes', exam.duration_minutes)
        exam.description = request.POST.get('description', exam.description)
        want_active = request.POST.get('is_active') == 'on'
        if want_active and not exam.is_active and not _exam_has_content(exam):
            messages.error(request, "Imtihonda hali birorta savol yo'q — avval bo'lim va savol qo'shing, keyin faollashtiring.")
        else:
            exam.is_active = want_active
        exam.save()
        return redirect('panel:exam_detail', pk=exam.pk)
    return render(request, 'panel/exam_form.html', {'exam_types': Exam.EXAM_TYPES, 'exam': exam})


@panel_required
@require_POST
def exam_delete(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    exam.delete()
    return JsonResponse({'ok': True})


@panel_required
@require_POST
def exam_toggle_active(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if not exam.is_active and not _exam_has_content(exam):
        return JsonResponse({
            'active': False,
            'error': "Imtihonda hali birorta savol yo'q — avval bo'lim va savol qo'shing.",
        }, status=400)
    exam.is_active = not exam.is_active
    exam.save(update_fields=['is_active'])
    return JsonResponse({'active': exam.is_active})


@panel_required
@require_POST
def exams_bulk_action(request):
    data, err = parse_json_body(request, error_message="Noto'g'ri JSON", ok_field=True)
    if err:
        return err
    action = data.get('action')
    ids = data.get('ids', [])
    if not ids:
        return JsonResponse({'ok': False})
    exams = Exam.objects.filter(pk__in=ids)
    if action == 'activate':
        exam_objs = list(exams)
        activate_ids = [e.pk for e in exam_objs if _exam_has_content(e)]
        Exam.objects.filter(pk__in=activate_ids).update(is_active=True)
        return JsonResponse({'ok': True, 'count': len(activate_ids), 'skipped': len(exam_objs) - len(activate_ids)})
    elif action == 'deactivate':
        exams.update(is_active=False)
    elif action == 'delete':
        exams.delete()
    return JsonResponse({'ok': True, 'count': len(ids)})


@panel_required
@require_POST
def exam_review(request, pk):
    """Approve or reject an AI-generated exam after human review."""
    exam = get_object_or_404(Exam, pk=pk, is_ai_generated=True)
    action = request.POST.get('action')
    if action == 'approve':
        exam.is_reviewed = True
        if _exam_has_content(exam):
            exam.is_active = True
            exam.save(update_fields=['is_reviewed', 'is_active'])
            messages.success(request, f'"{exam.title}" tasdiqlandi va faollashtirildi.')
        else:
            exam.save(update_fields=['is_reviewed'])
            messages.error(request, f'"{exam.title}" tasdiqlandi, lekin savollar yo\'q — faollashtirish uchun avval savol qo\'shing.')
    elif action == 'reject':
        title = exam.title
        exam.delete()
        messages.warning(request, f'"{title}" o\'chirildi.')
    return redirect('panel:exams')


# ── Manual exam builder: sections ───────────────────────────────────────────
_AUDIO_TYPES = {'audio/webm', 'audio/mp4', 'audio/mpeg', 'audio/ogg', 'audio/wav'}
_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


def _save_section_from_post(request, exam, section=None):
    """Validate + save Section fields from request.POST/FILES.
    Returns an Uzbek error message on failure, or None on success."""
    title = request.POST.get('title', '').strip()
    section_type = request.POST.get('section_type', '')
    content_raw = request.POST.get('content', '')

    if not title:
        return "Bo'lim nomini kiriting"
    if section_type not in dict(Section.SECTION_TYPES):
        return "Bo'lim turini tanlang"
    try:
        duration_minutes = int(request.POST.get('duration_minutes') or 0)
    except ValueError:
        return "Davomiylik butun son bo'lishi kerak"

    audio_file = request.FILES.get('audio_file')
    if audio_file:
        error = validate_audio_upload(audio_file, 40, _AUDIO_TYPES)
        if error:
            return error

    image = request.FILES.get('image')
    if image:
        error = validate_image_upload(image, 5, _IMAGE_TYPES)
        if error:
            return error

    if section is None:
        section = Section(exam=exam)
        section.order = (exam.sections.aggregate(Max('order'))['order__max'] or 0) + 1

    section.title = title
    section.section_type = section_type
    section.content = text_to_html_paragraphs(content_raw)
    section.duration_minutes = duration_minutes
    if audio_file:
        section.audio_file = audio_file
    if image:
        section.image = image
    section.save()
    return None


def _section_initial(section):
    """Plain-dict field defaults for section_form.html — always a real
    dict (never None), same rationale as _question_initial."""
    if section is None:
        return {'title': '', 'section_type': '', 'duration_minutes': 0}
    return {'title': section.title, 'section_type': section.section_type, 'duration_minutes': section.duration_minutes}


@panel_required
def section_create(request, exam_pk):
    exam = get_object_or_404(Exam, pk=exam_pk)
    error = None
    if request.method == 'POST':
        error = _save_section_from_post(request, exam)
        if not error:
            return redirect('panel:exam_detail', pk=exam.pk)
    return render(request, 'panel/section_form.html', {
        'exam': exam, 'section': None, 'section_types': Section.SECTION_TYPES, 'error': error,
        'initial_content': '', 'initial': _section_initial(None),
    })


@panel_required
def section_edit(request, pk):
    section = get_object_or_404(Section, pk=pk)
    exam = section.exam
    error = None
    if request.method == 'POST':
        error = _save_section_from_post(request, exam, section)
        if not error:
            return redirect('panel:exam_detail', pk=exam.pk)
    return render(request, 'panel/section_form.html', {
        'exam': exam, 'section': section, 'section_types': Section.SECTION_TYPES, 'error': error,
        'initial_content': html_paragraphs_to_text(section.content), 'initial': _section_initial(section),
    })


@panel_required
@require_POST
def section_delete(request, pk):
    section = get_object_or_404(Section, pk=pk)
    section.delete()
    return JsonResponse({'ok': True})


@panel_required
@require_POST
def section_move(request, pk):
    section = get_object_or_404(Section, pk=pk)
    data, err = parse_json_body(request, ok_field=True)
    if err:
        return err
    siblings = list(Section.objects.filter(exam=section.exam).order_by('order', 'pk'))
    idx = next((i for i, s in enumerate(siblings) if s.pk == section.pk), None)
    swap_idx = idx - 1 if data.get('direction') == 'up' else idx + 1
    if idx is None or swap_idx < 0 or swap_idx >= len(siblings):
        return JsonResponse({'ok': True})
    other = siblings[swap_idx]
    section.order, other.order = other.order, section.order
    Section.objects.bulk_update([section, other], ['order'])
    return JsonResponse({'ok': True})


@panel_required
@require_POST
def section_duplicate(request, pk):
    """Deep-copy a section (title, content, audio/image files) and all its
    questions — a faster starting point than re-typing a similar passage."""
    from django.core.files.base import ContentFile
    section = get_object_or_404(Section, pk=pk)
    new_section = Section(
        exam=section.exam,
        title=f"{section.title} (nusxa)",
        section_type=section.section_type,
        content=section.content,
        extra_data=section.extra_data,
        duration_minutes=section.duration_minutes,
        order=(section.exam.sections.aggregate(Max('order'))['order__max'] or 0) + 1,
    )
    # Copy the actual file content into a new file rather than pointing at
    # the same one — deleting either section later must not take the
    # other's file with it (Section's post_delete signal removes the file).
    if section.audio_file:
        new_section.audio_file.save(
            section.audio_file.name.rsplit('/', 1)[-1], ContentFile(section.audio_file.read()), save=False)
    if section.image:
        new_section.image.save(
            section.image.name.rsplit('/', 1)[-1], ContentFile(section.image.read()), save=False)
    new_section.save()

    for q in section.questions.all():
        Question.objects.create(
            section=new_section, text=q.text, question_type=q.question_type,
            options=q.options, correct_answer=q.correct_answer, explanation=q.explanation,
            model_answer=q.model_answer, order=q.order, word_limit=q.word_limit,
        )
    return redirect('panel:exam_detail', pk=section.exam.pk)


@panel_required
def results_export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="results.csv"'
    w = csv.writer(response)
    w.writerow(['ID', 'Foydalanuvchi', 'Imtihon', 'Holat', 'Ball', 'Listening', 'Reading', 'Writing', 'Speaking', 'Sana'])
    for r in UserResult.objects.select_related('user', 'exam').order_by('-completed_at'):
        w.writerow([r.pk, r.user.username, r.exam.title, r.get_status_display(), r.score, r.listening_score, r.reading_score, r.writing_score, r.speaking_score, r.completed_at.strftime('%Y-%m-%d %H:%M')])
    return response


# ── Transactions ───────────────────────────────────────────────────────────────
@panel_required
def transactions_list(request):
    status = request.GET.get('status', '')
    txs = Transaction.objects.select_related('user').order_by('-created_at')
    if status:
        txs = txs.filter(status=status)
    total = txs.filter(status='success').aggregate(t=Sum('amount'))['t'] or 0
    return render(request, 'panel/transactions_list.html', {'txs': txs, 'status': status, 'total': total})


@panel_required
@require_POST
def transaction_approve(request, pk):
    with db_transaction.atomic():
        tx = get_object_or_404(Transaction.objects.select_for_update(), pk=pk)
        if tx.status == 'pending':
            tx.status = 'success'
            tx.save(update_fields=['status'])
            User.objects.filter(pk=tx.user_id).update(balance=F('balance') + tx.amount)
    return JsonResponse({'status': tx.status})


@panel_required
@require_POST
def transaction_reject(request, pk):
    tx = get_object_or_404(Transaction, pk=pk)
    if tx.status == 'pending':
        tx.status = 'failed'
        tx.save(update_fields=['status'])
    return JsonResponse({'status': tx.status})


# ── Analytics ──────────────────────────────────────────────────────────────────
@panel_required
def analytics(request):
    import json
    from django.db.models import Avg, Count, Sum
    from datetime import timedelta

    now = timezone.now()

    # Last 30 days — daily new users
    days_labels, days_users = daily_series(User.objects.all(), 'date_joined', 30, Count('id'))
    _, days_results = daily_series(UserResult.objects.all(), 'completed_at', 30, Count('id'))
    _, days_revenue_raw = daily_series(
        Transaction.objects.filter(status='success'), 'created_at', 30, Sum('amount')
    )
    days_revenue = [float(v) for v in days_revenue_raw]

    # Exam type distribution
    by_type = (UserResult.objects.values('exam__exam_type')
               .annotate(cnt=Count('id'), avg=Avg('score')).order_by('-cnt'))

    # Top users by results
    top_users = (UserResult.objects.values('user__username')
                 .annotate(cnt=Count('id'), avg=Avg('score'))
                 .order_by('-cnt')[:8])

    # Band distribution — aggregated in DB, no full table load
    from django.db.models import Case, When, Value, CharField
    bands = {'4.0-5.0': 0, '5.5-6.0': 0, '6.5-7.0': 0, '7.5-8.0': 0, '8.5-9.0': 0}
    band_qs = (
        UserResult.objects
        .annotate(band_group=Case(
            When(score__lte=5.0, then=Value('4.0-5.0')),
            When(score__lte=6.0, then=Value('5.5-6.0')),
            When(score__lte=7.0, then=Value('6.5-7.0')),
            When(score__lte=8.0, then=Value('7.5-8.0')),
            default=Value('8.5-9.0'),
            output_field=CharField(),
        ))
        .values('band_group').annotate(cnt=Count('id'))
    )
    for row in band_qs:
        bands[row['band_group']] = row['cnt']

    # Monthly revenue (6 months)
    monthly_labels, monthly_rev_raw = monthly_series(
        Transaction.objects.filter(status='success'), 'created_at', 6, Sum('amount')
    )
    monthly_rev = [float(v) for v in monthly_rev_raw]

    stats = {
        'total_users': User.objects.count(),
        'total_results': UserResult.objects.count(),
        'total_revenue': Transaction.objects.filter(status='success').aggregate(t=Sum('amount'))['t'] or 0,
        'avg_score': UserResult.objects.graded().aggregate(a=Avg('score'))['a'] or 0,
        'avg_l': UserResult.objects.graded().aggregate(a=Avg('listening_score'))['a'] or 0,
        'avg_r': UserResult.objects.graded().aggregate(a=Avg('reading_score'))['a'] or 0,
        'avg_w': UserResult.objects.graded().aggregate(a=Avg('writing_score'))['a'] or 0,
        'avg_s': UserResult.objects.graded().aggregate(a=Avg('speaking_score'))['a'] or 0,
        'active_exams': Exam.objects.filter(is_active=True).count(),
        'pending_tx': Transaction.objects.filter(status='pending').count(),
    }

    return render(request, 'panel/analytics.html', {
        'stats': stats,
        'chart_labels': json.dumps(days_labels),
        'chart_users': json.dumps(days_users),
        'chart_results': json.dumps(days_results),
        'chart_revenue': json.dumps(days_revenue),
        'by_type': list(by_type),
        'chart_type_labels': json.dumps([b['exam__exam_type'] for b in by_type]),
        'chart_type_counts': json.dumps([b['cnt'] for b in by_type]),
        'chart_type_avgs': json.dumps([round(b['avg'] or 0, 1) for b in by_type]),
        'top_users': list(top_users),
        'chart_band_labels': json.dumps(list(bands.keys())),
        'chart_band_data': json.dumps(list(bands.values())),
        'chart_monthly_labels': json.dumps(monthly_labels),
        'chart_monthly_rev': json.dumps(monthly_rev),
    })


from itertools import chain

# ── Results ────────────────────────────────────────────────────────────────────
@panel_required
def results_list(request):
    exam_id = request.GET.get('exam', '')
    status = request.GET.get('status', '')
    results = UserResult.objects.select_related('user', 'exam').order_by('-completed_at')
    if exam_id:
        results = results.filter(exam_id=exam_id)
    if status == UserResult.STATUS_PENDING:
        # Oldest first — whoever has been waiting longest gets graded first.
        results = results.pending().order_by('completed_at')
    exams = Exam.objects.all()
    return render(request, 'panel/results_list.html', {
        'results': results[:100], 'exams': exams, 'exam_id': exam_id, 'status': status,
        'pending_count': UserResult.objects.pending().count(),
    })


_WRITING_CRITERIA = (
    ('task_achievement', 'Task Achievement'),
    ('coherence_cohesion', 'Coherence & Cohesion'),
    ('lexical_resource', 'Lexical Resource'),
    ('grammatical_accuracy', 'Grammar'),
)
_SPEAKING_CRITERIA = (
    ('fluency_coherence', 'Fluency & Coherence'),
    ('lexical_resource', 'Lexical Resource'),
    ('grammatical_range', 'Grammar'),
    ('pronunciation', 'Pronunciation'),
)
_BAND_CHOICES = [x / 2 for x in range(2, 19)]  # 1.0 … 9.0


def _parse_band(raw, required):
    """'' → None (unless required); otherwise a 0.5-step band in 0…9."""
    raw = (raw or '').strip()
    if not raw:
        if required:
            raise ValueError
        return None
    val = float(raw)
    if not 0 <= val <= 9 or (val * 2) % 1:
        raise ValueError
    return val


def _safe_band(raw):
    try:
        return _parse_band(raw, False)
    except ValueError:
        return None


def _parse_scored_block(post, prefix, criteria, required):
    """One graded block (a writing task, or speaking): an overall band plus
    optional per-criterion bands and a comment. Returns None when the
    block was left empty and isn't required."""
    band = _parse_band(post.get(f'{prefix}_band'), required)
    if band is None:
        return None
    block = {'band': band, 'feedback': post.get(f'{prefix}_feedback', '').strip()}
    for key, _ in criteria:
        val = _parse_band(post.get(f'{prefix}_{key}'), False)
        if val is not None:
            block[key] = val
    return block


def _objective_stats(result):
    """Per-skill correct/total for the auto-checked (listening/reading)
    questions, plus a ✓/✗ strip so the grader sees the whole picture."""
    stats = {}
    answers = (result.answers.select_related('question__section')
               .exclude(question__isnull=True)
               .exclude(question__question_type__in=('writing_task', 'short_answer'))
               .order_by('question__section__order', 'question__order'))
    for ua in answers:
        stype = ua.question.section.section_type
        entry = stats.setdefault(stype, {'correct': 0, 'total': 0, 'marks': []})
        entry['total'] += 1
        entry['correct'] += ua.is_correct
        entry['marks'].append(ua.is_correct)
    band_field = {'listening': result.listening_score, 'reading': result.reading_score}
    return [
        {'type': t, 'label': t.capitalize(), 'band': band_field.get(t, 0), **stats[t]}
        for t in ('listening', 'reading') if t in stats
    ]


@panel_required
def result_grade(request, pk):
    """Manual grading of Writing (hand-checked essays) and Speaking (held
    in person at the study center). Saving releases a pending result."""
    from exams.views import calc_writing_band, compute_overall_band, present_section_types

    result = get_object_or_404(UserResult.objects.select_related('user', 'exam'), pk=pk)
    writing_answers = list(
        result.answers.select_related('question__section')
        .filter(question__question_type='writing_task')
        .order_by('question__section__order', 'question__order')
    )
    prev_w = result.writing_feedback or {}
    prev_tasks = (prev_w.get('tasks') or []) if prev_w.get('manual') else []
    prev_s = result.speaking_feedback if isinstance(result.speaking_feedback, dict) else {}

    tasks = []
    for i, ua in enumerate(writing_answers, start=1):
        prev = prev_tasks[i - 1] if i - 1 < len(prev_tasks) else {}
        tasks.append({
            'num': i,
            'prefix': f'task{i}',
            'answer': ua,
            'question': ua.question,
            'word_count': len(ua.user_answer.split()),
            'band': prev.get('band'),
            'criteria': [(key, label, prev.get(key)) for key, label in _WRITING_CRITERIA],
            'feedback': prev.get('feedback', ''),
        })
    speaking = {
        'band': prev_s.get('band'),
        'criteria': [(key, label, prev_s.get(key)) for key, label in _SPEAKING_CRITERIA],
        'feedback': prev_s.get('feedback', ''),
    }

    error = ''
    if request.method == 'POST':
        try:
            task_feedbacks = []
            for t in tasks:
                block = _parse_scored_block(request.POST, t['prefix'], _WRITING_CRITERIA, required=True)
                block.update(task_num=t['num'], section_title=t['question'].section.title)
                task_feedbacks.append(block)
            speaking_block = _parse_scored_block(request.POST, 'speaking', _SPEAKING_CRITERIA, required=False)
        except ValueError:
            error = "Har bir Writing task uchun ball tanlang (1.0 – 9.0)."
            # Keep what the grader already picked instead of wiping the form.
            for t in tasks:
                t['band'] = _safe_band(request.POST.get(f"{t['prefix']}_band"))
                t['criteria'] = [(k, l, _safe_band(request.POST.get(f"{t['prefix']}_{k}"))) for k, l in _WRITING_CRITERIA]
                t['feedback'] = request.POST.get(f"{t['prefix']}_feedback", '')
            speaking['band'] = _safe_band(request.POST.get('speaking_band'))
            speaking['criteria'] = [(k, l, _safe_band(request.POST.get(f'speaking_{k}'))) for k, l in _SPEAKING_CRITERIA]
            speaking['feedback'] = request.POST.get('speaking_feedback', '')
        else:
            fields = ['score', 'status', 'graded_by', 'graded_at']
            if task_feedbacks:
                w_band = calc_writing_band([fb['band'] for fb in task_feedbacks])
                result.writing_feedback = {'manual': True, 'band': w_band, 'tasks': task_feedbacks,
                                           'graded_by': request.user.username}
                result.writing_score = w_band
                fields += ['writing_feedback', 'writing_score']
            if speaking_block:
                result.speaking_feedback = {'manual': True, **speaking_block, 'graded_by': request.user.username}
                result.speaking_score = speaking_block['band']
                fields += ['speaking_feedback', 'speaking_score']
            elif prev_s.get('manual'):
                # Grader cleared a previously entered speaking band.
                result.speaking_feedback = None
                result.speaking_score = 0.0
                fields += ['speaking_feedback', 'speaking_score']

            present = present_section_types(result.exam)
            if result.speaking_score:
                # Speaking held in person counts toward the overall band
                # even though the exam itself has no online speaking part.
                present.add('speaking')
            result.score = compute_overall_band({
                'listening': result.listening_score, 'reading': result.reading_score,
                'writing': result.writing_score, 'speaking': result.speaking_score,
            }, present)
            was_pending = result.is_pending
            result.status = UserResult.STATUS_GRADED
            result.graded_by = request.user
            result.graded_at = timezone.now()
            result.save(update_fields=fields)
            if was_pending:
                Notification.objects.create(
                    user=result.user,
                    title="Natijangiz tayyor",
                    message=f"«{result.exam.title}» imtihoni natijasi chiqdi: umumiy ball {result.score:.1f}.",
                    type='success',
                )
            messages.success(request, f"Saqlandi. Umumiy ball: {result.score:.1f}")
            nxt = UserResult.objects.pending().order_by('completed_at').first()
            if request.POST.get('next') == '1' and nxt:
                return redirect('panel:result_grade', pk=nxt.pk)
            return redirect(f"{reverse('panel:results')}?status=pending")

    return render(request, 'panel/result_grade.html', {
        'result': result, 'tasks': tasks, 'speaking': speaking,
        'objective': _objective_stats(result), 'band_choices': _BAND_CHOICES, 'error': error,
        # For the live overall-band preview on the page.
        'present_types': sorted(present_section_types(result.exam)),
        'fixed_bands': {'listening': result.listening_score, 'reading': result.reading_score},
        'pending_count': UserResult.objects.pending().exclude(pk=result.pk).count(),
    })


@panel_required
@require_POST
def result_delete(request, pk):
    result = get_object_or_404(UserResult, pk=pk)
    result.delete()
    return JsonResponse({'ok': True})


@panel_required
@require_POST
def results_bulk_delete(request):
    data, err = parse_json_body(request)
    if err:
        return err
    ids = data.get('ids', [])
    qs = UserResult.objects.filter(pk__in=ids)
    deleted = qs.count()
    qs.delete()
    return JsonResponse({'ok': True, 'deleted': deleted})


# ── Live exam monitoring ───────────────────────────────────────────────────────
_SECTION_LABELS = {
    'listening': 'Listening', 'reading': 'Reading', 'writing': 'Writing',
    'speaking': 'Speaking', 'finished': 'Yakunlash bosildi',
}


def _ago(now, moment):
    secs = max(0, int((now - moment).total_seconds()))
    if secs < 60:
        return f'{secs} soniya oldin'
    if secs < 3600:
        return f'{secs // 60} daqiqa oldin'
    if secs < 86400:
        return f'{secs // 3600} soat oldin'
    return f'{secs // 86400} kun oldin'


def _attempt_filters(now):
    online_since = now - ATTEMPT_ONLINE_WINDOW
    return {
        'active': Q(submitted_at__isnull=True, last_seen_at__gte=online_since),
        'unsent': Q(submitted_at__isnull=True, last_seen_at__lt=online_since, answered_count__gt=0),
    }


def _clock(seconds):
    return f'{seconds // 60}:{seconds % 60:02d}'


def _words(text):
    return len(str(text).split())


@panel_required
def attempts_live(request):
    now = timezone.now()
    online_since = now - ATTEMPT_ONLINE_WINDOW
    tab = request.GET.get('tab', 'all')
    exam_id = request.GET.get('exam', '')
    filters = _attempt_filters(now)

    qs = ExamAttempt.objects.select_related('user', 'exam')
    if exam_id:
        qs = qs.filter(exam_id=exam_id)
    recent = qs.filter(last_seen_at__gte=now - timedelta(hours=24))
    counts = {name: qs.filter(q).count() for name, q in filters.items()}
    counts['started'] = recent.count()
    counts['submitted'] = recent.filter(submitted_at__isnull=False).count()
    if tab in filters:
        qs = qs.filter(filters[tab])
    else:
        tab = 'all'
        qs = recent
    attempts = list(qs[:200])

    exam_ids = {a.exam_id for a in attempts}
    questions = Question.objects.filter(section__exam__in=exam_ids)
    if not settings.SPEAKING_ENABLED:
        questions = questions.exclude(section__section_type='speaking')
    totals = dict(questions.values_list('section__exam').annotate(n=Count('id')))
    writing_ids = {}
    for exam_pk, qid in (questions.filter(question_type='writing_task')
                         .order_by('section__order', 'order').values_list('section__exam', 'id')):
        writing_ids.setdefault(exam_pk, []).append(str(qid))
    # The same account writing from two computers at once usually means
    # someone else is sitting the test for them.
    multi_device = set(
        ExamAttempt.objects.filter(submitted_at__isnull=True, last_seen_at__gte=online_since)
        .values('user').annotate(n=Count('id')).filter(n__gt=1).values_list('user', flat=True)
    )

    for a in attempts:
        a.total_questions = totals.get(a.exam_id, 0)
        a.section_label = _SECTION_LABELS.get(a.current_section, a.current_section or '—')
        a.seen_ago = _ago(now, a.last_seen_at)
        a.writing_words = [_words(a.answers.get(qid, '')) for qid in writing_ids.get(a.exam_id, [])]
        a.suspicious = a.leave_count >= 3 or a.pasted_chars >= 100
        a.multi_device = a.user_id in multi_device and not a.is_submitted
        a.time_left_label = ''
        if a.is_submitted:
            a.state = 'submitted'
        elif a.last_seen_at >= online_since:
            a.state = 'active'
            if a.time_left is not None:
                elapsed = int((now - a.last_seen_at).total_seconds())
                a.time_left_label = _clock(max(0, a.time_left - elapsed))
        elif a.answered_count:
            a.state = 'unsent'
        else:
            a.state = 'abandoned'

    return render(request, 'panel/attempts_live.html', {
        'attempts': attempts, 'tab': tab, 'counts': counts,
        'exam_id': exam_id, 'exams': Exam.objects.order_by('-created_at'),
    })


@panel_required
def attempt_detail(request, pk):
    attempt = get_object_or_404(ExamAttempt.objects.select_related('user', 'exam', 'result'), pk=pk)
    sections = list(attempt.exam.sections.prefetch_related('questions').order_by('order'))
    if not settings.SPEAKING_ENABLED:
        sections = [s for s in sections if s.section_type != 'speaking']
    rows = []
    for section in sections:
        items = []
        for number, q in enumerate(section.questions.all(), 1):
            answer = str(attempt.answers.get(str(q.id), '')).strip()
            items.append({
                'number': number, 'question': q, 'answer': answer,
                'is_writing': q.question_type == 'writing_task',
                'words': _words(answer) if q.question_type == 'writing_task' else None,
            })
        rows.append({'section': section, 'items': items,
                     'answered': sum(1 for i in items if i['answer'])})
    return render(request, 'panel/attempt_detail.html', {
        'attempt': attempt, 'rows': rows,
        'section_label': _SECTION_LABELS.get(attempt.current_section, attempt.current_section or '—'),
        'seen_ago': _ago(timezone.now(), attempt.last_seen_at),
    })


@panel_required
def attempt_camera(request, pk):
    """Latest webcam frame of an attempt (404 when the camera is off). With
    ?watch=1 the student's page switches to a frame every second."""
    attempt = get_object_or_404(ExamAttempt, pk=pk)
    if request.GET.get('watch') == '1' and not attempt.is_submitted:
        camera.mark_watched(attempt.user_id, attempt.exam_id, attempt.client_id)
    frame = camera.latest_frame(attempt.user_id, attempt.exam_id, attempt.client_id)
    if frame is None:
        return HttpResponse(status=404)
    resp = HttpResponse(frame[0], content_type='image/jpeg')
    resp['Cache-Control'] = 'no-store'
    resp['X-Frame-Age'] = str(int(frame[1]))
    return resp


@panel_required
def attempt_camera_live(request, pk):
    """Staff side of the live video call signalling. POST {action: 'start'}
    asks (and keeps asking) the student's page for a call and returns the
    session id; GET ?session= polls for the student's offer; POST {action:
    'answer', session, sdp} sends the answer back."""
    import uuid
    attempt = get_object_or_404(ExamAttempt, pk=pk)
    args = (attempt.user_id, attempt.exam_id, attempt.client_id)
    if request.method == 'GET':
        return JsonResponse({'offer': camera.get_sdp('offer', *args, request.GET.get('session', ''))})
    data, err = parse_json_body(request)
    if err:
        return err
    if attempt.is_submitted:
        return JsonResponse({'ok': False, 'error': 'Urinish yakunlangan'})
    if data.get('action') == 'start':
        # Each staff view keeps its own session (several can watch at once).
        session = re.sub(r'[^A-Za-z0-9_-]', '', str(data.get('session') or ''))[:64] or uuid.uuid4().hex
        camera.request_live(*args, session, str(data.get('quality') or 'high'))
        return JsonResponse({'ok': True, 'session': session})
    if data.get('action') == 'answer':
        sdp = data.get('sdp')
        session = str(data.get('session') or '')
        if (not isinstance(sdp, str) or len(sdp) > camera.MAX_SDP_CHARS
                or not camera.is_live_session(*args, session)):
            return JsonResponse({'ok': False, 'error': "Noto'g'ri so'rov"}, status=400)
        camera.put_sdp('answer', *args, session, sdp)
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False, 'error': "Noma'lum amal"}, status=400)


@panel_required
def attempt_camera_clip(request, pk):
    """Next relayed video clip of an attempt newer than ?after= (204 when
    there's none yet). Polling it keeps the student's page sending clips."""
    attempt = get_object_or_404(ExamAttempt, pk=pk)
    args = (attempt.user_id, attempt.exam_id, attempt.client_id)
    if not attempt.is_submitted:
        camera.request_relay(*args)
    try:
        after = int(request.GET.get('after') or 0)
    except ValueError:
        after = 0
    found = camera.next_clip(*args, after)
    if found is None:
        return HttpResponse(status=204)
    seq, clip = found
    resp = HttpResponse(clip['data'], content_type=clip['type'])
    resp['X-Clip-Seq'] = str(seq)
    resp['Cache-Control'] = 'no-store'
    return resp


@panel_required
@require_POST
def attempts_command(request):
    """Message or extra time for chosen attempts, or for everyone currently
    writing (optionally one exam). Delivered on the page's next autosave."""
    data, err = parse_json_body(request)
    if err:
        return err
    kind = data.get('type')
    if kind == 'message':
        text = str(data.get('text') or '').strip()[:500]
        if not text:
            return JsonResponse({'ok': False, 'error': "Xabar matni bo'sh"})
        command = {'type': 'message', 'text': text}
    elif kind == 'extra_time':
        try:
            minutes = int(data.get('minutes'))
        except (TypeError, ValueError):
            minutes = 0
        if not 1 <= minutes <= 60:
            return JsonResponse({'ok': False, 'error': "Daqiqa 1 dan 60 gacha bo'lishi kerak"})
        command = {'type': 'extra_time', 'seconds': minutes * 60}
    else:
        return JsonResponse({'ok': False, 'error': "Noma'lum buyruq"})

    attempts = ExamAttempt.objects.filter(submitted_at__isnull=True)
    if data.get('all_active'):
        attempts = attempts.filter(last_seen_at__gte=timezone.now() - ATTEMPT_ONLINE_WINDOW)
        if data.get('exam'):
            attempts = attempts.filter(exam_id=data['exam'])
    else:
        attempts = attempts.filter(pk__in=data.get('ids', []))
    sent = 0
    for attempt in attempts:
        attempt.add_command(**command)
        attempt.save(update_fields=['commands'])
        sent += 1
    return JsonResponse({'ok': True, 'sent': sent})


@panel_required
@require_POST
def attempts_finish_all(request):
    """Time's up: turn every unsent attempt of one exam with answers into a
    result. Pages still open see it on their next autosave and stop."""
    data, err = parse_json_body(request)
    if err:
        return err
    if not data.get('exam'):
        return JsonResponse({'ok': False, 'error': 'Avval imtihonni tanlang'})
    attempts = ExamAttempt.objects.select_related('user', 'exam').filter(
        exam_id=data['exam'], submitted_at__isnull=True, answered_count__gt=0)
    return JsonResponse({'ok': True, 'done': _finalize_many(attempts)})


def _finalize(attempt):
    result = finalize_attempt(attempt)
    Notification.objects.create(
        user=attempt.user,
        title="Javoblaringiz qabul qilindi",
        message=f"«{attempt.exam.title}» imtihonidagi javoblaringiz saqlangan nusxadan qabul qilindi. "
                f"Natijani «Natijalar» bo'limida ko'rishingiz mumkin.",
        type='success',
    )
    return result


@panel_required
@require_POST
def attempt_finalize(request, pk):
    attempt = get_object_or_404(ExamAttempt.objects.select_related('user', 'exam'), pk=pk)
    if attempt.is_submitted:
        return JsonResponse({'ok': False, 'error': "Bu urinish allaqachon yuborilgan"})
    result = _finalize(attempt)
    return JsonResponse({'ok': True, 'result_id': result.pk,
                         'url': reverse('exams:result_detail', args=[result.pk])})


@panel_required
@require_POST
def attempts_bulk_finalize(request):
    data, err = parse_json_body(request)
    if err:
        return err
    attempts = ExamAttempt.objects.select_related('user', 'exam').filter(
        pk__in=data.get('ids', []), submitted_at__isnull=True)
    return JsonResponse({'ok': True, 'done': _finalize_many(attempts)})


def _finalize_many(attempts):
    done = 0
    for attempt in attempts:
        try:
            _finalize(attempt)
            done += 1
        except Exception:
            logger.exception('Finalizing attempt %s failed', attempt.pk)
    return done


@panel_required
@require_POST
def attempt_delete(request, pk):
    get_object_or_404(ExamAttempt, pk=pk).delete()
    return JsonResponse({'ok': True})


# ── AI Exam Generator ──────────────────────────────────────────────────────────
@panel_required
def exam_generate(request):
    """Step 1: form; Step 2: POST → generate with progress → save → redirect."""
    if request.method == 'POST':
        section_type = request.POST.get('section_type', 'reading')
        variant = request.POST.get('variant', 'academic')
        topic = request.POST.get('topic', '').strip()
        model = request.POST.get('model', 'gpt-4o')
        price = request.POST.get('price', 0)
        custom_duration = request.POST.get('duration_minutes')

        from django.http import StreamingHttpResponse

        def stream_generator():
            yield f'<script>updateProgress(1, "AI bog\'lanmoqda...");</script>'
            try:
                from core.ai_utils import generate_ielts_exam
                from exams.models import Section, Question
                from django.db import transaction as db_tx

                exam_data = None
                # generator yields (percentage, message, [data])
                for p, m, *extra in generate_ielts_exam(
                    section_type=section_type,
                    variant=variant,
                    topic=topic or None,
                    model=model,
                ):
                    yield f'<script>updateProgress({int(p)}, "{m}");</script>'
                    if extra and extra[0]:
                        exam_data = extra[0]

                if not exam_data:
                    yield f'<script>showError("AI ma\'lumot qaytarmadi.");</script>'
                    return

                yield f'<script>updateProgress(98, "Ma\'lumotlar bazasiga saqlanmoqda...");</script>'
                
                # Use custom duration if provided, otherwise use AI's
                final_duration = int(custom_duration) if custom_duration else exam_data['duration_minutes']

                with db_tx.atomic():
                    exam = Exam.objects.create(
                        title=exam_data['title'],
                        description=exam_data['description'],
                        exam_type=exam_data['exam_type'],
                        price=price,
                        duration_minutes=final_duration,
                        is_active=False,
                        is_ai_generated=True,
                        ai_metadata=exam_data.get('ai_metadata'),
                    )
                    # Types the AI must give an exact answer for; writing_task
                    # and short_answer (speaking) are graded separately and
                    # are expected to have an empty correct_answer.
                    _GRADABLE_TYPES = {'mcq', 'tfng', 'gap_fill', 'matching'}
                    empty_answer_count = 0

                    for order, sec_data in enumerate(exam_data.get('sections', []), start=1):
                        from django.core.files.base import ContentFile
                        section = Section.objects.create(
                            exam=exam,
                            title=sec_data['title'],
                            section_type=sec_data['section_type'],
                            order=sec_data.get('order', order),
                            duration_minutes=sec_data.get('duration_minutes', 0),
                            content=sec_data.get('content', ''),
                            extra_data=sec_data.get('extra_data'),
                        )
                        if sec_data.get('audio_bytes'):
                            section.audio_file.save(
                                f"listening_{section.pk}.mp3",
                                ContentFile(sec_data['audio_bytes'])
                            )
                        
                        if sec_data.get('image_url'):
                            import requests
                            try:
                                img_resp = requests.get(sec_data['image_url'], timeout=15)
                                if img_resp.status_code == 200:
                                    section.image.save(
                                        f"task1_{section.pk}.png",
                                        ContentFile(img_resp.content)
                                    )
                            except requests.RequestException:
                                logger.warning(
                                    "AI exam generation: failed to download chart image for section %s from %s",
                                    section.pk, sec_data['image_url'], exc_info=True,
                                )

                        for q_data in sec_data.get('questions', []):
                            qtype = q_data.get('question_type', 'gap_fill')
                            answer = q_data.get('correct_answer', '')
                            if qtype in _GRADABLE_TYPES and not str(answer).strip():
                                empty_answer_count += 1
                            Question.objects.create(
                                section=section,
                                order=q_data.get('order', 1),
                                text=q_data['text'],
                                question_type=qtype,
                                correct_answer=answer,
                                options=q_data.get('options', []),
                                explanation=q_data.get('explanation', ''),
                                model_answer=q_data.get('model_answer', ''),
                                word_limit=q_data.get('word_limit', 0),
                            )

                redirect_url = redirect("panel:exam_detail", pk=exam.pk).url
                if empty_answer_count:
                    # AI hit its token budget before finishing some questions
                    # (see _normalise_questions' placeholder fallback) — flag
                    # it loudly instead of silently shipping a broken exam.
                    warn_msg = (
                        f"Diqqat: {empty_answer_count} ta savolda AI javob bermadi "
                        f"(token limitiga yetgan bo'lishi mumkin). Faollashtirishdan oldin "
                        f"bo'limlarni ochib, bo'sh javoblarni qo'lda to'ldiring yoki bo'limni qayta generatsiya qiling."
                    )
                    yield f'<script>updateProgress(100, "Tayyor (ogohlantirish bilan)"); alert({json.dumps(warn_msg)}); window.location.href="{redirect_url}";</script>'
                else:
                    yield f'<script>updateProgress(100, "Tayyor! Yo\'naltirilmoqda..."); window.location.href="{redirect_url}";</script>'

            except Exception as e:
                import traceback
                print(traceback.format_exc())
                yield f'<script>showError("AI xatoligi: {str(e).replace(chr(34), chr(39))}");</script>'

        # Initial layout for streaming
        initial_html = render(request, 'panel/exam_generate.html', {
            'section_types': [
                ('reading', 'Reading (3 passages, 40+ savol)'),
                ('writing', 'Writing (Task 1 + Task 2)'),
                ('listening', 'Listening (4 sections, 40 savol)'),
                ('speaking', 'Speaking (Part 1, 2, 3)'),
                ('full', 'Full Mock Test (barcha 4 bo\'lim)'),
            ],
            'streaming': True
        }).content.decode('utf-8')
        
        return StreamingHttpResponse(chain([initial_html], stream_generator()))

    return render(request, 'panel/exam_generate.html', {
        'section_types': [
            ('reading', 'Reading (3 passages, 40+ savol)'),
            ('writing', 'Writing (Task 1 + Task 2)'),
            ('listening', 'Listening (4 sections, 40 savol)'),
            ('speaking', 'Speaking (Part 1, 2, 3)'),
            ('full', 'Full Mock Test (barcha 4 bo\'lim)'),
        ],
    })


def _save_question_from_post(request, section, question=None):
    """Validate + save Question fields (type-specific) from request.POST.
    Returns an Uzbek error message on failure, or None on success."""
    text = request.POST.get('text', '').strip()
    qtype = request.POST.get('question_type', '')
    explanation = request.POST.get('explanation', '').strip()

    if not text:
        return "Savol matnini kiriting"
    if qtype not in dict(Question.QUESTION_TYPES):
        return "Savol turini tanlang"

    options, correct_answer, model_answer, word_limit = [], '', '', 0

    if qtype == 'mcq':
        option_texts = [t.strip() for t in request.POST.getlist('option_text') if t.strip()]
        if len(option_texts) < 2:
            return "Kamida 2 ta variant kiriting"
        try:
            correct_idx = int(request.POST.get('correct_option', ''))
        except ValueError:
            return "To'g'ri javobni belgilang"
        if not (0 <= correct_idx < len(option_texts)):
            return "To'g'ri javobni belgilang"
        options = [{'key': chr(65 + i), 'text': t} for i, t in enumerate(option_texts)]
        correct_answer = options[correct_idx]['key']
    elif qtype == 'tfng':
        correct_answer = request.POST.get('correct_answer_tfng', '').strip()
        if correct_answer not in ('True', 'False', 'Not Given'):
            return "To'g'ri javobni tanlang"
    elif qtype in ('gap_fill', 'matching'):
        correct_answer = request.POST.get('correct_answer_text', '').strip()
        if not correct_answer:
            return "To'g'ri javobni kiriting"
    elif qtype == 'writing_task':
        model_answer = request.POST.get('model_answer', '').strip()
        try:
            word_limit = int(request.POST.get('word_limit') or 0)
        except ValueError:
            return "So'z chegarasi butun son bo'lishi kerak"
    # short_answer: text + explanation (tip) only, no extra fields

    if question is None:
        question = Question(section=section)
        question.order = (section.questions.aggregate(Max('order'))['order__max'] or 0) + 1

    question.text = text
    question.question_type = qtype
    question.options = options
    question.correct_answer = correct_answer
    question.explanation = explanation
    question.model_answer = model_answer
    question.word_limit = word_limit
    question.save()
    return None


def _question_initial(question):
    """Plain-dict field defaults for question_form.html — always a real
    dict (never None) so `{{ x|default:initial.field }}` in the template
    never has to resolve an attribute on a possibly-None `question`."""
    if question is None:
        return {'text': '', 'question_type': '', 'correct_answer_tfng': '', 'correct_answer_text': '',
                'model_answer': '', 'word_limit': 0, 'explanation': ''}
    return {
        'text': question.text, 'question_type': question.question_type,
        'correct_answer_tfng': question.correct_answer, 'correct_answer_text': question.correct_answer,
        'model_answer': question.model_answer, 'word_limit': question.word_limit,
        'explanation': question.explanation,
    }


@panel_required
def question_create(request, section_pk):
    section = get_object_or_404(Section, pk=section_pk)
    error = None
    if request.method == 'POST':
        error = _save_question_from_post(request, section)
        if not error:
            return redirect('panel:exam_detail', pk=section.exam.pk)
    return render(request, 'panel/question_form.html', {
        'exam': section.exam, 'section': section, 'question': None,
        'question_types': Question.QUESTION_TYPES, 'error': error,
        'initial': _question_initial(None),
    })


@panel_required
def question_edit(request, pk):
    question = get_object_or_404(Question, pk=pk)
    section = question.section
    error = None
    if request.method == 'POST':
        error = _save_question_from_post(request, section, question)
        if not error:
            return redirect('panel:exam_detail', pk=section.exam.pk)
    return render(request, 'panel/question_form.html', {
        'exam': section.exam, 'section': section, 'question': question,
        'question_types': Question.QUESTION_TYPES, 'error': error,
        'initial': _question_initial(question),
    })


@panel_required
@require_POST
def question_move(request, pk):
    question = get_object_or_404(Question, pk=pk)
    data, err = parse_json_body(request, ok_field=True)
    if err:
        return err
    siblings = list(Question.objects.filter(section=question.section).order_by('order', 'pk'))
    idx = next((i for i, q in enumerate(siblings) if q.pk == question.pk), None)
    swap_idx = idx - 1 if data.get('direction') == 'up' else idx + 1
    if idx is None or swap_idx < 0 or swap_idx >= len(siblings):
        return JsonResponse({'ok': True})
    other = siblings[swap_idx]
    question.order, other.order = other.order, question.order
    Question.objects.bulk_update([question, other], ['order'])
    return JsonResponse({'ok': True})


@panel_required
@require_POST
def question_duplicate(request, pk):
    """Copy a question into the same section, then drop straight into
    editing the copy — faster than retyping near-identical MCQs by hand."""
    question = get_object_or_404(Question, pk=pk)
    new_question = Question.objects.create(
        section=question.section, text=question.text, question_type=question.question_type,
        options=question.options, correct_answer=question.correct_answer, explanation=question.explanation,
        model_answer=question.model_answer, word_limit=question.word_limit,
        order=(question.section.questions.aggregate(Max('order'))['order__max'] or 0) + 1,
    )
    return redirect('panel:question_edit', pk=new_question.pk)


@panel_required
@require_POST
def question_delete(request, pk):
    question = get_object_or_404(Question, pk=pk)
    question.delete()
    return JsonResponse({'ok': True})


@panel_required
def create_admin(request):
    if not request.user.is_superuser:
        return redirect('panel:dashboard')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        is_superuser = request.POST.get('is_superuser') == 'on'

        if not username or not password:
            error = 'Username va parol majburiy'
        elif len(password) < 8:
            error = 'Parol kamida 8 ta belgi bo\'lishi kerak'
        elif password != password2:
            error = 'Parollar mos kelmadi'
        elif User.objects.filter(username=username).exists():
            error = 'Bu username allaqachon mavjud'
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=True,
                is_superuser=is_superuser,
            )
            return redirect('panel:user_detail', pk=user.pk)

    return render(request, 'panel/create_admin.html', {'error': error})


# ── Site settings ────────────────────────────────────────────────────────────
@panel_required
def site_settings(request):
    settings_obj = SiteSettings.get()
    if request.method == 'POST':
        # Only touch site_name if the form actually sent it, so a request
        # that omits the field (rather than clearing it) doesn't get
        # rejected wholesale — the empty-value check only guards against an
        # explicit blank submission from the settings form itself.
        if 'site_name' in request.POST:
            site_name = request.POST.get('site_name', '').strip()
            if not site_name:
                messages.error(request, "Sayt nomi bo'sh bo'lishi mumkin emas")
                return redirect('panel:site_settings')
            settings_obj.site_name = site_name

        if 'logo' in request.FILES:
            logo = request.FILES['logo']
            error = validate_image_upload(logo, 2, {'image/jpeg', 'image/png', 'image/webp', 'image/svg+xml'})
            if error:
                messages.error(request, error)
                return redirect('panel:site_settings')
            settings_obj.logo = logo

        settings_obj.site_description = request.POST.get('site_description', '').strip()
        settings_obj.announcement = request.POST.get('announcement', '').strip()
        settings_obj.announcement_active = request.POST.get('announcement_active') == 'on'
        settings_obj.maintenance_mode = request.POST.get('maintenance_mode') == 'on'
        settings_obj.proctor_alarm = request.POST.get('proctor_alarm') == 'on'
        settings_obj.exam_password_required = request.POST.get('exam_password_required') == 'on'
        settings_obj.camera_proctoring = request.POST.get('camera_proctoring') == 'on'
        settings_obj.maintenance_message = request.POST.get('maintenance_message', '').strip()
        settings_obj.save()
        messages.success(request, 'Sozlamalar saqlandi')
        return redirect('panel:site_settings')
    return render(request, 'panel/settings.html', {'settings': settings_obj})


# ── Notifications ─────────────────────────────────────────────────────────────
@panel_required
def panel_notifications(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        message_text = request.POST.get('message', '').strip()
        ntype = request.POST.get('type', 'info')
        target_username = request.POST.get('target_username', '').strip()
        if not title or not message_text:
            messages.error(request, "Sarlavha va matn kiritilishi shart")
            return redirect('panel:notifications')
        target_user = None
        if target_username:
            try:
                target_user = User.objects.get(username=target_username)
            except User.DoesNotExist:
                messages.error(request, f"'{target_username}' nomli foydalanuvchi topilmadi")
                return redirect('panel:notifications')
        Notification.objects.create(user=target_user, title=title, message=message_text, type=ntype)
        messages.success(request, 'Xabarnoma yuborildi' if target_user else "Xabarnoma barchaga yuborildi")
        return redirect('panel:notifications')

    notifications = Notification.objects.select_related('user').order_by('-created_at')[:100]
    return render(request, 'panel/notifications.html', {'notifications': notifications})


@panel_required
@require_POST
def notification_delete(request, pk):
    Notification.objects.filter(pk=pk).delete()
    return JsonResponse({'ok': True})


# ── Promo codes ────────────────────────────────────────────────────────────────
@panel_required
def promocodes_list(request):
    from decimal import Decimal, InvalidOperation
    from django.utils.dateparse import parse_datetime

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        max_uses = request.POST.get('max_uses') or 1
        expires_raw = request.POST.get('expires_at', '').strip()

        if not code:
            messages.error(request, 'Kod kiritilishi shart')
            return redirect('panel:promocodes')
        if PromoCode.objects.filter(code=code).exists():
            messages.error(request, 'Bu kod allaqachon mavjud')
            return redirect('panel:promocodes')

        try:
            discount_amount = Decimal(request.POST.get('discount_amount') or '0')
            discount_percent = int(request.POST.get('discount_percent') or 0)
            max_uses = int(max_uses)
        except (InvalidOperation, ValueError):
            messages.error(request, "Chegirma/soni noto'g'ri formatda")
            return redirect('panel:promocodes')

        # Negative values would make TopUpView's bonus calculation reduce
        # (or zero out) the amount instead of adding to it — clamp to the
        # sane range implied by the form (0-100% and a non-negative bonus).
        discount_amount = max(Decimal('0'), discount_amount)
        discount_percent = max(0, min(100, discount_percent))
        max_uses = max(1, max_uses)

        expires_at = None
        if expires_raw:
            expires_at = parse_datetime(expires_raw)
            if expires_at and timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at)

        try:
            PromoCode.objects.create(
                code=code,
                discount_amount=discount_amount,
                discount_percent=discount_percent,
                max_uses=max_uses,
                expires_at=expires_at,
            )
        except IntegrityError:
            messages.error(request, 'Bu kod allaqachon mavjud')
            return redirect('panel:promocodes')
        messages.success(request, 'Promo kod yaratildi')
        return redirect('panel:promocodes')

    promocodes = PromoCode.objects.order_by('-created_at')
    return render(request, 'panel/promocodes.html', {'promocodes': promocodes})


@panel_required
@require_POST
def promocode_toggle(request, pk):
    promo = get_object_or_404(PromoCode, pk=pk)
    promo.is_active = not promo.is_active
    promo.save(update_fields=['is_active'])
    return JsonResponse({'ok': True, 'is_active': promo.is_active})


@panel_required
@require_POST
def promocode_delete(request, pk):
    get_object_or_404(PromoCode, pk=pk).delete()
    return JsonResponse({'ok': True})


# ── Ingliz tili kursi (learn/) ─────────────────────────────────────────────────
def _step_preview(step):
    """Short text of an exercise for tables (question, sentence or prompt)."""
    text = step.get('q') or step.get('text') or step.get('uz') or step.get('prompt_uz') or step.get('type', '')
    return str(text).replace('**', '')[:120]


@panel_required
def english_overview(request):
    now = timezone.now()
    today = timezone.localdate()
    week_start = today - timedelta(days=6)
    course = get_course()
    lessons = course['lessons']
    progress = LessonProgress.objects.exclude(lesson_slug__startswith='story:')

    def active_since(day):
        return DailyXP.objects.filter(date__gte=day, xp__gt=0).values('user').distinct().count()

    stats = {
        'learners': LearnerProfile.objects.count(),
        'active_today': DailyXP.objects.filter(date=today, xp__gt=0).count(),
        'active_7': active_since(week_start),
        'active_30': active_since(today - timedelta(days=29)),
        'completions': progress.count(),
        'avg_score': progress.aggregate(a=Avg('best_score'))['a'] or 0,
        'stories_read': LessonProgress.objects.filter(lesson_slug__startswith='story:').count(),
        'xp_week': DailyXP.objects.filter(date__gte=week_start).aggregate(s=Sum('xp'))['s'] or 0,
        'app_users': ApiToken.objects.values('user').distinct().count(),
        'app_active_7': ApiToken.objects.filter(last_used_at__gte=now - timedelta(days=7)).values('user').distinct().count(),
        'mistakes_open': Mistake.objects.count(),
    }

    # Last 14 days: learners with XP and total XP per day.
    start = today - timedelta(days=13)
    by_day = {r['date']: r for r in DailyXP.objects.filter(date__gte=start).values('date')
              .annotate(users=Count('user', filter=Q(xp__gt=0)), xp=Sum('xp'))}
    days = [start + timedelta(days=i) for i in range(14)]
    chart = {
        'labels': [d.strftime('%d %b') for d in days],
        'users': [by_day.get(d, {}).get('users', 0) for d in days],
        'xp': [by_day.get(d, {}).get('xp', 0) or 0 for d in days],
    }

    level_counts = dict(LearnerProfile.objects.values_list('level').annotate(c=Count('id')))
    done_by_slug = dict(progress.values_list('lesson_slug').annotate(c=Count('id')))
    stories = list(get_stories().values())
    levels = []
    for code in LEVELS:
        lv = course['levels'][code]
        slugs = [l['slug'] for u in lv['units'] for l in u['lessons']]
        levels.append({
            'code': code, 'name': LEVEL_INFO[code]['name'],
            'learners': level_counts.get(code, 0),
            'units': len(lv['units']), 'lessons': len(slugs),
            'words': sum(len(lessons[s]['words']) for s in slugs),
            'stories': sum(1 for st in stories if st['level'] == code),
            'completions': sum(done_by_slug.get(s, 0) for s in slugs),
        })
    unset_level = level_counts.get('', 0)

    top_lessons = []
    for row in (progress.values('lesson_slug').annotate(c=Count('id'), avg=Avg('best_score'), tries=Sum('attempts'))
                .order_by('-c')[:10]):
        lesson = lessons.get(row['lesson_slug'])
        top_lessons.append({**row, 'title': lesson['title'] if lesson else row['lesson_slug'],
                            'level': lesson['level'] if lesson else '—'})

    # Where learners struggle: exercises most people got wrong.
    hardest = []
    for row in (Mistake.objects.values('lesson_slug', 'step_index')
                .annotate(users=Count('user'), wrongs=Sum('wrong_count')).order_by('-users', '-wrongs')[:10]):
        lesson = lessons.get(row['lesson_slug'])
        step = lesson['steps'][row['step_index']] if lesson and row['step_index'] < len(lesson['steps']) else {}
        answer = step.get('answer')
        if step.get('type') == 'choice' and isinstance(answer, int) and answer < len(step.get('options', [])):
            answer = step['options'][answer]
        elif isinstance(answer, list):
            answer = answer[0] if answer else ''
        hardest.append({**row, 'lesson': lesson['title'] if lesson else row['lesson_slug'],
                        'type': step.get('type', '?'), 'text': _step_preview(step), 'answer': answer or ''})

    week_rows = list(DailyXP.objects.filter(date__gte=week_start).values('user')
                     .annotate(total=Sum('xp')).filter(total__gt=0).order_by('-total')[:10])
    week_users = User.objects.in_bulk([r['user'] for r in week_rows])
    top_week = [{'user': week_users.get(r['user']), 'xp': r['total']} for r in week_rows]

    recent = []
    for p in LessonProgress.objects.select_related('user').order_by('-completed_at')[:15]:
        is_story = p.lesson_slug.startswith('story:')
        item = get_stories().get(p.lesson_slug[6:]) if is_story else lessons.get(p.lesson_slug)
        recent.append({'p': p, 'story': is_story, 'title': item['title'] if item else p.lesson_slug})

    return render(request, 'panel/english.html', {
        'stats': stats, 'levels': levels, 'unset_level': unset_level,
        'top_lessons': top_lessons, 'hardest': hardest, 'top_week': top_week, 'recent': recent,
        'content_errors': validate_course()[:20],
        'chart_labels': json.dumps(chart['labels']), 'chart_users': json.dumps(chart['users']),
        'chart_xp': json.dumps(chart['xp']),
    })


@panel_required
def english_learners(request):
    q = request.GET.get('q', '').strip()
    level = request.GET.get('level', '')
    sort = request.GET.get('sort', 'active')
    profiles = LearnerProfile.objects.select_related('user')
    if q:
        profiles = profiles.filter(Q(user__username__icontains=q) | Q(user__first_name__icontains=q)
                                   | Q(user__last_name__icontains=q))
    if level in LEVELS:
        profiles = profiles.filter(level=level)
    elif level == 'none':
        profiles = profiles.filter(level='')
    order = {'xp': ['-xp'], 'streak': ['-streak', '-xp'], 'new': ['-pk']}.get(sort, ['-last_active', '-xp'])
    page = Paginator(profiles.order_by(*order), 50).get_page(request.GET.get('page'))

    ids = [p.user_id for p in page]
    lesson_stats = {r['user']: r for r in LessonProgress.objects.filter(user__in=ids)
                    .exclude(lesson_slug__startswith='story:').values('user')
                    .annotate(done=Count('id'), avg=Avg('best_score'))}
    stories = dict(LessonProgress.objects.filter(user__in=ids, lesson_slug__startswith='story:')
                   .values_list('user').annotate(c=Count('id')))
    words = dict(Vocabulary.objects.filter(user__in=ids).values_list('user').annotate(c=Count('id')))
    mistakes = dict(Mistake.objects.filter(user__in=ids).values_list('user').annotate(c=Count('id')))
    devices = {}
    for t in ApiToken.objects.filter(user__in=ids).order_by('-last_used_at', '-created_at'):
        devices.setdefault(t.user_id, t)
    rows = [{
        'p': p, 'done': lesson_stats.get(p.user_id, {}).get('done', 0),
        'avg': lesson_stats.get(p.user_id, {}).get('avg'),
        'stories': stories.get(p.user_id, 0), 'words': words.get(p.user_id, 0),
        'mistakes': mistakes.get(p.user_id, 0), 'device': devices.get(p.user_id),
    } for p in page]
    return render(request, 'panel/english_learners.html', {
        'rows': rows, 'page': page, 'q': q, 'level': level, 'sort': sort, 'levels': LEVELS,
        'total': profiles.count(),
    })


@panel_required
def english_devices(request):
    q = request.GET.get('q', '').strip()
    now = timezone.now()
    tokens = ApiToken.objects.select_related('user').order_by(F('last_used_at').desc(nulls_last=True), '-created_at')
    if q:
        tokens = tokens.filter(Q(user__username__icontains=q) | Q(device__icontains=q) | Q(ip__icontains=q))
    all_tokens = ApiToken.objects.all()
    stats = {
        'sessions': all_tokens.count(),
        'users': all_tokens.values('user').distinct().count(),
        'active_24h': all_tokens.filter(last_used_at__gte=now - timedelta(hours=24)).count(),
        'active_7d': all_tokens.filter(last_used_at__gte=now - timedelta(days=7)).count(),
        'android': all_tokens.filter(platform__istartswith='android').count(),
        'ios': all_tokens.filter(platform__istartswith='ios').count(),
    }
    page = Paginator(tokens, 50).get_page(request.GET.get('page'))
    return render(request, 'panel/english_devices.html', {'page': page, 'q': q, 'stats': stats})


@panel_required
@require_POST
def english_device_revoke(request, pk):
    token = get_object_or_404(ApiToken.objects.select_related('user'), pk=pk)
    token.delete()
    messages.success(request, f"{token.user.username} — {token.device or 'qurilma'} ilovadan chiqarildi")
    nxt = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = reverse('panel:english_devices')
    return redirect(nxt)


@panel_required
def english_app(request):
    """Upload app builds; the newest one is offered on /learn/app/ and to old installs."""
    if request.method == 'POST':
        version = request.POST.get('version', '').strip()
        apk = request.FILES.get('apk')
        url = request.POST.get('url', '').strip()
        try:
            build = int(request.POST.get('build', ''))
        except ValueError:
            build = 0
        if not version or build <= 0:
            messages.error(request, "Versiya va build raqamini kiriting")
        elif not apk and not url:
            messages.error(request, "APK fayl yoki havola kerak")
        elif apk and not apk.name.lower().endswith('.apk'):
            messages.error(request, "Faqat .apk fayl yuklanadi")
        elif AppRelease.objects.filter(build=build).exists():
            messages.error(request, f"{build}-build allaqachon bor — kattaroq raqam kiriting")
        else:
            AppRelease.objects.create(
                version=version, build=build, apk=apk or '', url=url,
                notes=request.POST.get('notes', '').strip(), force_update=bool(request.POST.get('force_update')),
            )
            messages.success(request, f"{version} ({build}) e'lon qilindi")
            return redirect('panel:english_app')
    releases = AppRelease.objects.all()
    installed = dict(ApiToken.objects.exclude(app_version='').values_list('app_version').annotate(c=Count('id')))
    return render(request, 'panel/english_app.html', {
        'releases': releases, 'installed': sorted(installed.items(), key=lambda kv: kv[0], reverse=True),
        'drafts': LessonDraft.objects.count(),
    })


@panel_required
@require_POST
def english_app_delete(request, pk):
    release = get_object_or_404(AppRelease, pk=pk)
    if release.apk:
        release.apk.delete(save=False)
    release.delete()
    messages.success(request, "Versiya o'chirildi")
    return redirect('panel:english_app')
