"""Spaced repetition for the personal vocabulary deck (SM-2 variant).

Grades: 0 = Again (forgot), 1 = Hard, 2 = Good, 3 = Easy.
A forgotten card comes back in the same session (10 minutes); remembered
cards are pushed out by a growing interval, so a learner spends review time
only on the words they are about to forget.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

AGAIN, HARD, GOOD, EASY = 0, 1, 2, 3
MIN_EASE = 1.3
NEW_PER_SESSION = 15
SESSION_LIMIT = 40


def schedule(card, grade, now=None):
    """Apply a review grade to a Vocabulary row (not saved)."""
    now = now or timezone.now()
    grade = max(AGAIN, min(EASY, int(grade)))

    if grade == AGAIN:
        card.lapses += 1 if card.reps else 0
        card.reps = 0
        card.interval_days = 0
        card.ease = max(MIN_EASE, card.ease - 0.2)
        card.due_at = now + timedelta(minutes=10)
        return card

    card.reps += 1
    if card.reps == 1:
        interval = {HARD: 1, GOOD: 1, EASY: 4}[grade]
    elif card.reps == 2:
        interval = {HARD: 2, GOOD: 3, EASY: 6}[grade]
    else:
        prev = max(card.interval_days, 1)
        interval = {HARD: prev * 1.2, GOOD: prev * card.ease, EASY: prev * card.ease * 1.3}[grade]

    if grade == HARD:
        card.ease = max(MIN_EASE, card.ease - 0.15)
    elif grade == EASY:
        card.ease += 0.15

    card.interval_days = round(min(interval, 365), 2)
    card.due_at = now + timedelta(days=card.interval_days)
    return card


def due_queryset(user, now=None):
    now = now or timezone.now()
    return user.vocabulary.filter(due_at__isnull=False, due_at__lte=now)


def session_cards(user, now=None):
    """Cards for one review session: everything due, topped up with new words."""
    due = list(due_queryset(user, now).order_by('due_at')[:SESSION_LIMIT])
    room = max(0, min(NEW_PER_SESSION, SESSION_LIMIT - len(due)))
    new = list(user.vocabulary.filter(due_at__isnull=True).order_by('created_at')[:room]) if room else []
    return due + new


def review_counts(user, now=None):
    now = now or timezone.now()
    qs = user.vocabulary.all()
    due = qs.filter(due_at__isnull=False, due_at__lte=now).count()
    new = qs.filter(due_at__isnull=True).count()
    return {
        'due': due,
        'new': new,
        'session': min(SESSION_LIMIT, due + min(new, NEW_PER_SESSION)),
        'total': qs.count(),
        'learned': qs.filter(Q(interval_days__gte=21)).count(),
    }
