"""Hourly test passwords.

Each site exam — and each TESTLAR set (/testlar/<n>/) — has a 6-digit
password that changes every hour, on the hour. Nothing is stored: the
password is derived from SECRET_KEY, what it opens and the current hour, so
the panel and the test pages always agree without a cron job or a table to
keep in sync. The invigilator reads it in the panel and tells it to the
students in the room; a student who enters it is let in.
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
# Covers sitting on the test page for the whole attempt (and reloads during
# it); submitting a site exam clears it, so a retake needs a fresh password.
UNLOCK_TTL = 6 * 3600
# Wrong guesses per user per test before a short lockout — 6 digits are too
# few to leave unthrottled.
MAX_FAILURES = 5
FAILURE_WINDOW = 10 * 60


def exam_scope(exam_pk):
    return f'exam-password:{exam_pk}'


def testlar_scope(folder):
    return f'testlar-password:{folder}'


def _slot(now=None):
    return int((time.time() if now is None else now) // ROTATION_SECONDS)


def scope_password(scope, now=None, slot=None):
    slot = _slot(now) if slot is None else slot
    digest = hmac.new(settings.SECRET_KEY.encode(), f'{scope}:{slot}'.encode(), hashlib.sha256).digest()
    return f'{int.from_bytes(digest[:8], "big") % 1_000_000:06d}'


def exam_password(exam_pk, now=None):
    return scope_password(exam_scope(exam_pk), now=now)


def testlar_password(folder, now=None):
    return scope_password(testlar_scope(folder), now=now)


def seconds_until_rotation(now=None):
    now = time.time() if now is None else now
    return int(ROTATION_SECONDS - now % ROTATION_SECONDS)


def check_password(scope, entered, now=None):
    entered = ''.join(ch for ch in str(entered) if ch.isdigit())
    if len(entered) != 6:
        return False
    now = time.time() if now is None else now
    slot = _slot(now)
    candidates = [scope_password(scope, slot=slot)]
    if now % ROTATION_SECONDS < GRACE_SECONDS:
        candidates.append(scope_password(scope, slot=slot - 1))
    return any(hmac.compare_digest(entered, c) for c in candidates)


def check_exam_password(exam_pk, entered, now=None):
    return check_password(exam_scope(exam_pk), entered, now=now)


def _unlock_key(user_pk, scope):
    return f'unlocked_{user_pk}_{scope}'.replace(':', '_')


def _failures_key(user_pk, scope):
    return f'pw_fail_{user_pk}_{scope}'.replace(':', '_')


def is_unlocked(user_pk, scope):
    return bool(cache.get(_unlock_key(user_pk, scope)))


def mark_unlocked(user_pk, scope):
    cache.set(_unlock_key(user_pk, scope), True, timeout=UNLOCK_TTL)
    cache.delete(_failures_key(user_pk, scope))


def clear_unlocked(user_pk, scope):
    cache.delete(_unlock_key(user_pk, scope))


def too_many_failures(user_pk, scope):
    return (cache.get(_failures_key(user_pk, scope)) or 0) >= MAX_FAILURES


def record_failure(user_pk, scope):
    key = _failures_key(user_pk, scope)
    if not cache.add(key, 1, timeout=FAILURE_WINDOW):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=FAILURE_WINDOW)


def try_unlock(user_pk, scope, entered):
    """Checks a submitted password, with the lockout. Returns None when it
    unlocked, otherwise the error message to show."""
    if too_many_failures(user_pk, scope):
        return "Juda ko'p noto'g'ri urinish. 10 daqiqadan keyin qayta urinib ko'ring."
    if not check_password(scope, entered):
        record_failure(user_pk, scope)
        return "Test paroli noto'g'ri. Parolni nazoratchidan so'rang."
    mark_unlocked(user_pk, scope)
    return None


def password_required_for(user):
    """Staff (invigilators) are never asked; otherwise it follows the site
    setting."""
    from core.models import SiteSettings
    return not user.is_staff and SiteSettings.get().exam_password_required


# Site-exam shorthands.
def exam_is_unlocked(user_pk, exam_pk):
    return is_unlocked(user_pk, exam_scope(exam_pk))


def mark_exam_unlocked(user_pk, exam_pk):
    mark_unlocked(user_pk, exam_scope(exam_pk))


def clear_exam_unlocked(user_pk, exam_pk):
    clear_unlocked(user_pk, exam_scope(exam_pk))
