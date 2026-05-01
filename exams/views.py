from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView
import json

from .models import Exam, UserAnswer, UserResult, Question
from users.models import User


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


def calc_writing_band(text):
    """Minimal writing band based on word count (Task 2 baseline)."""
    words = len(text.split()) if text else 0
    if words >= 350: return 7.0
    if words >= 300: return 6.5
    if words >= 250: return 6.0
    if words >= 200: return 5.5
    if words >= 150: return 5.0
    if words >= 100: return 4.5
    return 4.0


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
        return context


class TakeExamView(LoginRequiredMixin, DetailView):
    model = Exam
    template_name = 'exams/take_exam.html'
    context_object_name = 'exam'

    def get(self, request, *args, **kwargs):
        exam = self.get_object()
        if not exam.is_active:
            messages.error(request, "Bu imtihon hozirda faol emas.")
            return redirect('exams:exam_detail', pk=exam.pk)
        if exam.price > 0 and not request.session.get(f'exam_paid_{exam.pk}'):
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.user.pk)
                # Re-check session inside the lock to prevent double-charge on concurrent requests
                if request.session.get(f'exam_paid_{exam.pk}'):
                    pass
                elif user.balance < exam.price:
                    messages.error(request, f"Balans yetarli emas. Imtihon narxi: {exam.price} so'm")
                    return redirect('exams:exam_detail', pk=exam.pk)
                else:
                    user.balance -= exam.price
                    user.save(update_fields=['balance'])
                    request.user.balance = user.balance
                    request.session[f'exam_paid_{exam.pk}'] = True
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sections'] = self.object.sections.prefetch_related('questions').all()
        return context


class SubmitExamView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        exam = get_object_or_404(Exam, pk=kwargs['pk'])
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Noto\'g\'ri so\'rov'}, status=400)

        answers = data.get('answers', {})
        section_stats = {}
        # writing_tasks: list of (order, text) — preserves Task1/Task2 order
        writing_tasks = []
        total_correct = 0
        total_questions = 0

        # Fetch sections once and reuse
        sections = list(exam.sections.prefetch_related('questions').order_by('order'))

        for section in sections:
            s_correct = 0
            s_total = 0
            for question in section.questions.all():
                user_ans = str(answers.get(str(question.id), '')).strip()
                if question.question_type == 'writing_task':
                    writing_tasks.append({
                        'order': section.order,
                        'section_title': section.title,
                        'text': user_ans,
                    })
                    continue
                s_total += 1
                total_questions += 1
                correct = str(question.correct_answer).strip().lower()
                if _fuzzy_match(user_ans, correct):
                    s_correct += 1
                    total_correct += 1
            prev_c, prev_t = section_stats.get(section.section_type, (0, 0))
            section_stats[section.section_type] = (prev_c + s_correct, prev_t + s_total)

        # AI Writing evaluation — Task 1 and Task 2 separately
        writing_feedback = None
        if writing_tasks:
            from core.ai_utils import evaluate_writing
            task_feedbacks = []
            for task in writing_tasks:
                task_num = len(task_feedbacks) + 1
                fb = evaluate_writing(task['text'], task_num=task_num)
                fb['task_num'] = task_num
                fb['section_title'] = task['section_title']
                task_feedbacks.append(fb)
            if task_feedbacks:
                avg_band = sum(fb['band'] for fb in task_feedbacks) / len(task_feedbacks)
                writing_feedback = {
                    'band': round(avg_band * 2) / 2.0,
                    'tasks': task_feedbacks,
                    # top-level averages for backward compat
                    'task_achievement': sum(fb.get('task_achievement', fb['band']) for fb in task_feedbacks) / len(task_feedbacks),
                    'coherence_cohesion': sum(fb.get('coherence_cohesion', fb['band']) for fb in task_feedbacks) / len(task_feedbacks),
                    'lexical_resource': sum(fb.get('lexical_resource', fb['band']) for fb in task_feedbacks) / len(task_feedbacks),
                    'grammatical_accuracy': sum(fb.get('grammatical_accuracy', fb['band']) for fb in task_feedbacks) / len(task_feedbacks),
                    'ai_graded': any(fb.get('ai_graded') for fb in task_feedbacks),
                }

        def get_band(stype):
            if stype == 'writing':
                if writing_feedback:
                    return writing_feedback['band']
                if writing_tasks:
                    return calc_writing_band(' '.join(t['text'] for t in writing_tasks))
            c, t = section_stats.get(stype, (0, 0))
            return calc_band(c, t)

        l_band = get_band('listening')
        r_band = get_band('reading')
        w_band = get_band('writing')
        s_band = get_band('speaking')

        active_bands = [b for b in [l_band, r_band, w_band, s_band] if b > 0]
        overall = round(sum(active_bands) / len(active_bands) * 2) / 2.0 if active_bands else 0.0

        request.session.pop(f'exam_paid_{exam.pk}', None)

        result = UserResult.objects.create(
            user=request.user,
            exam=exam,
            score=overall,
            listening_score=l_band,
            reading_score=r_band,
            writing_score=w_band,
            speaking_score=s_band,
            writing_feedback=writing_feedback,
        )

        answer_objs = []
        for section in sections:
            for question in section.questions.all():
                user_ans = str(answers.get(str(question.id), '')).strip()
                is_correct = (
                    False if question.question_type == 'writing_task'
                    else user_ans.lower() == str(question.correct_answer).strip().lower()
                )
                answer_objs.append(UserAnswer(
                    result=result,
                    question=question,
                    user_answer=user_ans,
                    is_correct=is_correct,
                ))
        UserAnswer.objects.bulk_create(answer_objs, ignore_conflicts=True)

        return JsonResponse({
            'status': 'success',
            'result_id': result.id,
            'score': result.score,
            'listening': result.listening_score,
            'reading': result.reading_score,
            'writing': result.writing_score,
            'speaking': result.speaking_score,
        })


class ResultDetailView(LoginRequiredMixin, DetailView):
    model = UserResult
    template_name = 'exams/result_detail.html'
    context_object_name = 'result'

    def get_queryset(self):
        return UserResult.objects.filter(user=self.request.user).select_related('exam')

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
            for q in section.questions.all():
                user_ans = str(db_answers.get(str(q.id), '')).strip()
                correct = str(q.correct_answer).strip().lower()
                if q.question_type == 'writing_task':
                    is_correct = None
                else:
                    is_correct = user_ans.lower() == correct
                    if is_correct:
                        correct_count += 1
                questions_data.append({
                    'order': q.order,
                    'text': q.text,
                    'question_type': q.question_type,
                    'user_answer': user_ans,
                    'correct_answer': q.correct_answer,
                    'explanation': q.explanation,
                    'is_correct': is_correct,
                    'word_limit': q.word_limit,
                })
            section.correct = correct_count
            section.total = len([q for q in questions_data if q['question_type'] != 'writing_task'])
            sections_data.append((section, questions_data))

        context['sections_data'] = sections_data
        context['band_label'] = band_label(result.score)
        context['prev_results'] = UserResult.objects.filter(
            user=self.request.user, exam=result.exam
        ).order_by('completed_at')
        return context


class SpeakingEvalView(LoginRequiredMixin, View):
    """
    POST: receives audio blob + result_id + question_id
          → Whisper transcription → GPT evaluation
          → saves speaking_feedback to UserResult
    """
    def post(self, request, *args, **kwargs):
        from core.ai_utils import transcribe_audio, evaluate_speaking

        result_id = request.POST.get('result_id')
        question_id = request.POST.get('question_id', '')
        audio_file = request.FILES.get('audio')

        if not audio_file:
            return JsonResponse({'error': 'Audio fayl topilmadi'}, status=400)
        if not result_id:
            return JsonResponse({'error': 'result_id talab qilinadi'}, status=400)
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

        audio_bytes = audio_file.read()
        filename = audio_file.name or 'audio.webm'

        transcript = transcribe_audio(audio_bytes, filename)
        feedback = evaluate_speaking(transcript, question=question_text)

        # Merge with existing speaking_feedback — replace by question_id if re-submitted
        existing = result.speaking_feedback or []
        if isinstance(existing, dict):
            existing = list(existing.values())
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
        result.save(update_fields=['speaking_feedback', 'speaking_score'])

        return JsonResponse({
            'status': 'ok',
            'transcript': transcript,
            'band': feedback['band'],
            'feedback': feedback['feedback'],
            'fluency': feedback['fluency_coherence'],
            'lexical': feedback['lexical_resource'],
            'grammar': feedback['grammatical_range'],
        })
