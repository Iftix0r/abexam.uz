from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, F
from django.utils import timezone

from users.models import Vocabulary
from .models import DailyXP, LearnerProfile, LessonProgress

LESSON_XP_FIRST = 10       # + up to 10 more for accuracy, first completion only
LESSON_XP_REPEAT = 5
REVIEW_XP = 1
TUTOR_XP = 2


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
        progress.attempts += 1
        progress.best_score = max(progress.best_score, score)
        progress.completed_at = timezone.now()
        progress.save()
        xp = LESSON_XP_REPEAT
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
    else:
        level = 'B2'
    return level, round(avg, 1)
