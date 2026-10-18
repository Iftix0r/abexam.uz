"""Exam camera proctoring.

While a student sits an exam, the exam page sends a small JPEG frame from
their webcam every few seconds; staff watch them on the panel's live page.
Only the latest frame of each attempt is kept, in the cache, for a couple of
minutes — nothing is recorded or stored long-term. When a staff member opens
one student's camera, that student's page is told to send frames every
second instead, which makes the view close to live video while keeping
traffic low for everyone else (shared hosting, plain HTTP — no streaming
server needed).
"""
import re
import time

from django.core.cache import cache

MAX_FRAME_BYTES = 200 * 1024
FRAME_TTL = 120
# A frame older than this means the camera (or the page) stopped.
FRESH_SECONDS = 30
IDLE_INTERVAL_MS = 5000
WATCHED_INTERVAL_MS = 1000
WATCH_TTL = 8


def _key(prefix, user_pk, exam_pk, client_id):
    client_id = re.sub(r'[^A-Za-z0-9_-]', '', str(client_id))[:64]
    return f'{prefix}_{user_pk}_{exam_pk}_{client_id}'


def store_frame(user_pk, exam_pk, client_id, jpeg):
    cache.set(_key('camframe', user_pk, exam_pk, client_id), {'jpg': jpeg, 'at': time.time()}, timeout=FRAME_TTL)


def latest_frame(user_pk, exam_pk, client_id):
    """(jpeg bytes, age in seconds) of the latest fresh frame, or None."""
    frame = cache.get(_key('camframe', user_pk, exam_pk, client_id))
    if not frame:
        return None
    age = time.time() - frame['at']
    return (frame['jpg'], age) if age <= FRESH_SECONDS else None


def mark_watched(user_pk, exam_pk, client_id):
    cache.set(_key('camwatch', user_pk, exam_pk, client_id), True, timeout=WATCH_TTL)


def next_interval_ms(user_pk, exam_pk, client_id):
    watched = cache.get(_key('camwatch', user_pk, exam_pk, client_id))
    return WATCHED_INTERVAL_MS if watched else IDLE_INTERVAL_MS


def looks_like_jpeg(data):
    return len(data) > 4 and data[:3] == b'\xff\xd8\xff'
