"""JSON API for the mobile app (mobile/ — Flutter).

Mounted at /api/learn/. The app signs in with username + password and then
sends `Authorization: Bearer <token>` on every call; cookies and CSRF are
not involved. Course logic lives in services.py and content.py, shared with
the website, so XP, unlocking and limits behave the same on both.
"""
import hashlib
import secrets
from datetime import timedelta
from functools import wraps

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.http import JsonResponse
from django.urls import path, reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from core.utils import get_client_ip, notify_admin_telegram, parse_json_body
from users.forms import RegisterForm
from users.models import LoginLog, Vocabulary
from users.views import _MAX_FAILS_PER_IP, _MAX_FAILS_PER_USER, _bump, _fail_keys, _login_blocked, delete_account
from . import ai, checkpoints, srs
from .gamification import badges, bump, daily_quests, open_chest
from .content import LEVEL_INFO, LEVELS, get_course, get_lesson, get_placement, get_stories, placement_level
from .models import ApiToken, AppRelease, LessonProgress, Mistake
from .services import (
    TUTOR_XP, apply_practice, award_xp, build_practice, clear_draft, complete_lesson, complete_story, get_draft,
    explain_step, get_profile, grade_review, leaderboard, recommended_level, record_mistakes, save_draft,
    today_xp, week_activity,
)
from .views import (
    DAILY_GOALS, EXPLAIN_DAILY_LIMIT, PRACTICE_PAID_DAILY, TUTOR_DAILY_LIMIT, WRITE_DAILY_LIMIT, _daily_quota_left,
    _done_map, _is_unlocked,
)

MAX_TOKENS_PER_USER = 10
REGISTER_PER_IP_HOURLY = 10
PRACTICE_TTL = 6 * 60 * 60


# ── auth plumbing ────────────────────────────────────────────────────────
def _hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


def _issue_token(user, request, data):
    key = secrets.token_urlsafe(32)
    ApiToken.objects.create(
        user=user, key_hash=_hash(key),
        device=str(data.get('device', ''))[:100],
        platform=str(data.get('platform', ''))[:40],
        app_version=str(data.get('app_version', ''))[:20],
        ip=get_client_ip(request),
        user_agent=request.headers.get('User-Agent', '')[:300],
    )
    stale = ApiToken.objects.filter(user=user).order_by('-created_at').values_list('pk', flat=True)[MAX_TOKENS_PER_USER:]
    ApiToken.objects.filter(pk__in=list(stale)).delete()
    return key


def _bearer(request):
    # Some Apache setups drop the Authorization header before it reaches
    # Django, so the app sends the token in X-Api-Token as well.
    header = request.headers.get('Authorization', '')
    if header.startswith('Bearer '):
        return header[7:].strip()
    return request.headers.get('X-Api-Token', '').strip()


def api(methods=('GET',), auth=True):
    """JSON endpoint: token auth (unless auth=False), method check, no CSRF."""
    def decorate(view):
        @csrf_exempt
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse({'error': 'Method not allowed'}, status=405)
            if auth:
                key = _bearer(request)
                token = ApiToken.objects.select_related('user').filter(key_hash=_hash(key)).first() if key else None
                if not token or not token.user.is_active:
                    return JsonResponse({'error': "Qaytadan kiring"}, status=401)
                now = timezone.now()
                if not token.last_used_at or now - token.last_used_at > timedelta(hours=1):
                    ApiToken.objects.filter(pk=token.pk).update(last_used_at=now, ip=get_client_ip(request))
                request.user = token.user
                request.api_token = token
            return view(request, *args, **kwargs)
        return wrapper
    return decorate


def _body(request):
    data, err = parse_json_body(request)
    if err:
        return None, err
    if not isinstance(data, dict):
        return None, JsonResponse({'error': "Noto'g'ri so'rov"}, status=400)
    return data, None


def _user_json(user):
    return {'id': user.pk, 'username': user.username, 'first_name': user.first_name, 'last_name': user.last_name}


@api(auth=False)
def health(request):
    # The app's hidden WebView opens this page to get past the hosting's
    # browser check (Imunify360); the marker tells it the real API answered.
    return JsonResponse({'ok': True, 'app': 'abexam-api'})


@api(methods=('POST',), auth=False)
def login(request):
    data, err = _body(request)
    if err:
        return err
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    ip = get_client_ip(request)
    ua = request.headers.get('User-Agent', '')[:300]
    if _login_blocked(ip, username):
        return JsonResponse({'error': "Juda ko'p noto'g'ri urinish. 15 daqiqadan keyin qayta urinib ko'ring."},
                            status=429)
    user = authenticate(request, username=username, password=password)
    if user is None:
        ip_key, user_key = _fail_keys(ip, username)
        user_fails, ip_fails = _bump(user_key), _bump(ip_key)
        blocked = user_fails >= _MAX_FAILS_PER_USER or ip_fails >= _MAX_FAILS_PER_IP
        LoginLog.objects.create(username_attempt=username[:150], ip=ip, user_agent=ua,
                                status='blocked' if blocked else 'failed')
        return JsonResponse({'error': "Foydalanuvchi nomi yoki parol noto'g'ri."}, status=400)
    cache.delete(_fail_keys(ip, username)[1])
    user.last_ip = ip
    user.save(update_fields=['last_ip'])
    LoginLog.objects.create(user=user, username_attempt=username[:150], ip=ip, user_agent=ua, status='success')
    notify_admin_telegram(f"📱 <b>Ilovaga kirish</b>\n👤 {user.get_full_name() or user.username} (@{user.username})\n🌐 IP: {ip}")
    return JsonResponse({'token': _issue_token(user, request, data), 'user': _user_json(user)})


@api(methods=('POST',), auth=False)
def register(request):
    data, err = _body(request)
    if err:
        return err
    ip = get_client_ip(request)
    key = f'learn_api_register_{ip}'
    if cache.get(key, 0) >= REGISTER_PER_IP_HOURLY:
        return JsonResponse({'error': "Juda ko'p urinish. Keyinroq qayta urinib ko'ring."}, status=429)
    form = RegisterForm(data={k: str(data.get(k, '') or '') for k in (
        'username', 'first_name', 'last_name', 'email', 'phone_number', 'password', 'confirm_password')})
    if not form.is_valid():
        errors = [msg for field_errors in form.errors.values() for msg in field_errors]
        return JsonResponse({'error': ' '.join(errors) or "Ma'lumotlarni tekshiring"}, status=400)
    cache.set(key, cache.get(key, 0) + 1, 60 * 60)
    user = form.save(commit=False)
    user.set_password(form.cleaned_data['password'])
    user.last_ip = ip
    user.save()
    notify_admin_telegram(
        f"🆕 <b>Ilovada ro'yxatdan o'tish</b>\n👤 {user.get_full_name() or '—'} (@{user.username})\n"
        f"📞 {user.phone_number or '—'}\n🌐 IP: {ip}")
    return JsonResponse({'token': _issue_token(user, request, data), 'user': _user_json(user)})


@api(methods=('POST',))
def logout(request):
    request.api_token.delete()
    return JsonResponse({'ok': True})


@api(methods=('POST',))
def delete_me(request):
    """Deletes the account for good — the password is asked again first."""
    data, err = _body(request)
    if err:
        return err
    user = request.user
    if user.is_staff:
        return JsonResponse({'error': "Admin hisobini ilovadan o'chirib bo'lmaydi."}, status=403)
    if not user.check_password(str(data.get('password', ''))):
        return JsonResponse({'error': "Parol noto'g'ri."}, status=400)
    delete_account(user)
    return JsonResponse({'ok': True})


# ── profile and course map ───────────────────────────────────────────────
def _level_code(user, profile):
    return profile.level or recommended_level(user)[0] or 'A1'


@api(methods=('GET', 'POST'))
def me(request):
    user = request.user
    profile = get_profile(user)
    if request.method == 'POST':
        data, err = _body(request)
        if err:
            return err
        fields = []
        if data.get('level') in LEVELS:
            profile.level = data['level']
            fields.append('level')
        if data.get('daily_goal') in DAILY_GOALS:
            profile.daily_goal = data['daily_goal']
            fields.append('daily_goal')
        if fields:
            profile.save(update_fields=fields)
    rec_level, rec_avg = recommended_level(user)
    return JsonResponse({
        'user': _user_json(user),
        'level': profile.level or None,
        'level_code': _level_code(user, profile),
        'recommended_level': rec_level,
        'ielts_avg': rec_avg,
        'xp': profile.xp,
        'xp_today': today_xp(user),
        'daily_goal': profile.daily_goal,
        'daily_goals': list(DAILY_GOALS),
        'streak': profile.current_streak,
        'best_streak': profile.best_streak,
        'week': [{'date': d['date'].isoformat(), 'label': d['label'], 'xp': d['xp'], 'today': d['today']}
                 for d in week_activity(user)],
        'review': srs.review_counts(user),
        'mistakes': Mistake.objects.filter(user=user).count(),
        'show_placement': not profile.level and not _done_map(user),
        'streak_freezes': profile.streak_freezes,
        'daily': daily_quests(user, profile),
    })


@api()
def achievements(request):
    return JsonResponse({'badges': badges(request.user)})


@api(methods=('POST',))
def chest(request):
    xp = open_chest(request.user)
    if xp is None:
        return JsonResponse({'error': "Avval bugungi barcha topshiriqlarni bajaring"}, status=400)
    return JsonResponse({'ok': True, 'xp': xp})


@api()
def course(request):
    user = request.user
    profile = get_profile(user)
    code = request.GET.get('level')
    if code not in LEVELS:
        code = _level_code(user, profile)
    data = get_course()
    done = _done_map(user)

    levels = []
    for c in LEVELS:
        slugs = [l['slug'] for u in data['levels'][c]['units'] for l in u['lessons']]
        finished = sum(1 for s in slugs if s in done)
        levels.append({'code': c, **LEVEL_INFO[c], 'total': len(slugs), 'done': finished})

    tests = checkpoints.status(user, done)
    current = None
    units = []
    for unit in data['levels'][code]['units']:
        lessons = []
        for lesson in unit['lessons']:
            state = 'done' if lesson['slug'] in done else ('open' if _is_unlocked(lesson, done) else 'locked')
            if state == 'open' and current is None:
                current, state = lesson['slug'], 'current'
            lessons.append({
                'slug': lesson['slug'], 'title': lesson['title'], 'title_uz': lesson['title_uz'],
                'goal_uz': lesson.get('goal_uz', ''), 'minutes': lesson.get('minutes', 10),
                'words': len(lesson['words']), 'exercises': lesson['exercise_count'],
                'state': state, 'score': done.get(lesson['slug']),
            })
        units.append({'slug': unit['slug'], 'title': unit.get('title', ''), 'title_uz': unit.get('title_uz', ''),
                      'icon': unit.get('icon', 'book-open'), 'lessons': lessons,
                      'test': tests[('unit', unit['slug'])]})
    exam = tests[('level', code)]
    return JsonResponse({'level': code, 'levels': levels, 'units': units, 'current': current,
                         'exam': {**exam, 'passed_at': exam['passed_at'].isoformat() if exam['passed_at'] else None},
                         'pass_mark': checkpoints.PASS_MARK})


# ── lessons ──────────────────────────────────────────────────────────────
def _lesson_json(lesson):
    keys = ('slug', 'level', 'title', 'title_uz', 'goal_uz', 'minutes', 'words', 'steps', 'next_slug', 'unit_title_uz')
    return {k: lesson.get(k) for k in keys}


@api()
def lesson_detail(request, slug):
    lesson = get_lesson(slug)
    if not lesson:
        return JsonResponse({'error': 'Dars topilmadi'}, status=404)
    if not _is_unlocked(lesson, _done_map(request.user)):
        return JsonResponse({'error': 'Avval oldingi darsni tugating'}, status=403)
    return JsonResponse({**_lesson_json(lesson), 'draft': get_draft(request.user, lesson)})


@api(methods=('POST',))
def lesson_draft(request, slug):
    """Same as the website's LessonDraftView: resume a lesson on any device."""
    lesson = get_lesson(slug)
    if not lesson or not _is_unlocked(lesson, _done_map(request.user)):
        return JsonResponse({'error': 'Dars topilmadi'}, status=404)
    data, err = _body(request)
    if err:
        return err
    if data.get('data') is None:
        clear_draft(request.user, lesson)
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': save_draft(request.user, lesson, data.get('data'))})


@api(auth=False)
def app_version(request):
    """Newest app build, so old installs can offer an update."""
    release = AppRelease.latest()
    if not release or not release.available:
        return JsonResponse({'build': 0})
    return JsonResponse({
        'version': release.version, 'build': release.build, 'force': release.force_update,
        'notes': [line.strip() for line in release.notes.splitlines() if line.strip()],
        'url': request.build_absolute_uri(reverse('learn:app_download')),
        'page': request.build_absolute_uri(reverse('learn:app')),
    })


@api(methods=('POST',))
def lesson_complete(request, slug):
    lesson = get_lesson(slug)
    if not lesson:
        return JsonResponse({'error': 'Dars topilmadi'}, status=404)
    if not _is_unlocked(lesson, _done_map(request.user)):
        return JsonResponse({'error': 'Dars hali ochilmagan'}, status=403)
    data, err = _body(request)
    if err:
        return err
    try:
        score = int(data.get('score', 0))
    except (TypeError, ValueError):
        score = 0
    result = complete_lesson(request.user, lesson, score)
    mistakes = data.get('mistakes')
    if isinstance(mistakes, list):
        record_mistakes(request.user, lesson, mistakes[:50])
    return JsonResponse({'ok': True, **result})


@api(methods=('POST',))
def write_check(request):
    data, err = _body(request)
    if err:
        return err
    lesson = get_lesson(str(data.get('slug', '')))
    try:
        step = lesson['steps'][int(data.get('step', -1))] if lesson else None
    except (IndexError, TypeError, ValueError):
        step = None
    text = str(data.get('text', '')).strip()
    if not step or step.get('type') != 'write':
        return JsonResponse({'error': "Topshiriq topilmadi"}, status=400)
    if len(text.split()) < 3:
        return JsonResponse({'error': "Kamida bir nechta gap yozing"}, status=400)
    if not _daily_quota_left(request.user, 'write', WRITE_DAILY_LIMIT):
        return JsonResponse({'error': "Bugungi AI tekshiruv limiti tugadi. Ertaga davom eting!"}, status=429)
    result = ai.check_writing(step.get('prompt') or step.get('prompt_uz', ''), text[:3000], lesson['level'])
    if result is None:
        return JsonResponse({'error': "AI hozir javob bermadi. Keyinroq urinib ko'ring."}, status=503)
    return JsonResponse({'ok': True, **result})


@api(methods=('POST',))
def explain(request):
    """'Explain my answer' — same as the website's ExplainView."""
    data, err = _body(request)
    if err:
        return err
    lesson = get_lesson(str(data.get('slug', '')))
    if not lesson:
        return JsonResponse({'error': 'Dars topilmadi'}, status=404)
    if not _daily_quota_left(request.user, 'explain', EXPLAIN_DAILY_LIMIT):
        return JsonResponse({'error': "Bugungi AI izoh limiti tugadi. Ertaga davom eting!"}, status=429)
    result = explain_step(lesson, data.get('step'), str(data.get('answer', ''))[:300])
    if result is None:
        return JsonResponse({'error': "AI hozir javob bermadi. Keyinroq urinib ko'ring."}, status=503)
    return JsonResponse({'ok': True, **result})


# ── unit tests and level exams ───────────────────────────────────────────
def _test_key(user, tid):
    return f'learn_api_test_{user.pk}_{tid}'


@api()
def checkpoint(request):
    kind, key = request.GET.get('kind', ''), request.GET.get('key', '')
    if kind not in ('unit', 'level') or not checkpoints.lessons_of(kind, key):
        return JsonResponse({'error': 'Test topilmadi'}, status=404)
    if not checkpoints.can_take(kind, key, _done_map(request.user)):
        return JsonResponse({'error': "Bu test hali ochilmagan — avval oldingi bo'limni tugating"}, status=403)
    test = checkpoints.build(kind, key)
    tid = secrets.token_hex(8)
    cache.set(_test_key(request.user, tid), {'kind': kind, 'key': key,
              'served': [[s['_src']['slug'], s['_src']['idx']] for s in test['steps']]}, PRACTICE_TTL)
    return JsonResponse({'id': tid, **test})


@api(methods=('POST',))
def checkpoint_complete(request):
    data, err = _body(request)
    if err:
        return err
    key = _test_key(request.user, str(data.get('id', ''))[:32])
    session = cache.get(key)
    cache.delete(key)
    if not session:
        return JsonResponse({'error': "Test sessiyasi topilmadi. Qaytadan boshlang."}, status=400)
    return JsonResponse({'ok': True, **checkpoints.finish(request.user, session['kind'], session['key'],
                                                          session['served'], data.get('results'))})


# ── mixed practice ───────────────────────────────────────────────────────
# The app has no session, so the served exercises are kept in the cache
# under a one-time id instead (same rules as PracticeView/PracticeCompleteView).
def _practice_key(user, pid):
    return f'learn_api_practice_{user.pk}_{pid}'


@api()
def practice(request):
    steps, words = build_practice(request.user)
    pid = secrets.token_hex(8)
    cache.set(_practice_key(request.user, pid), [[s['_src']['slug'], s['_src']['idx']] for s in steps], PRACTICE_TTL)
    return JsonResponse({'id': pid, 'steps': steps, 'words': words})


@api(methods=('POST',))
def practice_complete(request):
    data, err = _body(request)
    if err:
        return err
    key = _practice_key(request.user, str(data.get('id', ''))[:32])
    served = cache.get(key)
    cache.delete(key)
    if not served:
        return JsonResponse({'error': "Mashq sessiyasi topilmadi. Qaytadan boshlang."}, status=400)
    pay = _daily_quota_left(request.user, 'practice', PRACTICE_PAID_DAILY)
    result = apply_practice(request.user, data.get('results'), {(slug, idx) for slug, idx in served}, pay)
    return JsonResponse({'ok': True, **result})


# ── vocabulary review ────────────────────────────────────────────────────
@api()
def review(request):
    cards = srs.session_cards(request.user)
    pool = list(Vocabulary.objects.filter(user=request.user).order_by('?').values_list('translation', flat=True)[:40])
    return JsonResponse({
        'cards': [{'id': c.id, 'en': c.english, 'uz': c.translation, 'ex': c.example,
                   'new': c.due_at is None, 'reps': c.reps} for c in cards],
        'pool': pool,
        'counts': srs.review_counts(request.user),
    })


@api(methods=('POST',))
def review_grade(request):
    data, err = _body(request)
    if err:
        return err
    try:
        card = Vocabulary.objects.get(pk=int(data.get('id')), user=request.user)
        grade = int(data.get('grade'))
    except (Vocabulary.DoesNotExist, TypeError, ValueError):
        return JsonResponse({'error': "So'z topilmadi"}, status=404)
    return JsonResponse({'ok': True, **grade_review(card, grade)})


# ── stories ──────────────────────────────────────────────────────────────
@api()
def stories(request):
    read = dict(LessonProgress.objects.filter(user=request.user, lesson_slug__startswith='story:')
                .values_list('lesson_slug', 'best_score'))
    items = [{'slug': st['slug'], 'level': st['level'], 'emoji': st.get('emoji', '📖'),
              'minutes': st.get('minutes', 5), 'title': st['title'], 'title_uz': st.get('title_uz', ''),
              'score': read.get('story:' + st['slug'])} for st in get_stories().values()]
    return JsonResponse({'stories': items, 'level': get_profile(request.user).level or None})


@api()
def story_detail(request, slug):
    story = get_stories().get(slug)
    if not story:
        return JsonResponse({'error': 'Hikoya topilmadi'}, status=404)
    return JsonResponse(story)


@api(methods=('POST',))
def story_complete(request, slug):
    if slug not in get_stories():
        return JsonResponse({'error': 'Hikoya topilmadi'}, status=404)
    data, err = _body(request)
    if err:
        return err
    try:
        score = int(data.get('score', 0))
    except (TypeError, ValueError):
        score = 0
    return JsonResponse({'ok': True, **complete_story(request.user, slug, score)})


# ── leaderboard, placement, grammar ──────────────────────────────────────
@api()
def leaderboard_view(request):
    board = leaderboard(request.user, limit=50)
    return JsonResponse({**board, 'start': board['start'].isoformat(), 'end': board['end'].isoformat()})


@api(methods=('GET', 'POST'))
def placement(request):
    if request.method == 'GET':
        return JsonResponse(get_placement())
    data, err = _body(request)
    if err:
        return err
    answers = data.get('answers')
    if not isinstance(answers, dict):
        return JsonResponse({'error': "Javoblar topilmadi"}, status=400)
    level = placement_level(get_placement(), answers)
    profile = get_profile(request.user)
    profile.level = level
    profile.save(update_fields=['level'])
    return JsonResponse({'ok': True, 'level': level})


@api()
def grammar(request):
    done = _done_map(request.user)
    data = get_course()
    out = []
    for code in LEVELS:
        items = [{'lesson': lesson['slug'], 'lesson_title': lesson['title'], 'open': _is_unlocked(lesson, done), **step}
                 for unit in data['levels'][code]['units'] for lesson in unit['lessons']
                 for step in lesson['steps'] if step.get('type') == 'grammar']
        if items:
            out.append({'code': code, 'name': data['levels'][code]['name'], 'items': items})
    return JsonResponse({'levels': out})


# ── AI tutor ─────────────────────────────────────────────────────────────
@api()
def tutor(request):
    scenarios = [{'key': k, 'title_uz': v['title_uz'], 'desc_uz': v['desc_uz'], 'opener': v['opener']}
                 for k, v in ai.SCENARIOS.items()]
    profile = get_profile(request.user)
    return JsonResponse({'scenarios': scenarios, 'level': profile.level or recommended_level(request.user)[0] or 'B1'})


@api(methods=('POST',))
def tutor_send(request):
    data, err = _body(request)
    if err:
        return err
    message = str(data.get('message', '')).strip()
    if not message:
        return JsonResponse({'error': "Xabar bo'sh"}, status=400)
    if not _daily_quota_left(request.user, 'tutor', TUTOR_DAILY_LIMIT):
        return JsonResponse({'error': "Bugungi suhbat limiti tugadi. Ertaga davom etamiz!"}, status=429)
    level = get_profile(request.user).level or recommended_level(request.user)[0] or 'B1'
    result = ai.tutor_reply(str(data.get('scenario', 'free')), level, message, data.get('history'))
    if not result or not result['reply']:
        return JsonResponse({'error': "AI hozir javob bermadi. Qayta urinib ko'ring."}, status=503)
    award_xp(request.user, TUTOR_XP)
    bump(request.user, 'tutor')
    return JsonResponse({'ok': True, **result})


app_name = 'learn_api'

urlpatterns = [
    path('health/', health, name='health'),
    path('auth/login/', login, name='login'),
    path('auth/register/', register, name='register'),
    path('auth/logout/', logout, name='logout'),
    path('auth/delete/', delete_me, name='delete_me'),
    path('me/', me, name='me'),
    path('achievements/', achievements, name='achievements'),
    path('quests/chest/', chest, name='chest'),
    path('course/', course, name='course'),
    path('lessons/<slug:slug>/', lesson_detail, name='lesson'),
    path('lessons/<slug:slug>/complete/', lesson_complete, name='lesson_complete'),
    path('lessons/<slug:slug>/draft/', lesson_draft, name='lesson_draft'),
    path('app-version/', app_version, name='app_version'),
    path('write-check/', write_check, name='write_check'),
    path('explain/', explain, name='explain'),
    path('checkpoint/', checkpoint, name='checkpoint'),
    path('checkpoint/complete/', checkpoint_complete, name='checkpoint_complete'),
    path('practice/', practice, name='practice'),
    path('practice/complete/', practice_complete, name='practice_complete'),
    path('review/', review, name='review'),
    path('review/grade/', review_grade, name='review_grade'),
    path('stories/', stories, name='stories'),
    path('stories/<slug:slug>/', story_detail, name='story'),
    path('stories/<slug:slug>/complete/', story_complete, name='story_complete'),
    path('leaderboard/', leaderboard_view, name='leaderboard'),
    path('placement/', placement, name='placement'),
    path('grammar/', grammar, name='grammar'),
    path('tutor/', tutor, name='tutor'),
    path('tutor/send/', tutor_send, name='tutor_send'),
]
