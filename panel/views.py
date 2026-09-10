import csv
import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Avg, Count, F, Max, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import SiteSettings, Notification, PromoCode
from core.utils import (
    daily_series, html_paragraphs_to_text, monthly_series, parse_json_body,
    text_to_html_paragraphs, validate_audio_upload, validate_image_upload,
)
from exams.models import Exam, Question, Section, UserResult
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
        'avg_score': UserResult.objects.aggregate(a=Avg('score'))['a'] or 0,
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
    stats = results.aggregate(avg=Avg('score'), total=Count('id'))
    return render(request, 'panel/user_detail.html', {
        'obj': user, 'results': results, 'transactions': transactions, 'stats': stats
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
    exams = Exam.objects.annotate(sections_count=Count('sections'), results_count=Count('userresult')).order_by('-created_at')
    if q:
        exams = exams.filter(title__icontains=q)
    if etype:
        exams = exams.filter(exam_type=etype)
    if show == 'pending_review':
        exams = exams.filter(is_ai_generated=True, is_reviewed=False)
    pending_review_count = Exam.objects.filter(is_ai_generated=True, is_reviewed=False).count()
    return render(request, 'panel/exams_list.html', {
        'exams': exams, 'q': q, 'etype': etype,
        'exam_types': Exam.EXAM_TYPES,
        'pending_review_count': pending_review_count,
        'show': show,
    })


@panel_required
def exam_detail(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    sections = exam.sections.prefetch_related('questions').all()
    results = UserResult.objects.filter(exam=exam).select_related('user').order_by('-completed_at')[:20]
    stats = UserResult.objects.filter(exam=exam).aggregate(avg=Avg('score'), total=Count('id'))
    return render(request, 'panel/exam_detail.html', {
        'exam': exam, 'sections': sections, 'results': results, 'stats': stats
    })


@panel_required
def exam_create(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        exam_type = request.POST.get('exam_type', 'mock')
        price = request.POST.get('price', 0)
        duration = request.POST.get('duration_minutes', 60)
        description = request.POST.get('description', '')
        is_active = request.POST.get('is_active') == 'on'
        if title:
            exam = Exam.objects.create(
                title=title, exam_type=exam_type, price=price,
                duration_minutes=duration, description=description, is_active=is_active
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
        error = validate_audio_upload(audio_file, 25, _AUDIO_TYPES)
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
    w.writerow(['ID', 'Foydalanuvchi', 'Imtihon', 'Ball', 'Listening', 'Reading', 'Writing', 'Speaking', 'Sana'])
    for r in UserResult.objects.select_related('user', 'exam').order_by('-completed_at'):
        w.writerow([r.pk, r.user.username, r.exam.title, r.score, r.listening_score, r.reading_score, r.writing_score, r.speaking_score, r.completed_at.strftime('%Y-%m-%d %H:%M')])
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
        'avg_score': UserResult.objects.aggregate(a=Avg('score'))['a'] or 0,
        'avg_l': UserResult.objects.aggregate(a=Avg('listening_score'))['a'] or 0,
        'avg_r': UserResult.objects.aggregate(a=Avg('reading_score'))['a'] or 0,
        'avg_w': UserResult.objects.aggregate(a=Avg('writing_score'))['a'] or 0,
        'avg_s': UserResult.objects.aggregate(a=Avg('speaking_score'))['a'] or 0,
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
    results = UserResult.objects.select_related('user', 'exam').order_by('-completed_at')
    if exam_id:
        results = results.filter(exam_id=exam_id)
    exams = Exam.objects.all()
    return render(request, 'panel/results_list.html', {
        'results': results[:100], 'exams': exams, 'exam_id': exam_id
    })


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
