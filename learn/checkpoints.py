"""Unit tests and level exams (Duolingo's checkpoints and "test out").

A test is a shuffled mix of exercises from every lesson it covers, played
in the normal lesson player without hints or second chances. Passing
(80%+) proves the material is learned; if some of its lessons weren't done
yet, they are marked done, so a learner who already knows them can skip ahead.
"""
import random

from django.db import transaction
from django.utils import timezone

from .content import LEVEL_INFO, LEVELS, get_course
from .models import Checkpoint, LessonProgress

PASS_MARK = 80
UNIT_SIZE = 12
LEVEL_SIZE = 20
UNIT_XP = 20
LEVEL_XP = 60
TEST_TYPES = {'choice', 'gap', 'order', 'translate', 'listen', 'match'}


def _unit(slug):
    for code in LEVELS:
        for unit in get_course()['levels'][code]['units']:
            if unit['slug'] == slug:
                return code, unit
    return None, None


def lessons_of(kind, key):
    """(title_uz, level code, lessons) of a unit or level, or None if unknown."""
    if kind == 'unit':
        code, unit = _unit(key)
        return (unit.get('title_uz', ''), code, unit['lessons']) if unit else None
    if kind == 'level' and key in LEVELS:
        lv = get_course()['levels'][key]
        lessons = [l for u in lv['units'] for l in u['lessons']]
        return (f"{key} — {LEVEL_INFO[key]['name']}", key, lessons) if lessons else None
    return None


def can_take(kind, key, done):
    """A unit test opens with the unit (its first lesson unlocked); a level exam is always open."""
    found = lessons_of(kind, key)
    if not found:
        return False
    if kind == 'level':
        return True
    first = found[2][0]
    return first['slug'] in done or not first.get('prev_slug') or first['prev_slug'] in done


def build(kind, key):
    """Exercises for one attempt: spread over all lessons, shuffled."""
    title, code, lessons = lessons_of(kind, key)
    rng = random.Random()
    pools = []
    for lesson in lessons:
        pool = [(lesson, i) for i, st in enumerate(lesson['steps'])
                if st.get('type') in TEST_TYPES and not st.get('needs_text')]
        rng.shuffle(pool)
        pools.append(pool)
    size = UNIT_SIZE if kind == 'unit' else LEVEL_SIZE
    picked = []
    # Round-robin so every lesson is represented before any repeats.
    while len(picked) < size and any(pools):
        for pool in pools:
            if pool and len(picked) < size:
                picked.append(pool.pop())
    rng.shuffle(picked)
    steps, words, seen = [], [], set()
    for lesson, idx in picked:
        steps.append(dict(lesson['steps'][idx], _src={'slug': lesson['slug'], 'idx': idx, 'mistake': False}))
        for w in lesson['words']:
            if w['en'] not in seen:
                seen.add(w['en'])
                words.append(w)
    return {'kind': kind, 'key': key, 'level': code, 'title_uz': title, 'steps': steps, 'words': words,
            'pass_mark': PASS_MARK}


@transaction.atomic
def finish(user, kind, key, served, results):
    """Score an attempt. `served` is the list of (slug, idx) actually shown."""
    from .content import get_lesson
    from .services import award_xp, record_mistakes

    served = [tuple(s) for s in served]
    left = set(served)
    right, wrong = 0, {}
    for r in results if isinstance(results, list) else []:
        if not isinstance(r, dict):
            continue
        pair = (str(r.get('slug', '')), r.get('step'))
        if pair not in left:
            continue
        left.discard(pair)
        if r.get('ok'):
            right += 1
        else:
            wrong.setdefault(pair[0], []).append(pair[1])
    score = round(right * 100 / len(served)) if served else 0
    passed = score >= PASS_MARK

    cp, _ = Checkpoint.objects.select_for_update().get_or_create(user=user, kind=kind, key=key)
    first_pass = passed and not cp.passed
    cp.attempts += 1
    cp.best_score = max(cp.best_score, score)
    if first_pass:
        cp.passed_at = timezone.now()
    cp.save()

    # Wrong answers come back in mixed practice, like mistakes in lessons.
    for slug, idxs in wrong.items():
        lesson = get_lesson(slug)
        if lesson:
            record_mistakes(user, lesson, idxs)

    tested_out = 0
    xp = 0
    if first_pass:
        _, _, lessons = lessons_of(kind, key)
        done = set(LessonProgress.objects.filter(user=user).values_list('lesson_slug', flat=True))
        new = [LessonProgress(user=user, lesson_slug=l['slug'], best_score=score, attempts=0)
               for l in lessons if l['slug'] not in done]
        LessonProgress.objects.bulk_create(new)
        tested_out = len(new)
        xp = UNIT_XP if kind == 'unit' else LEVEL_XP
    profile = award_xp(user, xp)
    return {'score': score, 'passed': passed, 'first_pass': first_pass, 'best_score': cp.best_score,
            'pass_mark': PASS_MARK, 'xp': xp, 'tested_out': tested_out, 'streak': profile.streak,
            'right': right, 'total': len(served)}


def status(user, done):
    """{(kind, key): {'state', 'score'}} for the learner's checkpoints."""
    rows = {(c.kind, c.key): c for c in Checkpoint.objects.filter(user=user)}
    out = {}
    for code in LEVELS:
        lv = get_course()['levels'][code]
        for unit in lv['units']:
            c = rows.get(('unit', unit['slug']))
            state = 'passed' if c and c.passed else ('open' if can_take('unit', unit['slug'], done) else 'locked')
            out[('unit', unit['slug'])] = {'state': state, 'score': c.best_score if c else None}
        c = rows.get(('level', code))
        out[('level', code)] = {'state': 'passed' if c and c.passed else 'open', 'score': c.best_score if c else None,
                                'passed_at': c.passed_at if c and c.passed else None}
    return out
