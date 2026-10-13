"""Duolingo-style motivation: daily quests with a reward chest, and
achievement badges with tiers. Shared by the website and the mobile API.
"""
import random

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from users.models import Vocabulary
from .models import DailyXP, LearnerProfile, LessonProgress

CHEST_XP = 15

# key, title (with {n}), lucide icon, DailyXP counter, default target
QUEST_POOL = [
    ('lessons', "{n} ta dars o'ting", 'graduation-cap', 'lessons', 2),
    ('perfect', "Bitta darsni 90%+ natija bilan tugating", 'star', 'perfect', 1),
    ('reviews', "{n} ta so'zni takrorlang", 'layers', 'reviews', 10),
    ('story', "Bitta hikoya o'qing", 'book-open', 'stories', 1),
    ('practice', "Xatolar ustida bir marta ishlang", 'target', 'practice', 1),
    ('tutor', "AI bilan {n} ta xabar almashing", 'messages-square', 'tutor', 5),
]


def bump(user, field, n=1):
    """Count one quest-relevant action for today."""
    day, _ = DailyXP.objects.get_or_create(user=user, date=timezone.localdate())
    DailyXP.objects.filter(pk=day.pk).update(**{field: F(field) + n})


def daily_quests(user, profile=None):
    """Today's three quests: the XP goal plus two picked per learner per day."""
    profile = profile or LearnerProfile.objects.get_or_create(user=user)[0]
    today = timezone.localdate()
    day = DailyXP.objects.filter(user=user, date=today).first() or DailyXP(user=user, date=today)
    # Same two quests all day for this learner, different ones tomorrow.
    picked = random.Random(today.toordinal() * 7919 + user.pk).sample(QUEST_POOL, 2)
    quests = [{'key': 'xp', 'title_uz': f"{profile.daily_goal} XP to'plang", 'icon': 'zap',
               'target': profile.daily_goal, 'progress': min(day.xp, profile.daily_goal)}]
    for key, title, icon, field, target in picked:
        quests.append({'key': key, 'title_uz': title.format(n=target), 'icon': icon, 'target': target,
                       'progress': min(getattr(day, field), target)})
    for q in quests:
        q['done'] = q['progress'] >= q['target']
    return {'quests': quests, 'all_done': all(q['done'] for q in quests), 'chest_opened': day.chest,
            'chest_xp': CHEST_XP}


@transaction.atomic
def open_chest(user):
    """Reward for finishing all of today's quests (once a day). Returns XP or None."""
    from .services import award_xp
    info = daily_quests(user)
    if not info['all_done']:
        return None
    updated = DailyXP.objects.filter(user=user, date=timezone.localdate(), chest=False).update(chest=True)
    if not updated:
        return None
    award_xp(user, CHEST_XP)
    return CHEST_XP


# ── achievements ─────────────────────────────────────────────────────────
# key, title, lucide icon, description (with {n}), tiers
BADGES = [
    ('lessons', "Bilim yo'li", 'graduation-cap', "{n} ta dars tugating", [1, 10, 30, 60, 100]),
    ('streak', 'Olovli seriya', 'flame', "{n} kunlik seriya", [3, 7, 30, 100, 365]),
    ('perfect', 'Mukammallik', 'star', "{n} ta darsni 100% bilan tugating", [1, 5, 20, 50]),
    ('words', "So'z boyligi", 'library', "Lug'atingizda {n} ta so'z", [25, 100, 300, 700]),
    ('stories', 'Kitobxon', 'book-open', "{n} ta hikoya o'qing", [1, 5, 15, 30]),
    ('xp', 'XP ustasi', 'zap', "{n} XP to'plang", [100, 500, 2000, 10000]),
]


def _metrics(user, profile):
    lessons = LessonProgress.objects.filter(user=user).exclude(lesson_slug__startswith='story:')
    return {
        'lessons': lessons.count(),
        'perfect': lessons.filter(best_score=100).count(),
        'streak': profile.best_streak,
        'words': Vocabulary.objects.filter(user=user).count(),
        'stories': LessonProgress.objects.filter(user=user, lesson_slug__startswith='story:').count(),
        'xp': profile.xp,
    }


def badges(user, profile=None):
    profile = profile or LearnerProfile.objects.get_or_create(user=user)[0]
    values = _metrics(user, profile)
    out = []
    for key, title, icon, desc, tiers in BADGES:
        value = values[key]
        tier = sum(1 for t in tiers if value >= t)
        nxt = tiers[tier] if tier < len(tiers) else None
        out.append({
            'key': key, 'title_uz': title, 'icon': icon, 'tier': tier, 'tiers': len(tiers), 'value': value,
            'next': nxt, 'desc_uz': desc.format(n=nxt or tiers[-1]),
            'pct': 100 if nxt is None else round(value * 100 / nxt),
        })
    return out


def check_badges(user):
    """Newly reached tiers since last time (to celebrate them), and remember them."""
    profile = LearnerProfile.objects.get_or_create(user=user)[0]
    seen = set(profile.badges or [])
    new = []
    for b in badges(user, profile):
        for level in range(1, b['tier'] + 1):
            mark = f"{b['key']}:{level}"
            if mark not in seen:
                seen.add(mark)
                if level == b['tier']:
                    new.append({'key': b['key'], 'title_uz': b['title_uz'], 'icon': b['icon'], 'tier': level})
    if len(seen) != len(profile.badges or []):
        LearnerProfile.objects.filter(pk=profile.pk).update(badges=sorted(seen))
    return new
