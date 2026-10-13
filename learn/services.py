import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, F, Sum
from django.utils import timezone

from users.models import Vocabulary
from .content import EXERCISE_STEPS, get_lesson
from .models import DailyXP, LearnerProfile, LessonProgress, Mistake

LESSON_XP_FIRST = 10       # + up to 10 more for accuracy, first completion only
LESSON_XP_REPEAT = 5       # once per lesson per day, so replays can't farm the leaderboard
REVIEW_XP = 1
TUTOR_XP = 2


def repeat_pays(progress):
    """A repeated lesson/story earns XP only on its first replay of the day.

    Call before counting the new attempt: completed_at moves on every replay,
    so "touched today and already replayed" means today's replay was paid.
    """
    return timezone.localdate(progress.completed_at) != timezone.localdate() or progress.attempts < 2


def get_profile(user):
    profile, _ = LearnerProfile.objects.get_or_create(user=user)
    return profile


@transaction.atomic
def award_xp(user, amount):
    """Add XP for today and keep the streak counting consecutive days."""
    today = timezone.localdate()
    profile = LearnerProfile.objects.select_for_update().get_or_create(user=user)[0]
    if profile.last_active != today:
        if profile.last_active == today - timedelta(days=1):
            profile.streak += 1
        else:
            profile.streak = 1
        profile.best_streak = max(profile.best_streak, profile.streak)
        profile.last_active = today
    profile.xp += amount
    profile.save()
    day, _ = DailyXP.objects.get_or_create(user=user, date=today)
    DailyXP.objects.filter(pk=day.pk).update(xp=F('xp') + amount)
    return profile


def today_xp(user):
    row = DailyXP.objects.filter(user=user, date=timezone.localdate()).first()
    return row.xp if row else 0


def week_activity(user):
    """Last 7 days, oldest first: [{'date', 'xp', 'label'}]."""
    today = timezone.localdate()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    xp = dict(DailyXP.objects.filter(user=user, date__gte=days[0]).values_list('date', 'xp'))
    labels = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya']
    return [{'date': d, 'xp': xp.get(d, 0), 'label': labels[d.weekday()], 'today': d == today} for d in days]


def add_lesson_words(user, lesson):
    """Put the lesson's new words into the learner's review deck (once)."""
    existing = {e.lower() for e in user.vocabulary.values_list('english', flat=True)}
    added = []
    for w in lesson.get('words', []):
        if w['en'].lower() in existing:
            continue
        added.append(Vocabulary(
            user=user, english=w['en'][:255], translation=w['uz'][:255],
            example=(w.get('ex') or '')[:300], lesson_slug=lesson['slug'],
        ))
        existing.add(w['en'].lower())
    Vocabulary.objects.bulk_create(added)
    return len(added)


@transaction.atomic
def complete_lesson(user, lesson, score):
    score = max(0, min(100, int(score)))
    progress, created = LessonProgress.objects.select_for_update().get_or_create(
        user=user, lesson_slug=lesson['slug'], defaults={'best_score': score, 'attempts': 1},
    )
    if created:
        xp = LESSON_XP_FIRST + round(score / 10)
    else:
        xp = LESSON_XP_REPEAT if repeat_pays(progress) else 0
        progress.attempts += 1
        progress.best_score = max(progress.best_score, score)
        progress.completed_at = timezone.now()
        progress.save()
    words_added = add_lesson_words(user, lesson)
    profile = award_xp(user, xp)
    return {'xp': xp, 'words_added': words_added, 'first_time': created,
            'total_xp': profile.xp, 'streak': profile.streak, 'best_score': progress.best_score}


def recommended_level(user):
    """Map the learner's IELTS mock average to a starting CEFR level."""
    from exams.models import UserResult
    avg = UserResult.objects.graded().filter(user=user).aggregate(a=Avg('score'))['a']
    if avg is None:
        return None, None
    if avg < 3.5:
        level = 'A1'
    elif avg < 4.0:
        level = 'A2'
    elif avg < 5.5:
        level = 'B1'
    elif avg < 7.0:
        level = 'B2'
    elif avg < 8.5:
        level = 'C1'
    else:
        level = 'C2'
    return level, round(avg, 1)


# ── Mixed practice from past mistakes ───────────────────────────────────
# Speaking needs a microphone and a supporting browser, so it never comes
# back as a "mistake" to fix.
PRACTICE_TYPES = EXERCISE_STEPS - {'speak'}
PRACTICE_SIZE = 10
PRACTICE_MISTAKES = 7


def _practice_step(slug, idx):
    lesson = get_lesson(slug)
    if not lesson or not 0 <= idx < len(lesson['steps']):
        return None, None
    step = lesson['steps'][idx]
    ok = step.get('type') in PRACTICE_TYPES and not step.get('needs_text')
    return (step, lesson) if ok else (None, None)


def record_mistakes(user, lesson, indexes):
    now = timezone.now()
    for idx in {i for i in indexes if isinstance(i, int)}:
        if not _practice_step(lesson['slug'], idx)[0]:
            continue
        m, created = Mistake.objects.get_or_create(user=user, lesson_slug=lesson['slug'], step_index=idx)
        if not created:
            m.wrong_count += 1
            m.right_streak = 0
            m.last_wrong_at = now
            m.save()


def build_practice(user):
    """Up to 10 exercises: weakest past mistakes first, topped up with random
    exercises from finished lessons, then shuffled (interleaved practice)."""
    picked, seen = [], set()
    for m in Mistake.objects.filter(user=user).order_by('-wrong_count', 'last_wrong_at')[:30]:
        step, lesson = _practice_step(m.lesson_slug, m.step_index)
        if step and len(picked) < PRACTICE_MISTAKES:
            picked.append((lesson, m.step_index, True))
            seen.add((m.lesson_slug, m.step_index))
    pool = []
    for slug in LessonProgress.objects.filter(user=user).values_list('lesson_slug', flat=True):
        lesson = get_lesson(slug)
        if lesson:
            pool += [(lesson, i, False) for i, st in enumerate(lesson['steps'])
                     if st.get('type') in PRACTICE_TYPES and (slug, i) not in seen]
    random.shuffle(pool)
    picked += pool[:PRACTICE_SIZE - len(picked)]
    random.shuffle(picked)

    steps, words, seen_words = [], [], set()
    for lesson, idx, was_wrong in picked:
        steps.append(dict(lesson['steps'][idx], _src={'slug': lesson['slug'], 'idx': idx, 'mistake': was_wrong}))
        for w in lesson['words']:
            if w['en'] not in seen_words:
                seen_words.add(w['en'])
                words.append(w)
    return steps, words


def apply_practice(user, results, served=None, pay=True):
    """`served` is the set of (slug, idx) the session actually showed; anything
    else is ignored and each served step counts once, so a hand-made request
    can't claim XP for exercises nobody answered."""
    now = timezone.now()
    right = 0
    served = None if served is None else set(served)
    for r in results if isinstance(results, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get('step'), int):
            continue
        slug, idx, ok = str(r.get('slug', '')), r['step'], bool(r.get('ok'))
        if served is not None:
            if (slug, idx) not in served:
                continue
            served.discard((slug, idx))
        if not _practice_step(slug, idx)[0]:
            continue
        m = Mistake.objects.filter(user=user, lesson_slug=slug, step_index=idx).first()
        if ok:
            right += 1
            if m:
                m.right_streak += 1
                if m.right_streak >= 2:
                    m.delete()
                else:
                    m.save()
        elif m:
            m.wrong_count += 1
            m.right_streak = 0
            m.last_wrong_at = now
            m.save()
        else:
            Mistake.objects.create(user=user, lesson_slug=slug, step_index=idx)
    xp = 3 + min(right, 12) if pay else 0
    profile = award_xp(user, xp)
    return {'xp': xp, 'streak': profile.streak, 'right': right,
            'mistakes_left': Mistake.objects.filter(user=user).count()}


# ── Weekly leaderboard ──────────────────────────────────────────────────
def leaderboard(user, limit=20):
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday())
    rows = list(DailyXP.objects.filter(date__gte=start).values('user').annotate(total=Sum('xp'))
                .filter(total__gt=0).order_by('-total', 'user'))
    from users.models import User
    names = {u.pk: u for u in User.objects.filter(pk__in=[r['user'] for r in rows[:limit]] + [user.pk])}
    board = []
    for rank, r in enumerate(rows, 1):
        if rank <= limit:
            u = names[r['user']]
            board.append({'rank': rank, 'name': _display_name(u), 'xp': r['total'], 'me': u.pk == user.pk})
    my = next(({'rank': i, 'xp': r['total']} for i, r in enumerate(rows, 1) if r['user'] == user.pk), None)
    return {'rows': board, 'me': my, 'total': len(rows), 'start': start, 'end': start + timedelta(days=6)}


def _display_name(u):
    # First name + last initial: recognisable to classmates, not a full name list.
    if u.first_name:
        return f"{u.first_name} {u.last_name[:1]}." if u.last_name else u.first_name
    return u.username
