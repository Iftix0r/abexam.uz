"""Course content loader.

Lessons are plain JSON files in data/learn/ (one or more files per CEFR
level), so new material ships with a normal git deploy — no seeding step,
and progress is keyed by the lesson's stable `slug`.

File shape:
    {"level": "A1", "title_uz": "...", "order": 1,
     "units": [{"slug": "...", "title": "...", "title_uz": "...", "icon": "...",
                "lessons": [{"slug": "...", "title": "...", "title_uz": "...",
                             "goal_uz": "...", "minutes": 8,
                             "words": [{"en", "uz", "ipa", "ex"}],
                             "steps": [{"type": ...}, ...]}]}]}
"""
import json
import re
import threading
from pathlib import Path

from django.conf import settings

LEVELS = ['A1', 'A2', 'B1', 'B2']
LEVEL_INFO = {
    'A1': {'name': "Boshlang'ich", 'ielts': '—', 'desc': "Salomlashish, o'zingiz haqingizda, kundalik oddiy gaplar."},
    'A2': {'name': "Elementar", 'ielts': '3.0–3.5', 'desc': "Kundalik hayot, xarid, sayohat, o'tgan voqealar."},
    'B1': {'name': "O'rta", 'ielts': '4.0–5.0', 'desc': "Fikr bildirish, tajriba, rejalar, ish va o'qish."},
    'B2': {'name': "O'rtadan yuqori", 'ielts': '5.5–6.5', 'desc': "IELTS uchun akademik lug'at, bog'lovchilar, grafik tasvirlash."},
}

# Steps the player can render. Exercise steps count toward the lesson score.
INPUT_STEPS = {'words', 'dialogue', 'reading', 'grammar', 'tip'}
EXERCISE_STEPS = {'choice', 'gap', 'order', 'listen', 'match', 'translate', 'speak'}
PRODUCE_STEPS = {'write'}
STEP_TYPES = INPUT_STEPS | EXERCISE_STEPS | PRODUCE_STEPS

_lock = threading.Lock()
_cache = {'key': None, 'course': None}


def content_dir():
    return Path(settings.BASE_DIR) / 'data' / 'learn'


def _files():
    # A1.json comes first, then extra units of that level in name order
    # (A1-02-shopping.json, A1-03-...), so new files only ever append.
    def key(p):
        level, _, rest = p.stem.partition('-')
        return (level, rest != '', rest)
    return sorted(content_dir().glob('*.json'), key=key)


def _build(files):
    levels = {code: {'code': code, **LEVEL_INFO[code], 'units': []} for code in LEVELS}
    lessons = {}
    for path in files:
        data = json.loads(path.read_text(encoding='utf-8'))
        code = data.get('level')
        if code not in levels:
            continue
        for unit in data.get('units', []):
            unit = dict(unit, level=code, lessons=list(unit.get('lessons', [])))
            for i, lesson in enumerate(unit['lessons']):
                lesson = dict(lesson, level=code, unit_slug=unit['slug'], unit_title_uz=unit.get('title_uz', ''),
                              index=i, words=lesson.get('words', []), steps=lesson.get('steps', []))
                lesson['exercise_count'] = sum(1 for s in lesson['steps'] if s.get('type') in EXERCISE_STEPS)
                unit['lessons'][i] = lesson
                lessons[lesson['slug']] = lesson
            levels[code]['units'].append(unit)

    # Lessons open one after another across the whole level, so link them.
    for level in levels.values():
        flat = [l for u in level['units'] for l in u['lessons']]
        level['lesson_count'] = len(flat)
        for prev, nxt in zip([None] + flat[:-1], flat):
            nxt['prev_slug'] = prev['slug'] if prev else None
            if prev:
                prev['next_slug'] = nxt['slug']
        if flat:
            flat[-1].setdefault('next_slug', None)
    return {'levels': levels, 'lessons': lessons}


def get_course():
    files = _files()
    key = tuple((p.name, p.stat().st_mtime_ns) for p in files)
    with _lock:
        if _cache['key'] != key:
            _cache['course'] = _build(files)
            _cache['key'] = key
        return _cache['course']


def get_lesson(slug):
    return get_course()['lessons'].get(slug)


# ── Answer checking (mirrored in templates/learn/lesson.html) ─────────────
_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)


def normalize(text):
    text = (text or '').lower().replace('’', "'").replace('‘', "'")
    text = _PUNCT.sub(' ', text)
    return ' '.join(text.split())


def answer_matches(given, accepted):
    if isinstance(accepted, str):
        accepted = [accepted]
    g = normalize(given)
    return bool(g) and any(g == normalize(a) for a in accepted)


# ── Validation (used by tests and by the lesson generator) ───────────────
def validate_lesson(lesson):
    errors = []
    slug = lesson.get('slug') or '?'
    for field in ('slug', 'title', 'title_uz', 'steps'):
        if not lesson.get(field):
            errors.append(f"{slug}: '{field}' yo'q")
    for w in lesson.get('words', []):
        if not w.get('en') or not w.get('uz'):
            errors.append(f"{slug}: so'zda en/uz yo'q: {w}")
    for n, step in enumerate(lesson.get('steps', []), 1):
        t = step.get('type')
        where = f"{slug} #{n} ({t})"
        if t not in STEP_TYPES:
            errors.append(f"{where}: noma'lum qadam turi")
        elif t == 'choice':
            opts = step.get('options') or []
            if len(opts) < 2 or not isinstance(step.get('answer'), int) or not 0 <= step['answer'] < len(opts):
                errors.append(f"{where}: options/answer noto'g'ri")
        elif t in ('gap', 'translate', 'listen') and not step.get('answer'):
            errors.append(f"{where}: answer yo'q")
        elif t == 'gap' and '___' not in step.get('text', ''):
            errors.append(f"{where}: matnda ___ yo'q")
        elif t == 'order':
            answer = step.get('answer', '')
            if sorted(normalize(answer).split()) != sorted(normalize(' '.join(step.get('words', []))).split()):
                errors.append(f"{where}: words javob bilan mos emas")
        elif t == 'match' and len(step.get('pairs', [])) < 2:
            errors.append(f"{where}: kamida 2 juft kerak")
        elif t == 'speak' and not step.get('text'):
            errors.append(f"{where}: text yo'q")
        elif t == 'dialogue' and not step.get('lines'):
            errors.append(f"{where}: lines yo'q")
        elif t == 'reading' and not step.get('text'):
            errors.append(f"{where}: text yo'q")
    return errors


def validate_course():
    errors, seen = [], set()
    for path in _files():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except ValueError as e:
            errors.append(f"{path.name}: JSON xato: {e}")
            continue
        if data.get('level') not in LEVELS:
            errors.append(f"{path.name}: level noto'g'ri")
        for unit in data.get('units', []):
            for lesson in unit.get('lessons', []):
                if lesson.get('slug') in seen:
                    errors.append(f"{path.name}: takroriy slug {lesson.get('slug')}")
                seen.add(lesson.get('slug'))
                errors.extend(validate_lesson(lesson))
    return errors
