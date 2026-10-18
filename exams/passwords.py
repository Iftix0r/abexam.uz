"""Hourly exam passwords.

Each exam has a 6-digit password that changes every hour, on the hour.
Nothing is stored: the password is derived from SECRET_KEY, the exam id and
the current hour, so the panel and the exam page always agree without a
cron job or a table to keep in sync. The invigilator reads it in the panel
and tells it to the students in the room; a student who enters it is let in
to that exam until they submit it.
"""
import hashlib
import hmac
import time

from django.conf import settings
from django.core.cache import cache

ROTATION_SECONDS = 3600
# A password handed out at 10:59 still works for a student who types it at
# 11:03 — the previous hour's password is accepted for this long into the
# next hour.
GRACE_SECONDS = 10 * 60
# Covers sitting on the exam page for the whole attempt (and reloads during
# it); submitting clears it, so a retake needs a fresh password.
UNLOCK_TTL = 6 * 3600
# Wrong guesses per user per exam before a short lockout — 6 digits are too
# few to leave unthrottled.
MAX_FAILURES = 5
FAILURE_WINDOW = 10 * 60


def _slot(now=None):
    return int((time.time() if now is None else now) // ROTATION_SECONDS)


def exam_password(exam_pk, now=None, slot=None):
    slot = _slot(now) if slot is None else slot
    digest = hmac.new(settings.SECRET_KEY.encode(), f'exam-password:{exam_pk}:{slot}'.encode(),
                      hashlib.sha256).digest()
    return f'{int.from_bytes(digest[:8], "big") % 1_000_000:06d}'


def seconds_until_rotation(now=None):
    now = time.time() if now is None else now
    return int(ROTATION_SECONDS - now % ROTATION_SECONDS)


def check_exam_password(exam_pk, entered, now=None):
    entered = ''.join(ch for ch in str(entered) if ch.isdigit())
    if len(entered) != 6:
        return False
    now = time.time() if now is None else now
    slot = _slot(now)
    candidates = [exam_password(exam_pk, slot=slot)]
    if now % ROTATION_SECONDS < GRACE_SECONDS:
        candidates.append(exam_password(exam_pk, slot=slot - 1))
    return any(hmac.compare_digest(entered, c) for c in candidates)


def _unlock_key(user_pk, exam_pk):
    return f'exam_unlocked_{user_pk}_{exam_pk}'


def _failures_key(user_pk, exam_pk):
    return f'exam_pw_fail_{user_pk}_{exam_pk}'


def exam_is_unlocked(user_pk, exam_pk):
    return bool(cache.get(_unlock_key(user_pk, exam_pk)))


def mark_exam_unlocked(user_pk, exam_pk):
    cache.set(_unlock_key(user_pk, exam_pk), True, timeout=UNLOCK_TTL)
    cache.delete(_failures_key(user_pk, exam_pk))


def clear_exam_unlocked(user_pk, exam_pk):
    cache.delete(_unlock_key(user_pk, exam_pk))


def too_many_failures(user_pk, exam_pk):
    return (cache.get(_failures_key(user_pk, exam_pk)) or 0) >= MAX_FAILURES


def record_failure(user_pk, exam_pk):
    key = _failures_key(user_pk, exam_pk)
    if not cache.add(key, 1, timeout=FAILURE_WINDOW):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=FAILURE_WINDOW)
