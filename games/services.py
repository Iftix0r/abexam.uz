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
from django.db.models import Max, Sum
from django.utils import timezone

from learn.content import LEVELS, get_course
from learn.models import LearnerProfile
from learn.services import award_xp
from users.models import User

from .models import GameScore

GAMES = {
    'quiz': {'title': "So'z poygasi", 'icon': 'zap', 'color': '#f59e0b', 'size': 30, 'seconds': 60,
             'text': "60 soniyada iloji boricha ko'p to'g'ri tarjimani toping."},
    'scramble': {'title': 'Harf ustasi', 'icon': 'shuffle', 'color': '#8b5cf6', 'size': 10, 'seconds': 0,
                 'text': "Aralashgan harflardan to'g'ri so'zni yig'ing."},
    'match': {'title': 'Juftlikni top', 'icon': 'blocks', 'color': '#10b981', 'size': 8, 'seconds': 0,
              'text': "Inglizcha so'zni o'zbekcha tarjimasi bilan ulang."},
    'spell': {'title': 'Tarjima yoz', 'icon': 'keyboard', 'color': '#3b82f6', 'size': 10, 'seconds': 0,
              'text': "O'zbekcha so'zni ko'rib, inglizcha yozing."},
}
ROUND_SECONDS = 900
MIN_SECONDS_PER_ANSWER = 0.35
POINTS_PER_WORD = 10
POINTS_PER_MISTAKE = 3
XP_PER_TWO_WORDS = 1
DAILY_XP_LIMIT = 40
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


def _quiz_items(picked, bank):
    items = []
    for word in picked:
        to_uzbek = random.random() < 0.7
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


def build_items(game, level):
    bank = word_bank(level)
    pool = bank
    if game == 'scramble':
        pool = [w for w in bank if _SINGLE_WORD.fullmatch(w['en'].lower())]
    picked = random.sample(pool, min(GAMES[game]['size'], len(pool)))
    if game == 'quiz':
        return _quiz_items(picked, bank)
    if game == 'scramble':
        return [{**w, 'letters': _scrambled(w['en'].lower())} for w in picked]
    return picked


def start_round(user, game, level):
    items = build_items(game, level)
    token = secrets.token_urlsafe(16)
    cache.set(f'game_round:{token}', {
        'user': user.pk, 'game': game, 'level': level, 'size': len(items), 'started': timezone.now(),
    }, ROUND_SECONDS)
    return token, items


def xp_today(user):
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return GameScore.objects.filter(user=user, created_at__gte=start).aggregate(t=Sum('xp'))['t'] or 0


def finish_round(user, token, correct, mistakes):
    """Returns (result, error)."""
    key = f'game_round:{token}'
    state = cache.get(key)
    if not state or state['user'] != user.pk:
        return None, "O'yin topilmadi, qaytadan boshlang"
    cache.delete(key)  # a round counts once
    correct = max(0, min(correct, state['size']))
    mistakes = max(0, min(mistakes, 500))
    elapsed = (timezone.now() - state['started']).total_seconds()
    if correct * MIN_SECONDS_PER_ANSWER > elapsed:
        return None, "Natija qabul qilinmadi"

    score = max(0, correct * POINTS_PER_WORD - mistakes * POINTS_PER_MISTAKE)
    previous_best = (GameScore.objects.filter(user=user, game=state['game'], level=state['level'])
                     .aggregate(b=Max('score'))['b'] or 0)
    room = max(0, DAILY_XP_LIMIT - xp_today(user))
    xp = min(room, correct // 2 * XP_PER_TWO_WORDS)
    with transaction.atomic():
        GameScore.objects.create(user=user, game=state['game'], level=state['level'], score=score,
                                 correct=correct, mistakes=mistakes, xp=xp)
        if xp:
            award_xp(user, xp)
    return {'score': score, 'correct': correct, 'mistakes': mistakes, 'size': state['size'], 'xp': xp,
            'best': max(score, previous_best), 'new_best': score > previous_best,
            'xp_limit_reached': room == 0 or xp == room}, None


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
