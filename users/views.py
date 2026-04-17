from django.shortcuts import render, redirect
from django.views.generic import TemplateView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as BaseLoginView
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.utils import timezone
from .forms import RegisterForm


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


class CustomLoginView(BaseLoginView):
    template_name = 'login.html'

    def form_valid(self, response):
        from .models import LoginLog
        ip = get_client_ip(self.request)
        ua = self.request.META.get('HTTP_USER_AGENT', '')[:300]
        user = self.request.user if self.request.user.is_authenticated else None
        # clear fail counter
        cache.delete(f'login_fail_{ip}')
        # save last ip
        if self.request.user.is_authenticated:
            self.request.user.last_ip = ip
            self.request.user.save(update_fields=['last_ip'])
        LoginLog.objects.create(
            user=self.get_form().get_user(),
            username_attempt=self.request.POST.get('username', ''),
            ip=ip, user_agent=ua, status='success'
        )
        return super().form_valid(response)

    def form_invalid(self, form):
        from .models import LoginLog
        ip = get_client_ip(self.request)
        ua = self.request.META.get('HTTP_USER_AGENT', '')[:300]
        username = self.request.POST.get('username', '')

        # brute force: 5 urinishdan keyin 15 daqiqa blok
        key = f'login_fail_{ip}'
        fails = cache.get(key, 0) + 1
        cache.set(key, fails, timeout=900)

        status = 'blocked' if fails >= 5 else 'failed'
        LoginLog.objects.create(
            username_attempt=username, ip=ip,
            user_agent=ua, status=status
        )
        return super().form_invalid(form)

    def get(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        fails = cache.get(f'login_fail_{ip}', 0)
        if fails >= 5:
            from django.http import HttpResponse
            return HttpResponse(
                '<h2 style="font-family:sans-serif;text-align:center;margin-top:80px">⛔ Juda ko\'p urinish. 15 daqiqadan keyin qayta urinib ko\'ring.</h2>',
                status=429
            )
        return super().get(request, *args, **kwargs)


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = 'register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.last_ip = get_client_ip(self.request)
        user.save()
        return super().form_valid(form)


class HomeView(TemplateView):
    template_name = 'home.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().get(request, *args, **kwargs)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        from exams.models import UserResult
        from django.db.models import Avg, Count
        from datetime import timedelta
        import json
        context = super().get_context_data(**kwargs)
        user = self.request.user
        results = UserResult.objects.filter(user=user).order_by('-completed_at')

        context['recent_results'] = results[:3]
        context['stats'] = results.aggregate(avg_score=Avg('score'), total_tests=Count('id'))

        # Last 8 results for progress chart
        chart_results = list(results[:8][::-1])
        context['chart_labels'] = json.dumps([r.completed_at.strftime('%d %b') for r in chart_results])
        context['chart_scores'] = json.dumps([r.score for r in chart_results])
        context['chart_listening'] = json.dumps([r.listening_score for r in chart_results])
        context['chart_reading'] = json.dumps([r.reading_score for r in chart_results])

        # Section averages
        avgs = results.aggregate(
            avg_l=Avg('listening_score'), avg_r=Avg('reading_score'),
            avg_w=Avg('writing_score'), avg_s=Avg('speaking_score'),
        )
        context['section_avgs'] = avgs
        return context


class ExamsListView(LoginRequiredMixin, TemplateView):
    template_name = 'exams_list.html'

    def get_context_data(self, **kwargs):
        from exams.models import Exam, UserResult
        from django.db.models import Count
        context = super().get_context_data(**kwargs)
        exams = Exam.objects.filter(is_active=True).prefetch_related('sections__questions').order_by('-created_at')
        # annotate total questions
        for exam in exams:
            exam.total_questions = sum(s.questions.count() for s in exam.sections.all())
        completed_ids = set(
            UserResult.objects.filter(user=self.request.user).values_list('exam_id', flat=True)
        )
        context['exams'] = exams
        context['completed_ids'] = completed_ids
        return context


class ResultsListView(LoginRequiredMixin, TemplateView):
    template_name = 'results_list.html'

    def get_context_data(self, **kwargs):
        from exams.models import UserResult
        from django.db.models import Avg, Count
        context = super().get_context_data(**kwargs)
        results = UserResult.objects.filter(user=self.request.user).order_by('-completed_at')
        context['results'] = results
        full_stats = results.aggregate(
            avg_score=Avg('score'), total_tests=Count('id'),
            avg_listening=Avg('listening_score'), avg_reading=Avg('reading_score'),
            avg_writing=Avg('writing_score'), avg_speaking=Avg('speaking_score'),
        )
        if full_stats['avg_score']:
            full_stats['avg_score_percentage'] = round(float(full_stats['avg_score']) / 9 * 100, 1)
        else:
            full_stats['avg_score_percentage'] = 0
        context['stats'] = full_stats
        return context


class VocabularyView(LoginRequiredMixin, TemplateView):
    template_name = 'vocabulary.html'

    def get_context_data(self, **kwargs):
        from .models import Vocabulary
        context = super().get_context_data(**kwargs)
        context['words'] = Vocabulary.objects.filter(user=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        from .models import Vocabulary
        action = request.POST.get('action')
        if action == 'delete':
            Vocabulary.objects.filter(id=request.POST.get('word_id'), user=request.user).delete()
            return JsonResponse({'status': 'deleted'})
        english = request.POST.get('english')
        translation = request.POST.get('translation')
        if english and translation:
            Vocabulary.objects.create(user=request.user, english=english, translation=translation)
        return redirect('vocabulary')


class FinanceView(LoginRequiredMixin, TemplateView):
    template_name = 'finance.html'

    def get_context_data(self, **kwargs):
        from payments.models import Transaction
        context = super().get_context_data(**kwargs)
        context['transactions'] = Transaction.objects.filter(user=self.request.user)
        return context


@method_decorator(csrf_exempt, name='dispatch')
class ChatAIView(LoginRequiredMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        import json
        from core.ai_utils import get_ai_response
        data = json.loads(request.body)
        message = data.get('message')
        history = data.get('history', [])
        if not message:
            return JsonResponse({'error': 'Xabar topilmadi'}, status=400)
        return JsonResponse({'response': get_ai_response(message, history)})


class AnalyticsView(LoginRequiredMixin, TemplateView):
    template_name = 'analytics.html'

    def get_context_data(self, **kwargs):
        import json
        from exams.models import UserResult, Exam
        from django.db.models import Avg, Count, Max, Min
        from datetime import timedelta
        context = super().get_context_data(**kwargs)
        user = self.request.user
        results = UserResult.objects.filter(user=user).select_related('exam').order_by('completed_at')

        # Umumiy statistika
        stats = results.aggregate(
            total=Count('id'), avg=Avg('score'),
            best=Max('score'), worst=Min('score'),
            avg_l=Avg('listening_score'), avg_r=Avg('reading_score'),
            avg_w=Avg('writing_score'), avg_s=Avg('speaking_score'),
        )
        context['stats'] = stats

        # Progress over time (barcha natijalar)
        context['chart_dates'] = json.dumps([r.completed_at.strftime('%d %b %Y') for r in results])
        context['chart_scores'] = json.dumps([r.score for r in results])
        context['chart_l'] = json.dumps([r.listening_score for r in results])
        context['chart_r'] = json.dumps([r.reading_score for r in results])
        context['chart_w'] = json.dumps([r.writing_score for r in results])
        context['chart_s'] = json.dumps([r.speaking_score for r in results])

        # Imtihon turlari bo'yicha
        by_type = results.values('exam__exam_type').annotate(cnt=Count('id'), avg=Avg('score')).order_by('-cnt')
        context['by_type'] = list(by_type)
        context['chart_type_labels'] = json.dumps([b['exam__exam_type'] for b in by_type])
        context['chart_type_counts'] = json.dumps([b['cnt'] for b in by_type])
        context['chart_type_avgs'] = json.dumps([round(b['avg'] or 0, 1) for b in by_type])

        # Oylik faollik (so'nggi 6 oy)
        now = timezone.now()
        monthly = []
        monthly_labels = []
        for i in range(5, -1, -1):
            month_start = (now.replace(day=1) - timedelta(days=i*30)).replace(day=1, hour=0, minute=0, second=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1)
            cnt = results.filter(completed_at__gte=month_start, completed_at__lt=month_end).count()
            monthly.append(cnt)
            monthly_labels.append(month_start.strftime('%b %Y'))
        context['chart_monthly_labels'] = json.dumps(monthly_labels)
        context['chart_monthly'] = json.dumps(monthly)

        # Band score taqsimoti
        bands = {'4.0-5.0': 0, '5.5-6.0': 0, '6.5-7.0': 0, '7.5-8.0': 0, '8.5-9.0': 0}
        for r in results:
            if r.score <= 5.0: bands['4.0-5.0'] += 1
            elif r.score <= 6.0: bands['5.5-6.0'] += 1
            elif r.score <= 7.0: bands['6.5-7.0'] += 1
            elif r.score <= 8.0: bands['7.5-8.0'] += 1
            else: bands['8.5-9.0'] += 1
        context['chart_band_labels'] = json.dumps(list(bands.keys()))
        context['chart_band_data'] = json.dumps(list(bands.values()))

        # So'nggi 5 natija
        context['recent_results'] = list(results.order_by('-completed_at')[:5])

        # Eng yaxshi va eng yomon imtihon
        context['best_result'] = results.order_by('-score').first()
        context['worst_result'] = results.order_by('score').first()

        return context


class ProfileView(LoginRequiredMixin, View):
    def get(self, request):
        from exams.models import UserResult
        from django.db.models import Avg, Count
        results = UserResult.objects.filter(user=request.user).order_by('-completed_at')
        stats = results.aggregate(avg_score=Avg('score'), total_tests=Count('id'))
        return render(request, 'users/profile.html', {
            'recent_results': results[:5],
            'stats': stats,
        })

    def post(self, request):
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.phone_number = request.POST.get('phone_number', user.phone_number)
        user.bio = request.POST.get('bio', user.bio)
        if 'avatar' in request.FILES:
            user.avatar = request.FILES['avatar']
        user.save()
        return redirect('profile')
