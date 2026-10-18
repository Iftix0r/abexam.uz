import logging
import math
import re
from itertools import groupby

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from core.utils import get_client_ip, parse_json_body
from .models import Exam, ExamAttempt, UserAnswer, UserResult, Question
from . import camera
from .passwords import clear_exam_unlocked, exam_is_unlocked, exam_scope, password_required_for, try_unlock
from users.models import User

submit_logger = logging.getLogger('exams.submit')

# Generous enough to cover sitting on the exam-detail page plus the full
# attempt; a stale flag just means a benign extra grace period, not a way
# to get free access (payment already happened when it was set).
_EXAM_PAID_TTL = 6 * 3600


def _exam_paid_key(user_pk, exam_pk):
    return f'exam_paid_{user_pk}_{exam_pk}'


def exam_is_paid(user_pk, exam_pk):
    return bool(cache.get(_exam_paid_key(user_pk, exam_pk)))


def mark_exam_paid(user_pk, exam_pk):
    cache.set(_exam_paid_key(user_pk, exam_pk), True, timeout=_EXAM_PAID_TTL)


def clear_exam_paid(user_pk, exam_pk):
    cache.delete(_exam_paid_key(user_pk, exam_pk))


def exam_needs_password(user, exam):
    """True while this user still has to enter the exam's hourly password
    before starting it — admins included."""
    return password_required_for(user) and not exam_is_unlocked(user.pk, exam.pk)


def _fuzzy_match(user_ans: str, correct: str) -> bool:
    """IELTS-style flexible answer checking: case, articles, slash-alternatives."""
    u = user_ans.strip().lower()
    c = correct.strip().lower()
    if not u:
        return False
    if u == c:
        return True
    # Accept any alternative separated by /
    alternatives = [a.strip() for a in c.split('/')]
    if u in alternatives:
        return True
    # Strip leading articles and compare
    for art in ('a ', 'an ', 'the '):
        u2 = u[len(art):] if u.startswith(art) else u
        for alt in alternatives:
            c2 = alt[len(art):] if alt.startswith(art) else alt
            if u2 == c2:
                return True
    return False


def _choose_many_groups(questions):
    """"Choose TWO letters" is stored as consecutive mcq rows sharing the same
    options and the same slash-separated answer ("C/E"), each accepting
    either letter. Maps every such question's id to one shared set of the
    still-unclaimed correct letters, so picking the same right letter in
    both rows only earns the mark once."""
    groups = {}
    i, n = 0, len(questions)
    while i < n:
        q = questions[i]
        j = i + 1
        if q.question_type == 'mcq' and '/' in q.correct_answer:
            while (j < n and questions[j].question_type == 'mcq'
                   and questions[j].correct_answer == q.correct_answer
                   and questions[j].options == q.options):
                j += 1
            if j - i >= 2:
                remaining = {a.strip().lower() for a in q.correct_answer.split('/')}
                for member in questions[i:j]:
                    groups[member.id] = remaining
        i = j
    return groups


def grade_answers(questions, answer_for):
    """{question.id: is_correct} for one section's questions (in order).
    answer_for(question) returns the user's raw answer."""
    groups = _choose_many_groups(questions)
    verdicts = {}
    for q in questions:
        user_ans = str(answer_for(q)).strip()
        remaining = groups.get(q.id)
        if remaining is None:
            verdicts[q.id] = _fuzzy_match(user_ans, q.correct_answer)
        else:
            key = user_ans.lower()
            verdicts[q.id] = key in remaining
            remaining.discard(key)
    return verdicts


# IELTS Listening/Reading band table (scaled to 40 questions)
_IELTS_TABLE = [
    (39, 9.0), (37, 8.5), (35, 8.0), (32, 7.5), (30, 7.0),
    (27, 6.5), (23, 6.0), (18, 5.5), (16, 5.0), (13, 4.5),
    (10, 4.0), (8, 3.5), (6, 3.0), (5, 2.5), (4, 2.0),
    (3, 1.5), (1, 1.0),
]


def calc_band(correct, total):
    """IELTS-accurate band score (scaled to 40 questions)."""
    if total == 0:
        return 0.0
    scaled = correct / total * 40
    for threshold, band in _IELTS_TABLE:
        if scaled >= threshold:
            return band
    return 0.0


def round_band(value):
    """IELTS rounding to the nearest half band (.25 → .5, .75 → next whole)."""
    return math.floor(value * 2 + 0.5) / 2.0


def calc_writing_band(task_bands):
    """Overall Writing band from per-task bands. With the standard two
    tasks, Task 2 carries twice the weight of Task 1 (as in real IELTS)."""
    if not task_bands:
        return 0.0
    if len(task_bands) == 2:
        return round_band((task_bands[0] + 2 * task_bands[1]) / 3)
    return round_band(sum(task_bands) / len(task_bands))


def present_section_types(exam):
    """Section types the exam actually has, so a legitimate 0.0 band isn't
    mistaken for a section that doesn't exist in the exam."""
    types = set(exam.sections.values_list('section_type', flat=True))
    if not settings.SPEAKING_ENABLED:
        types.discard('speaking')
    return types


def compute_overall_band(band_by_type, present_types):
    active = [band_by_type[t] for t in present_types if t in band_by_type]
    return round(sum(active) / len(active) * 2) / 2.0 if active else 0.0


def band_label(score):
    if score >= 8.5: return "Expert"
    if score >= 7.5: return "Very Good User"
    if score >= 7.0: return "Good User"
    if score >= 6.5: return "Competent User"
    if score >= 6.0: return "Competent User"
    if score >= 5.5: return "Modest User"
    if score >= 5.0: return "Modest User"
    if score >= 4.5: return "Limited User"
    return "Extremely Limited"


class ExamDetailView(LoginRequiredMixin, DetailView):
    model = Exam
    template_name = 'exams/exam_detail.html'
    context_object_name = 'exam'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exam = self.object
        context['total_questions'] = sum(
            s.questions.count() for s in exam.sections.prefetch_related('questions').all()
        )
        context['user_results'] = UserResult.objects.filter(
            user=self.request.user, exam=exam
        ).order_by('-completed_at')[:3]
        context['last_graded'] = UserResult.objects.graded().filter(
            user=self.request.user, exam=exam
        ).order_by('-completed_at').first()
        context['needs_password'] = exam_needs_password(self.request.user, exam)
        return context


class ExamUnlockView(LoginRequiredMixin, View):
    """Checks the hourly test password from the exam page's start form and,
    when it's right, lets this student into the exam."""

    def post(self, request, pk):
        exam = get_object_or_404(Exam, pk=pk)
        if not exam_needs_password(request.user, exam):
            return redirect('exams:take_exam', pk=exam.pk)
        error = try_unlock(request.user.pk, exam_scope(exam.pk), request.POST.get('password', ''))
        if error:
            messages.error(request, error)
            return redirect('exams:exam_detail', pk=exam.pk)
        return redirect('exams:take_exam', pk=exam.pk)


class TakeExamView(LoginRequiredMixin, DetailView):
    model = Exam
    template_name = 'exams/take_exam.html'
    context_object_name = 'exam'

    def get(self, request, *args, **kwargs):
        exam = self.get_object()
        # Staff previewing a draft/paid exam before publishing it skips the
        # active/payment gates — only when explicitly requested, so a
        # staff member's own normal exam-taking flow is unaffected.
        is_preview = request.user.is_staff and request.GET.get('preview') == '1'
        if not exam.is_active and not is_preview:
            messages.error(request, "Bu imtihon hozirda faol emas.")
            return redirect('exams:exam_detail', pk=exam.pk)
        if is_preview:
            return super().get(request, *args, **kwargs)
        # Checked before the payment below, so a student without the
        # password is never charged for an exam they can't open.
        if exam_needs_password(request.user, exam):
            messages.info(request, "Testni boshlash uchun test parolini kiriting.")
            return redirect('exams:exam_detail', pk=exam.pk)
        if exam.price > 0 and not exam_is_paid(request.user.pk, exam.pk):
            # A Django session write only persists at the end of the
            # request, so two concurrent requests (double-click, retry)
            # can both see "not paid yet" before either commits — the DB
            # row lock below only serializes the balance update, not that
            # check. A short-lived cache lock closes that window, and the
            # "paid" flag itself lives in cache (not the session) so it's
            # visible immediately to any request, including ones on a
            # different session/tab.
            lock_key = f'exam_pay_lock_{request.user.pk}_{exam.pk}'
            if not cache.add(lock_key, 1, timeout=10):
                messages.error(request, "So'rov qayta ishlanmoqda, biroz kutib qayta urinib ko'ring.")
                return redirect('exams:exam_detail', pk=exam.pk)
            try:
                if not exam_is_paid(request.user.pk, exam.pk):
                    with transaction.atomic():
                        user = User.objects.select_for_update().get(pk=request.user.pk)
                        if user.balance < exam.price:
                            messages.error(request, f"Balans yetarli emas. Imtihon narxi: {exam.price} so'm")
                            return redirect('exams:exam_detail', pk=exam.pk)
                        user.balance -= exam.price
                        user.save(update_fields=['balance'])
                        request.user.balance = user.balance
                    mark_exam_paid(request.user.pk, exam.pk)
            finally:
                cache.delete(lock_key)
        return super().get(request, *args, **kwargs)

    _DEFAULT_DURATION = {'listening': 30, 'reading': 60, 'writing': 60, 'speaking': 60}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections = list(self.object.sections.prefetch_related('questions').all())
        if not settings.SPEAKING_ENABLED:
            sections = [s for s in sections if s.section_type != 'speaking']
        for section in sections:
            questions = list(section.questions.all())
            for q in questions:
                if section.section_type in ('listening', 'reading'):
                    q.group_title, q.group_instructions, q.body_text = _split_question_heading(q.text)
                else:
                    q.group_title, q.group_instructions, q.body_text = '', '', q.text
            section.render_blocks = _build_render_blocks(questions)
            section.q_count = len(questions)
            # A map/plan/diagram that a run of questions refers to (e.g.
            # Listening "Label the plan", Q16-20) is shown right above the
            # block that starts at that question, so it follows the same
            # one-Part-at-a-time paging as the questions themselves.
            question_images = (section.extra_data or {}).get('question_images') or {}
            for block in section.render_blocks:
                image = question_images.get(str(block['questions'][0].order))
                if image:
                    block['image_url'] = default_storage.url(image)

        # A skill (listening/reading/writing/speaking) can be modelled as
        # several Section rows (one per part/passage) sharing the same
        # exam-wide footer tab. Bundling them here — instead of letting the
        # template key everything off "the first section in the group" —
        # is what lets every part actually be reachable and counted, not
        # just the first one. Question numbering also has to run across the
        # whole group (1..N), not restart at 1 in every passage/part.
        tab_groups = []
        for stype, group_iter in groupby(sections, key=lambda s: s.section_type):
            group = list(group_iter)
            counter = 0
            for section in group:
                for q in section.questions.all():
                    counter += 1
                    q.display_number = counter
            tab_groups.append({
                'type': stype,
                'label': group[0].get_section_type_display(),
                'title': group[0].title if len(group) == 1 else group[0].get_section_type_display(),
                'question_count': sum(s.q_count for s in group),
                'duration_minutes': sum(s.duration_minutes for s in group) or self._DEFAULT_DURATION.get(stype, 60),
                # Sub-navigation pills for a skill split across several
                # Section rows (e.g. 3 Reading passages) — without these,
                # switching to passage 2/3 only worked by scrolling past
                # passage 1, and nothing on screen showed there was more
                # content below the fold.
                'sub_sections': [
                    {'id': s.id, 'label': f'{i}-qism'} for i, s in enumerate(group, start=1)
                ] if len(group) > 1 else [],
            })

        context['sections'] = sections
        context['tab_groups'] = tab_groups
        return context


_QUESTION_TITLE_RE = re.compile(r'^\s*\[([^\]]+)\]\s*')


def _split_question_heading(text):
    """The first question of each Listening/Reading group carries that
    group's header line: "[Passage title] Instructions…\nQuestion". Shown
    as-is, the title and instructions run straight into question 1's own
    prompt; split them off so the page renders them as a separate heading
    above the question. Returns (title, instructions, question text)."""
    title = ''
    match = _QUESTION_TITLE_RE.match(text)
    if match:
        title, text = match.group(1).strip(), text[match.end():]
    instructions = ''
    if '\n' in text:
        instructions, text = (part.strip() for part in text.split('\n', 1))
    return title, instructions, text


def _build_render_blocks(questions):
    """Groups consecutive 'matching'-type questions that share an identical
    options list into one shared-table block instead of repeating the same
    options under every question — mirrors the real IELTS computer-delivered
    layout (e.g. "match each statement to a person" or paragraph-matching,
    where several questions point at the same small set of choices)."""
    blocks = []
    i, n = 0, len(questions)
    while i < n:
        q = questions[i]
        if q.question_type == 'matching' and q.options:
            j = i + 1
            while (j < n and questions[j].question_type == 'matching'
                   and questions[j].options == q.options and not _has_heading(questions[j])):
                j += 1
            group = questions[i:j]
            if len(group) >= 2:
                blocks.append({'kind': 'group', 'questions': group, 'options': q.options})
            else:
                blocks.append({'kind': 'single', 'questions': [q]})
            i = j
        else:
            blocks.append({'kind': 'single', 'questions': [q]})
            i += 1
    for block in blocks:
        first = block['questions'][0]
        block['title'] = getattr(first, 'group_title', '')
        block['instructions'] = getattr(first, 'group_instructions', '')
    return blocks


def _has_heading(question):
    # A new title/instructions line starts a new question group, even when
    # its options happen to match the previous group's (e.g. two A–C sets).
    return bool(getattr(question, 'group_title', '') or getattr(question, 'group_instructions', ''))


class DemoAnswersView(LoginRequiredMixin, View):
    """Superuser-only QA tool: returns the correct answer for every gradable
    question in the exam, so staff can auto-fill + auto-submit an AI-generated
    exam and verify the scoring pipeline grades it correctly — without
    exposing answers to anyone else (this is a real leak vector otherwise)."""

    # Speaking questions require an actual audio recording and can't be
    # auto-answered; they're intentionally left out of the response.
    _GRADABLE_TYPES = {'mcq', 'tfng', 'gap_fill', 'matching'}

    def get(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            return JsonResponse({'error': "Ruxsat yo'q"}, status=403)
        exam = get_object_or_404(Exam, pk=kwargs['pk'])
        answers = {}
        for question in Question.objects.filter(section__exam=exam):
            if question.question_type in self._GRADABLE_TYPES:
                if question.correct_answer.strip():
                    answers[question.id] = question.correct_answer
            elif question.question_type == 'writing_task':
                answers[question.id] = question.model_answer.strip() or (
                    "This is a demo answer used only to verify the AI grading pipeline. " * 40
                )
        return JsonResponse(answers)


def create_result(user, exam, answers):
    """Grades `answers` ({question_id: raw answer}) and saves them as a new
    UserResult. Used by the student's own submit and by staff turning an
    unsent autosaved attempt into a result."""
    section_stats = {}
    # writing_tasks: list of (order, text) — preserves Task1/Task2 order
    writing_tasks = []
    total_correct = 0
    total_questions = 0

    # Fetch sections once and reuse
    sections = list(exam.sections.prefetch_related('questions').order_by('order'))
    if not settings.SPEAKING_ENABLED:
        sections = [s for s in sections if s.section_type != 'speaking']

    # (question, user_answer, is_correct) captured here so the second
    # pass building UserAnswer rows can reuse it instead of recomputing
    # _fuzzy_match for every question again.
    answer_records = []

    for section in sections:
        s_correct = 0
        s_total = 0
        questions = list(section.questions.all())
        verdicts = grade_answers(questions, lambda q: answers.get(str(q.id), ''))
        for question in questions:
            user_ans = str(answers.get(str(question.id), '')).strip()
            if question.question_type == 'writing_task':
                writing_tasks.append({
                    'order': section.order,
                    'section_title': section.title,
                    'text': user_ans,
                })
                answer_records.append((question, user_ans, False))
                continue
            s_total += 1
            total_questions += 1
            is_correct = verdicts[question.id]
            answer_records.append((question, user_ans, is_correct))
            if is_correct:
                s_correct += 1
                total_correct += 1
        prev_c, prev_t = section_stats.get(section.section_type, (0, 0))
        section_stats[section.section_type] = (prev_c + s_correct, prev_t + s_total)

    def get_band(stype):
        c, t = section_stats.get(stype, (0, 0))
        return calc_band(c, t)

    l_band = get_band('listening')
    r_band = get_band('reading')
    s_band = get_band('speaking')

    # Writing is graded by staff by hand (panel → Natijalar → Baholash),
    # so the overall band can't exist yet: the result is held back as
    # "pending" and only released once the writing band is filled in.
    pending = bool(writing_tasks)
    if pending:
        overall = 0.0
    else:
        band_by_type = {'listening': l_band, 'reading': r_band, 'writing': 0.0, 'speaking': s_band}
        overall = compute_overall_band(band_by_type, present_section_types(exam))

    result = UserResult.objects.create(
        user=user,
        exam=exam,
        score=overall,
        listening_score=l_band,
        reading_score=r_band,
        writing_score=0.0,
        speaking_score=s_band,
        status=UserResult.STATUS_PENDING if pending else UserResult.STATUS_GRADED,
    )

    answer_objs = [
        UserAnswer(result=result, question=question, user_answer=user_ans, is_correct=is_correct)
        for question, user_ans, is_correct in answer_records
    ]
    UserAnswer.objects.bulk_create(answer_objs, ignore_conflicts=True)

    return result


def submit_payload(result):
    if result.is_pending:
        # No bands in the response — they'd leak the partial result
        # before the writing is graded.
        return {'status': 'success', 'result_id': result.id, 'pending': True}
    return {
        'status': 'success',
        'result_id': result.id,
        'score': result.score,
        'listening': result.listening_score,
        'reading': result.reading_score,
        'writing': result.writing_score,
        'speaking': result.speaking_score,
    }


def _count_answered(answers):
    return sum(1 for v in answers.values() if str(v).strip())


def _int(value, low=0, high=10**7):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return None


def save_attempt(user, exam, client_id, answers=None, section='', meta=None, ip=None):
    """Upserts the server-side copy of an attempt. `answers=None` is a
    heartbeat (nothing changed). `meta` carries the page's live details
    (time_left, leave_count, away_seconds, pasted_chars). A submitted
    attempt is never overwritten — a late autosave must not clobber what
    was graded."""
    attempt, created = ExamAttempt.objects.get_or_create(user=user, exam=exam, client_id=client_id)
    if attempt.is_submitted:
        return attempt
    fields = ['last_seen_at']
    attempt.last_seen_at = timezone.now()
    if answers is not None:
        attempt.answers = answers
        attempt.answered_count = _count_answered(answers)
        fields += ['answers', 'answered_count']
    if section:
        attempt.current_section = section
        fields.append('current_section')
    if ip:
        attempt.ip = ip
        fields.append('ip')
    meta = meta or {}
    if 'time_left' in meta:
        attempt.time_left = _int(meta['time_left'])
        fields.append('time_left')
    # Counters only grow: a reload that lost the page's local copy must not
    # wipe what was already reported.
    for name in ('leave_count', 'away_seconds', 'pasted_chars'):
        value = _int(meta.get(name))
        if value is not None and value > getattr(attempt, name):
            setattr(attempt, name, value)
            fields.append(name)
    attempt.save(update_fields=fields)
    return attempt


def finalize_attempt(attempt):
    """Grades an attempt's answers into a result and marks it submitted."""
    with transaction.atomic():
        result = create_result(attempt.user, attempt.exam, attempt.answers)
        attempt.result = result
        attempt.submitted_at = timezone.now()
        attempt.last_error = ''
        attempt.save(update_fields=['result', 'submitted_at', 'last_error'])
    return result


class ExamAutosaveView(LoginRequiredMixin, View):
    """Periodic copy of the exam page's answers and live details, so they
    survive a failed submit or a cleared browser and staff can follow the
    exam live. The reply carries staff commands (messages, extra time) and
    tells the page if staff already finalized the attempt."""

    def post(self, request, *args, **kwargs):
        exam = get_object_or_404(Exam, pk=kwargs['pk'])
        data, err = parse_json_body(request)
        if err:
            return err
        client_id = str(data.get('attempt_id') or '')[:64]
        answers = data.get('answers')
        if not client_id or not (answers is None or isinstance(answers, dict)):
            return JsonResponse({'error': "Noto'g'ri so'rov"}, status=400)
        meta = data.get('meta') if isinstance(data.get('meta'), dict) else {}
        attempt = save_attempt(request.user, exam, client_id, answers, str(data.get('section') or '')[:20],
                               meta, get_client_ip(request))
        return JsonResponse({
            'ok': True,
            'submitted': attempt.is_submitted,
            'result_id': attempt.result_id,
            'commands': attempt.commands,
        })


class CameraFrameView(LoginRequiredMixin, View):
    """One webcam frame (raw JPEG body) from the exam page. The reply says
    how soon to send the next one — every second while staff are watching
    this student, otherwise every few seconds."""

    def post(self, request, *args, **kwargs):
        client_id = request.headers.get('X-Attempt-Id', '')
        data = request.body
        if not client_id or len(data) > camera.MAX_FRAME_BYTES or not camera.looks_like_jpeg(data):
            return JsonResponse({'error': "Noto'g'ri kadr"}, status=400)
        exam_pk = kwargs['pk']
        camera.store_frame(request.user.pk, exam_pk, client_id, data)
        return JsonResponse({
            'interval': camera.next_interval_ms(request.user.pk, exam_pk, client_id),
            # Staff watching this student: the live video calls to keep up,
            # and whether to also send relayed clips.
            'live': camera.live_sessions(request.user.pk, exam_pk, client_id),
            'relay': camera.relay_requested(request.user.pk, exam_pk, client_id),
        })


class CameraClipView(LoginRequiredMixin, View):
    """A 2-second webcam clip (raw WebM body) for staff watching over the
    relay. The reply says whether they still are."""

    def post(self, request, *args, **kwargs):
        client_id = request.headers.get('X-Attempt-Id', '')
        try:
            seq = int(request.headers.get('X-Clip-Seq', ''))
        except ValueError:
            seq = 0
        content_type = request.content_type or ''
        data = request.body
        if (not client_id or seq <= 0 or not content_type.startswith('video/') or not data
                or len(data) > camera.MAX_CLIP_BYTES):
            return JsonResponse({'error': "Noto'g'ri klip"}, status=400)
        full_type = request.META.get('CONTENT_TYPE', content_type)[:100]
        camera.store_clip(request.user.pk, kwargs['pk'], client_id, seq, data, full_type)
        return JsonResponse({'relay': camera.relay_requested(request.user.pk, kwargs['pk'], client_id)})


class CameraLiveView(LoginRequiredMixin, View):
    """The student's side of the live video call signalling: POST the
    connection offer, GET (poll) staff's answer."""

    def post(self, request, *args, **kwargs):
        data, err = parse_json_body(request)
        if err:
            return err
        client_id, session_id = str(data.get('attempt_id') or ''), str(data.get('session') or '')
        sdp = data.get('sdp')
        if (not client_id or not session_id or not isinstance(sdp, str) or len(sdp) > camera.MAX_SDP_CHARS
                or not camera.is_live_session(request.user.pk, kwargs['pk'], client_id, session_id)):
            return JsonResponse({'error': "Noto'g'ri so'rov"}, status=400)
        camera.put_sdp('offer', request.user.pk, kwargs['pk'], client_id, session_id, sdp)
        return JsonResponse({'ok': True})

    def get(self, request, *args, **kwargs):
        answer = camera.get_sdp('answer', request.user.pk, kwargs['pk'],
                                request.GET.get('attempt_id', ''), request.GET.get('session', ''))
        return JsonResponse({'answer': answer})


class SubmitExamView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            return self._post(request, *args, **kwargs)
        except Exception as e:
            # The answers go into logs/errors.log too, so a submit that keeps
            # failing can still be recovered by hand from the server side.
            submit_logger.exception(
                'Exam submit failed: user=%s exam=%s body=%s',
                request.user.pk, kwargs.get('pk'), request.body[:200_000].decode('utf-8', 'replace'),
            )
            attempt = getattr(request, '_exam_attempt', None)
            if attempt is not None:
                ExamAttempt.objects.filter(pk=attempt.pk).update(last_error=f'{type(e).__name__}: {e}'[:1000])
            if request.user.is_superuser:
                import traceback
                return JsonResponse({'error': traceback.format_exc()}, status=500)
            return JsonResponse({'error': "Xatolik yuz berdi. Qayta urinib ko'ring."}, status=500)

    def _post(self, request, *args, **kwargs):
        exam = get_object_or_404(Exam, pk=kwargs['pk'])
        data, err = parse_json_body(request)
        if err:
            return err
        answers = data.get('answers', {})

        # The answers are stored before grading (outside its transaction),
        # so they're on the server even if grading below blows up.
        attempt = None
        client_id = str(data.get('attempt_id') or '')[:64]
        if client_id and isinstance(answers, dict):
            try:
                attempt = save_attempt(request.user, exam, client_id, answers, 'finished')
            except Exception:
                # The server-side copy is a safety net — never let it stand
                # between the student and their graded result.
                submit_logger.exception('Saving attempt before submit failed: user=%s exam=%s',
                                        request.user.pk, exam.pk)
            else:
                request._exam_attempt = attempt
            # A retry whose first try went through (only the reply got lost),
            # or an attempt staff already finalized from the panel: hand back
            # that result instead of creating a second one — or hitting the
            # paid check, which the first submit already cleared.
            if attempt is not None and attempt.is_submitted and attempt.result_id:
                return JsonResponse(submit_payload(attempt.result))

        if exam.price > 0 and not exam_is_paid(request.user.pk, exam.pk):
            return JsonResponse({'error': "Bu imtihon uchun to'lov amalga oshirilmagan"}, status=402)

        if attempt is not None:
            result = finalize_attempt(attempt)
        else:
            with transaction.atomic():
                result = create_result(request.user, exam, answers)
        clear_exam_paid(request.user.pk, exam.pk)
        clear_exam_unlocked(request.user.pk, exam.pk)
        return JsonResponse(submit_payload(result))


class ResultDetailView(LoginRequiredMixin, DetailView):
    model = UserResult
    template_name = 'exams/result_detail.html'
    context_object_name = 'result'

    def get_queryset(self):
        qs = UserResult.objects.select_related('exam')
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        result = self.object

        db_answers = {
            str(ua.question_id): ua.user_answer
            for ua in result.answers.select_related('question').all()
            if ua.question_id
        }
        if not db_answers:
            db_answers = self.request.session.get(f'exam_answers_{result.exam.pk}', {})

        sections_data = []
        for section in result.exam.sections.prefetch_related('questions').all():
            questions_data = []
            correct_count = 0
            questions = list(section.questions.all())
            verdicts = grade_answers(questions, lambda q: db_answers.get(str(q.id), ''))
            for q in questions:
                user_ans = str(db_answers.get(str(q.id), '')).strip()
                if q.question_type in ('writing_task', 'short_answer'):
                    is_correct = None
                else:
                    is_correct = verdicts[q.id]
                    if is_correct:
                        correct_count += 1
                questions_data.append({
                    'order': q.order,
                    'text': q.text,
                    'question_type': q.question_type,
                    'user_answer': user_ans,
                    'is_correct': is_correct,
                    'word_limit': q.word_limit,
                })
            section.correct = correct_count
            section.total = len([q for q in questions_data if q['question_type'] not in ('writing_task', 'short_answer')])
            sections_data.append((section, questions_data))

        context['sections_data'] = sections_data
        context['band_label'] = band_label(result.score)
        context['prev_results'] = UserResult.objects.graded().filter(
            user=result.user, exam=result.exam
        ).order_by('completed_at')
        context['hide_result'] = result.is_pending and not self.request.user.is_staff
        return context


class SpeakingEvalView(LoginRequiredMixin, View):
    """
    POST: receives audio blob + result_id + question_id
          → Whisper transcription → GPT evaluation
          → saves speaking_feedback to UserResult
    """
    # Canned transcript for the superuser-only demo path — lets QA verify
    # the speaking grading pipeline without recording real audio.
    _DEMO_TRANSCRIPT = (
        "This is a demo spoken response used only to verify the AI grading pipeline. "
        "In a real answer I would speak fluently, use a good range of vocabulary and "
        "accurate grammar, and give specific reasons and examples to support my point of view."
    )

    def post(self, request, *args, **kwargs):
        from core.ai_utils import transcribe_audio, evaluate_speaking

        result_id = request.POST.get('result_id')
        question_id = request.POST.get('question_id', '')
        audio_file = request.FILES.get('audio')
        is_demo = request.POST.get('demo') == '1'

        if is_demo and not request.user.is_superuser:
            return JsonResponse({'error': "Ruxsat yo'q"}, status=403)
        if not is_demo and not audio_file:
            return JsonResponse({'error': 'Audio fayl topilmadi'}, status=400)
        if not result_id:
            return JsonResponse({'error': 'result_id talab qilinadi'}, status=400)
        if audio_file:
            if audio_file.size > 25 * 1024 * 1024:
                return JsonResponse({'error': 'Audio fayl hajmi 25MB dan oshmasligi kerak'}, status=400)
            allowed_audio_types = {'audio/webm', 'audio/mp4', 'audio/mpeg', 'audio/ogg', 'audio/wav'}
            if audio_file.content_type not in allowed_audio_types:
                return JsonResponse({'error': 'Noto\'g\'ri audio format'}, status=400)

        try:
            result = UserResult.objects.get(pk=result_id, user=request.user)
        except UserResult.DoesNotExist:
            return JsonResponse({'error': 'Natija topilmadi'}, status=404)

        # Question text for better context
        question_text = ''
        if question_id:
            try:
                question_text = Question.objects.get(pk=question_id).text
            except Question.DoesNotExist:
                pass

        if is_demo:
            transcript = self._DEMO_TRANSCRIPT
        else:
            audio_bytes = audio_file.read()
            filename = audio_file.name or 'audio.webm'
            transcript = transcribe_audio(audio_bytes, filename)

        feedback = evaluate_speaking(transcript, question=question_text)

        # Merge with existing speaking_feedback — replace by question_id if re-submitted
        existing = result.speaking_feedback or []
        if isinstance(existing, dict):
            # A teacher-entered (panel) speaking grade is a single dict, not
            # per-question entries — the online recording replaces it.
            existing = [] if existing.get('manual') else list(existing.values())
        existing = [e for e in existing if str(e.get('question_id', '')) != str(question_id)]
        existing.append({
            'question_id': question_id,
            'question_text': question_text,
            **feedback,
        })

        # Overall speaking band = average of all evaluated questions
        all_bands = [e['band'] for e in existing if 'band' in e]
        if all_bands:
            avg = sum(all_bands) / len(all_bands)
            overall_band = round(avg * 2) / 2
            result.speaking_score = overall_band

        result.speaking_feedback = existing

        band_by_type = {
            'listening': result.listening_score, 'reading': result.reading_score,
            'writing': result.writing_score, 'speaking': result.speaking_score,
        }
        result.score = compute_overall_band(band_by_type, present_section_types(result.exam))
        result.save(update_fields=['speaking_feedback', 'speaking_score', 'score'])

        return JsonResponse({
            'status': 'ok',
            'transcript': transcript,
            'band': feedback['band'],
            'feedback': feedback['feedback'],
            'fluency': feedback['fluency_coherence'],
            'lexical': feedback['lexical_resource'],
            'grammar': feedback['grammatical_range'],
        })
