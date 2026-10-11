from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core.utils import parse_json_body
from users.models import Vocabulary
from . import ai, srs
from .content import LEVELS, get_course, get_lesson
from .models import LessonProgress
from .services import (
    REVIEW_XP, TUTOR_XP, award_xp, complete_lesson, get_profile,
    recommended_level, today_xp, week_activity,
)

TUTOR_DAILY_LIMIT = 60
WRITE_DAILY_LIMIT = 30
DAILY_GOALS = (10, 20, 30, 50)


def _ai_quota_left(user, kind, limit):
    """Count one AI call against a per-user daily cap; False once it's used up."""
    key = f'learn_ai_{kind}_{user.pk}_{timezone.localdate():%Y%m%d}'
    used = cache.get(key, 0)
    if used >= limit:
        return False
    cache.set(key, used + 1, 60 * 60 * 26)
    return True


def _done_map(user):
    return dict(LessonProgress.objects.filter(user=user).values_list('lesson_slug', 'best_score'))


def _is_unlocked(lesson, done):
    return lesson['slug'] in done or not lesson.get('prev_slug') or lesson['prev_slug'] in done


class HubView(LoginRequiredMixin, TemplateView):
    template_name = 'learn/hub.html'

    def get(self, request, *args, **kwargs):
        profile = get_profile(request.user)
        chosen = request.GET.get('level')
        if chosen in LEVELS and chosen != profile.level:
            profile.level = chosen
            profile.save(update_fields=['level'])
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        profile = get_profile(user)
        rec_level, rec_avg = recommended_level(user)
        level_code = profile.level or rec_level or 'A1'
        course = get_course()
        done = _done_map(user)

        level = course['levels'][level_code]
        current = None
        units = []
        for unit in level['units']:
            items = []
            for lesson in unit['lessons']:
                state = 'done' if lesson['slug'] in done else ('open' if _is_unlocked(lesson, done) else 'locked')
                if state == 'open' and current is None:
                    current = lesson
                    state = 'current'
                items.append({'lesson': lesson, 'state': state, 'score': done.get(lesson['slug'])})
            units.append({'unit': unit, 'items': items,
                          'done': sum(1 for i in items if i['state'] == 'done')})

        levels = []
        for code in LEVELS:
            lv = course['levels'][code]
            slugs = [l['slug'] for u in lv['units'] for l in u['lessons']]
            finished = sum(1 for s in slugs if s in done)
            levels.append({'code': code, 'name': lv['name'], 'ielts': lv['ielts'], 'desc': lv['desc'],
                           'total': len(slugs), 'done': finished,
                           'pct': round(finished * 100 / len(slugs)) if slugs else 0})

        xp_today = today_xp(user)
        goal_pct = min(100, round(xp_today * 100 / profile.daily_goal)) if profile.daily_goal else 100
        week = week_activity(user)
        for d in week:
            d['h'] = max(4, min(50, round(d['xp'] * 50 / profile.daily_goal))) if profile.daily_goal else 4
        ctx.update({
            'profile': profile,
            'level': level,
            'level_code': level_code,
            'levels': levels,
            'units': units,
            'current_lesson': current,
            'level_done': sum(u['done'] for u in units),
            'xp_today': xp_today,
            'goal_pct': goal_pct,
            # Stroke offset for the progress ring (circumference 2π·32 ≈ 201.06).
            'goal_offset': f'{201.06 * (1 - goal_pct / 100):.2f}',
            'week': week,
            'review': srs.review_counts(user),
            'rec_level': rec_level,
            'rec_avg': rec_avg,
            'daily_goals': DAILY_GOALS,
            'scenarios': ai.SCENARIOS,
        })
        return ctx


class GoalView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            goal = int(request.POST.get('goal', 0))
        except ValueError:
            goal = 0
        if goal in DAILY_GOALS:
            profile = get_profile(request.user)
            profile.daily_goal = goal
            profile.save(update_fields=['daily_goal'])
        return redirect('learn:hub')


class LessonView(LoginRequiredMixin, TemplateView):
    template_name = 'learn/lesson.html'

    def get(self, request, *args, **kwargs):
        lesson = get_lesson(kwargs['slug'])
        if not lesson:
            raise Http404
        if not _is_unlocked(lesson, _done_map(request.user)):
            messages.error(request, "Avval oldingi darsni tugating")
            return redirect(f"{reverse('learn:hub')}?level={lesson['level']}")
        self.lesson = lesson
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lesson = self.lesson
        ctx['lesson'] = lesson
        ctx['lesson_data'] = {
            'slug': lesson['slug'], 'level': lesson['level'], 'title': lesson['title'],
            'title_uz': lesson['title_uz'], 'words': lesson['words'], 'steps': lesson['steps'],
            'next_slug': lesson.get('next_slug'),
        }
        ctx['progress'] = LessonProgress.objects.filter(user=self.request.user, lesson_slug=lesson['slug']).first()
        return ctx


class LessonCompleteView(LoginRequiredMixin, View):
    def post(self, request, slug):
        lesson = get_lesson(slug)
        if not lesson:
            return JsonResponse({'error': 'Dars topilmadi'}, status=404)
        if not _is_unlocked(lesson, _done_map(request.user)):
            return JsonResponse({'error': 'Dars hali ochilmagan'}, status=403)
        data, err = parse_json_body(request)
        if err:
            return err
        try:
            score = int(data.get('score', 0))
        except (TypeError, ValueError):
            score = 0
        return JsonResponse({'ok': True, **complete_lesson(request.user, lesson, score)})


class WriteCheckView(LoginRequiredMixin, View):
    def post(self, request):
        data, err = parse_json_body(request)
        if err:
            return err
        lesson = get_lesson(data.get('slug', ''))
        try:
            step = lesson['steps'][int(data.get('step', -1))] if lesson else None
        except (IndexError, TypeError, ValueError):
            step = None
        text = str(data.get('text', '')).strip()
        if not step or step.get('type') != 'write':
            return JsonResponse({'error': "Topshiriq topilmadi"}, status=400)
        if len(text.split()) < 3:
            return JsonResponse({'error': "Kamida bir nechta gap yozing"}, status=400)
        if not _ai_quota_left(request.user, 'write', WRITE_DAILY_LIMIT):
            return JsonResponse({'error': "Bugungi AI tekshiruv limiti tugadi. Ertaga davom eting!"}, status=429)
        result = ai.check_writing(step.get('prompt') or step.get('prompt_uz', ''), text, lesson['level'])
        if result is None:
            return JsonResponse({'error': "AI hozir javob bermadi. Keyinroq urinib ko'ring."}, status=503)
        return JsonResponse({'ok': True, **result})


class ReviewView(LoginRequiredMixin, TemplateView):
    template_name = 'learn/review.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cards = srs.session_cards(self.request.user)
        ctx['cards'] = [{
            'id': c.id, 'en': c.english, 'uz': c.translation, 'ex': c.example,
            'new': c.due_at is None, 'reps': c.reps,
        } for c in cards]
        ctx['review'] = srs.review_counts(self.request.user)
        return ctx


class ReviewGradeView(LoginRequiredMixin, View):
    def post(self, request):
        data, err = parse_json_body(request)
        if err:
            return err
        try:
            card = Vocabulary.objects.get(pk=int(data.get('id')), user=request.user)
            grade = int(data.get('grade'))
        except (Vocabulary.DoesNotExist, TypeError, ValueError):
            return JsonResponse({'error': "So'z topilmadi"}, status=404)
        srs.schedule(card, grade).save(update_fields=['due_at', 'interval_days', 'ease', 'reps', 'lapses'])
        award_xp(request.user, REVIEW_XP)
        return JsonResponse({'ok': True, 'interval_days': card.interval_days,
                             'again': grade == srs.AGAIN})


class TutorView(LoginRequiredMixin, TemplateView):
    template_name = 'learn/tutor.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        profile = get_profile(self.request.user)
        key = self.request.GET.get('s', 'free')
        ctx['scenarios'] = ai.SCENARIOS
        ctx['scenario_key'] = key if key in ai.SCENARIOS else 'free'
        ctx['scenario'] = ai.SCENARIOS[ctx['scenario_key']]
        ctx['level_code'] = profile.level or recommended_level(self.request.user)[0] or 'B1'
        return ctx


class TutorSendView(LoginRequiredMixin, View):
    def post(self, request):
        data, err = parse_json_body(request)
        if err:
            return err
        message = str(data.get('message', '')).strip()
        if not message:
            return JsonResponse({'error': 'Xabar bo\'sh'}, status=400)
        if not _ai_quota_left(request.user, 'tutor', TUTOR_DAILY_LIMIT):
            return JsonResponse({'error': "Bugungi suhbat limiti tugadi. Ertaga davom etamiz!"}, status=429)
        level = get_profile(request.user).level or recommended_level(request.user)[0] or 'B1'
        result = ai.tutor_reply(data.get('scenario', 'free'), level, message, data.get('history'))
        if not result or not result['reply']:
            return JsonResponse({'error': "AI hozir javob bermadi. Qayta urinib ko'ring."}, status=503)
        award_xp(request.user, TUTOR_XP)
        return JsonResponse({'ok': True, **result})
