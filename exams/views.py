from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView
import json

from .models import Exam, UserAnswer, UserResult
from users.models import User


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
        if exam.price > 0 and not request.session.get(f'exam_paid_{exam.pk}'):
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.user.pk)
                if user.balance < exam.price:
                    messages.error(request, f"Balans yetarli emas. Imtihon narxi: {exam.price} so'm")
                    return redirect('exams:exam_detail', pk=exam.pk)
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
        writing_texts = {}
        total_correct = 0
        total_questions = 0

        # Fetch sections once and reuse
        sections = list(exam.sections.prefetch_related('questions').all())

        for section in sections:
            s_correct = 0
            s_total = 0
            for question in section.questions.all():
                user_ans = str(answers.get(str(question.id), '')).strip()
                if question.question_type == 'writing_task':
                    writing_texts.setdefault(section.section_type, []).append(user_ans)
                    continue
                s_total += 1
                total_questions += 1
                correct = str(question.correct_answer).strip().lower()
                if user_ans.lower() == correct:
                    s_correct += 1
                    total_correct += 1
            prev_c, prev_t = section_stats.get(section.section_type, (0, 0))
            section_stats[section.section_type] = (prev_c + s_correct, prev_t + s_total)

        def get_band(stype):
            if stype == 'writing' and writing_texts.get('writing'):
                return calc_writing_band(' '.join(writing_texts['writing']))
            c, t = section_stats.get(stype, (0, 0))
            return calc_band(c, t)

        l_band = get_band('listening')
        r_band = get_band('reading')
        w_band = get_band('writing')
        s_band = get_band('speaking')

        active_bands = [b for b in [l_band, r_band, w_band, s_band] if b > 0]
        overall = round(sum(active_bands) / len(active_bands) * 2) / 2 if active_bands else 0.0

        request.session.pop(f'exam_paid_{exam.pk}', None)

        result = UserResult.objects.create(
            user=request.user,
            exam=exam,
            score=overall,
            listening_score=l_band,
            reading_score=r_band,
            writing_score=w_band,
            speaking_score=s_band,
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
