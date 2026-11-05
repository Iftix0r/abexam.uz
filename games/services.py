"""Rounds of the English word games. Words come from the course, so playing
repeats what the lessons teach.

The browser has to know the answers to react instantly, so a score cannot be
taken on trust: the server hands out each round once, caps it by the words it
served and rejects a result faster than anyone could play.
"""
import random
import re
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Max, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from learn.content import LEVELS, get_course
from learn.models import LearnerProfile
from learn.services import award_xp
from users.models import User

from .models import GameMistake, GameScore

GAMES = {
    'quiz': {'title': "So'z poygasi", 'icon': 'zap', 'color': '#f59e0b', 'size': 30, 'seconds': 60,
             'text': "60 soniyada iloji boricha ko'p to'g'ri tarjimani toping."},
    'scramble': {'title': 'Harf ustasi', 'icon': 'shuffle', 'color': '#8b5cf6', 'size': 10, 'seconds': 0,
                 'text': "Aralashgan harflardan to'g'ri so'zni yig'ing."},
    'match': {'title': 'Juftlikni top', 'icon': 'blocks', 'color': '#10b981', 'size': 8, 'seconds': 0,
              'text': "Inglizcha so'zni o'zbekcha tarjimasi bilan ulang."},
    'spell': {'title': 'Tarjima yoz', 'icon': 'keyboard', 'color': '#3b82f6', 'size': 10, 'seconds': 0,
              'text': "O'zbekcha so'zni ko'rib, inglizcha yozing."},
    'listen': {'title': 'Tinglab top', 'icon': 'volume-2', 'color': '#ec4899', 'size': 12, 'seconds': 0,
               'text': "So'zni eshiting va to'g'ri tarjimasini tanlang."},
    'truefalse': {'title': "Ha yoki Yo'q", 'icon': 'check-check', 'color': '#ef4444', 'size': 40, 'seconds': 45,
                  'text': "Tarjima to'g'rimi? 45 soniyada tez javob bering."},
    'hunter': {'title': "So'z ovchisi", 'icon': 'target', 'color': '#14b8a6', 'size': 8, 'seconds': 0,
               'text': "Harflarni taxmin qilib so'zni toping, 6 ta imkoniyat bor."},
    'review': {'title': 'Xatolar ustida', 'icon': 'rotate-ccw', 'color': '#d32f2f', 'size': 12, 'seconds': 0,
               'text': "Xato qilgan so'zlaringizni takrorlang.", 'hidden': True},
}
RANKS = ((0, 'Yangi boshlovchi'), (500, "O'rganuvchi"), (1500, 'Bilimdon'), (4000, 'Usta'), (8000, 'Chempion'),
         (15000, 'Afsona'))
BADGES = (
    ('first', 'Birinchi qadam', "Birinchi o'yinni tugatish", 'play'),
    ('perfect', 'Xatosiz', "Bir o'yinni xatosiz tugatish", 'circle-check'),
    ('combo10', 'Olovli seriya', "10 ta ketma-ket to'g'ri javob", 'flame'),
    ('words100', "100 so'z", "Jami 100 ta to'g'ri javob", 'book-open'),
    ('words1000', "1000 so'z", "Jami 1000 ta to'g'ri javob", 'library'),
    ('streak7', 'Bir hafta', "7 kun ketma-ket o'ynash", 'calendar-days'),
    ('allgames', 'Hammasini sinadi', "Barcha o'yinlarni o'ynash", 'gamepad-2'),
)
ROUND_SECONDS = 900
MIN_SECONDS_PER_ANSWER = 0.35
POINTS_PER_WORD = 10
POINTS_PER_MISTAKE = 3
XP_PER_TWO_WORDS = 1
DAILY_XP_LIMIT = 40
DAILY_BONUS_XP = 10
DAILY_MIN_CORRECT = 5
COMBO_POINTS = 2
_SINGLE_WORD = re.compile(r'[a-z]{3,12}')


def word_bank(level):
    seen, words = set(), []
    for lesson in get_course()['lessons'].values():
        if lesson.get('level') != level:
            continue
        for word in lesson.get('words', []):
            en, uz = word.get('en', '').strip(), word.get('uz', '').strip()
            if en and uz and en.lower() not in seen:
                seen.add(en.lower())
                words.append({'en': en, 'uz': uz})
    return words


def default_level(user):
    profile = LearnerProfile.objects.filter(user=user).first()
    return profile.level if profile and profile.level in LEVELS else LEVELS[0]


def _quiz_items(picked, bank, always_uzbek=False):
    items = []
    for word in picked:
        to_uzbek = always_uzbek or random.random() < 0.7
        ask, answer = ('en', 'uz') if to_uzbek else ('uz', 'en')
        others = list({w[answer] for w in bank if w[answer] != word[answer]})
        options = random.sample(others, min(3, len(others))) + [word[answer]]
        random.shuffle(options)
        items.append({'en': word['en'], 'uz': word['uz'], 'q': word[ask], 'a': word[answer], 'options': options})
    return items


def _scrambled(word):
    letters = list(word)
    for _ in range(8):
        random.shuffle(letters)
        if ''.join(letters) != word:
            break
    return letters


def _true_false_items(picked, bank):
    items = []
    for word in picked:
        honest = random.random() < 0.5
        others = [w['uz'] for w in bank if w['uz'] != word['uz']]
        shown = word['uz'] if honest or not others else random.choice(others)
        items.append({'en': word['en'], 'uz': word['uz'], 'shown': shown, 'ok': shown == word['uz']})
    return items


def build_items(game, level, user=None):
    bank = word_bank(level)
    size = GAMES[game]['size']
    if game == 'review':
        rows = list(GameMistake.objects.filter(user=user).order_by('?')[:size]) if user else []
        return _quiz_items([{'en': m.en, 'uz': m.uz} for m in rows], bank + [{'en': m.en, 'uz': m.uz} for m in rows])
    pool = bank
    if game in ('scramble', 'hunter'):
        pool = [w for w in bank if _SINGLE_WORD.fullmatch(w['en'].lower())]
    picked = random.sample(pool, min(size, len(pool)))
    if game == 'quiz':
        return _quiz_items(picked, bank)
    if game == 'listen':
        return _quiz_items(picked, bank, always_uzbek=True)
    if game == 'truefalse':
        return _true_false_items(picked, bank)
    if game == 'scramble':
        return [{**w, 'letters': _scrambled(w['en'].lower())} for w in picked]
    return picked


def start_round(user, game, level):
    items = build_items(game, level, user)
    token = secrets.token_urlsafe(16)
    cache.set(f'game_round:{token}', {
        'user': user.pk, 'game': game, 'level': level, 'size': len(items), 'started': timezone.now(),
        'words': {item['en']: item['uz'] for item in items},
    }, ROUND_SECONDS)
    return token, items


def xp_today(user):
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return GameScore.objects.filter(user=user, created_at__gte=start).aggregate(t=Sum('xp'))['t'] or 0


def _today_start():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def daily_game():
    """Today's challenge: the same game for everyone, a new one each day."""
    playable = [slug for slug, game in GAMES.items() if not game.get('hidden')]
    return playable[timezone.localdate().toordinal() % len(playable)]


def daily_done(user):
    return GameScore.objects.filter(user=user, game=daily_game(), created_at__gte=_today_start(),
                                    correct__gte=DAILY_MIN_CORRECT).exists()


def _remember_mistakes(user, state, missed, solved):
    words = state['words']
    for en in missed:
        if en in words:  # only words this round really served
            GameMistake.objects.get_or_create(user=user, en=en, defaults={'uz': words[en], 'level': state['level']})
    clean = [en for en in solved if en in words and en not in missed]
    GameMistake.objects.filter(user=user, en__in=clean).delete()


def finish_round(user, token, correct, mistakes, combo=0, missed=(), solved=()):
    """Returns (result, error)."""
    key = f'game_round:{token}'
    state = cache.get(key)
    if not state or state['user'] != user.pk:
        return None, "O'yin topilmadi, qaytadan boshlang"
    cache.delete(key)  # a round counts once
    correct = max(0, min(correct, state['size']))
    mistakes = max(0, min(mistakes, 500))
    combo = max(0, min(combo, correct))
    elapsed = (timezone.now() - state['started']).total_seconds()
    if correct * MIN_SECONDS_PER_ANSWER > elapsed:
        return None, "Natija qabul qilinmadi"

    score = max(0, correct * POINTS_PER_WORD + combo * COMBO_POINTS - mistakes * POINTS_PER_MISTAKE)
    previous_best = (GameScore.objects.filter(user=user, game=state['game'], level=state['level'])
                     .aggregate(b=Max('score'))['b'] or 0)
    room = max(0, DAILY_XP_LIMIT - xp_today(user))
    xp = min(room, correct // 2 * XP_PER_TWO_WORDS)
    earns_bonus = state['game'] == daily_game() and correct >= DAILY_MIN_CORRECT and not daily_done(user)
    bonus = DAILY_BONUS_XP if earns_bonus else 0
    before = earned_badges(user)
    with transaction.atomic():
        GameScore.objects.create(user=user, game=state['game'], level=state['level'], score=score, correct=correct,
                                 mistakes=mistakes, combo=combo, xp=xp,
                                 perfect=correct == state['size'] and correct > 0 and mistakes == 0)
        if xp or bonus:
            award_xp(user, xp + bonus)
        _remember_mistakes(user, state, list(missed)[:60], list(solved)[:60])
    new_badges = [b[1] for b in BADGES if b[0] in earned_badges(user) - before]
    return {'score': score, 'correct': correct, 'mistakes': mistakes, 'size': state['size'], 'xp': xp + bonus,
            'combo': combo, 'best': max(score, previous_best), 'new_best': score > previous_best,
            'daily_bonus': bonus, 'new_badges': new_badges,
            'xp_limit_reached': room == 0 or xp == room}, None


def play_days(user):
    """(current streak, longest streak) of days with a finished game."""
    days = list(GameScore.objects.filter(user=user).annotate(day=TruncDate('created_at'))
                .values_list('day', flat=True).distinct().order_by('-day')[:400])
    longest = run = 0
    previous = None
    current = None
    for day in days:
        run = run + 1 if previous and (previous - day).days == 1 else 1
        if current is None and previous and (previous - day).days != 1:
            current = run_before
        run_before = run
        longest = max(longest, run)
        previous = day
    today = timezone.localdate()
    if not days or (today - days[0]).days > 1:
        return 0, longest
    return (run if current is None else current), longest


def earned_badges(user):
    stats = GameScore.objects.filter(user=user).aggregate(
        games=Count('id'), words=Sum('correct'), combo=Max('combo'), kinds=Count('game', distinct=True))
    if not stats['games']:
        return set()
    earned = {'first'}
    if GameScore.objects.filter(user=user, perfect=True).exists():
        earned.add('perfect')
    if (stats['combo'] or 0) >= 10:
        earned.add('combo10')
    if (stats['words'] or 0) >= 100:
        earned.add('words100')
    if (stats['words'] or 0) >= 1000:
        earned.add('words1000')
    if play_days(user)[1] >= 7:
        earned.add('streak7')
    if stats['kinds'] >= sum(1 for g in GAMES.values() if not g.get('hidden')):
        earned.add('allgames')
    return earned


def player_rank(user):
    total = GameScore.objects.filter(user=user).aggregate(t=Sum('score'))['t'] or 0
    index = max(i for i, (points, _) in enumerate(RANKS) if total >= points)
    floor, title = RANKS[index]
    if index + 1 == len(RANKS):
        return {'title': title, 'total': total, 'next': None, 'left': 0, 'pct': 100}
    ceiling, following = RANKS[index + 1]
    return {'title': title, 'total': total, 'next': following, 'left': ceiling - total,
            'pct': round((total - floor) / (ceiling - floor) * 100)}


def mistake_count(user):
    return GameMistake.objects.filter(user=user).count()


def my_bests(user):
    rows = GameScore.objects.filter(user=user).values('game').annotate(best=Max('score'))
    return {r['game']: r['best'] for r in rows}


def weekly_board(user, limit=10):
    now = timezone.localtime()
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    ranked = list(GameScore.objects.filter(created_at__gte=monday, user__is_active=True, user__is_staff=False)
                  .values('user').annotate(total=Sum('score')).filter(total__gt=0).order_by('-total', 'user'))
    users = User.objects.in_bulk([r['user'] for r in ranked[:limit]])
    rows = [{'rank': rank, 'name': users[r['user']].public_name, 'initials': users[r['user']].initials,
             'avatar_color': users[r['user']].avatar_color, 'premium': users[r['user']].is_premium,
             'total': r['total'], 'me': r['user'] == user.pk}
            for rank, r in enumerate(ranked[:limit], 1)]
    me = next(({'rank': rank, 'total': r['total']} for rank, r in enumerate(ranked, 1) if r['user'] == user.pk), None)
    return {'rows': rows, 'me': me}
