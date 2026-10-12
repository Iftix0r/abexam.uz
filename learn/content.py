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

LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
LEVEL_INFO = {
    'A1': {'name': "Boshlang'ich", 'ielts': '—', 'desc': "Salomlashish, o'zingiz haqingizda, kundalik oddiy gaplar."},
    'A2': {'name': "Elementar", 'ielts': '3.0–3.5', 'desc': "Kundalik hayot, xarid, sayohat, o'tgan voqealar."},
    'B1': {'name': "O'rta", 'ielts': '4.0–5.0', 'desc': "Fikr bildirish, tajriba, rejalar, ish va o'qish."},
    'B2': {'name': "O'rtadan yuqori", 'ielts': '5.5–6.5', 'desc': "IELTS uchun akademik lug'at, bog'lovchilar, grafik tasvirlash."},
    'C1': {'name': "Ilg'or", 'ielts': '7.0–8.0', 'desc': "IELTS 7+ uchun: murakkab grammatika, akademik uslub va idiomalar."},
    'C2': {'name': "Mukammal", 'ielts': '8.5–9.0', 'desc': "Ona tili darajasiga yaqin: nozik ma'no farqlari, uslub (register) va o'tmish haqida taxmin."},
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
                # Questions about the lesson's dialogue/text make no sense on
                # their own, so mixed practice skips them.
                after_text = False
                for st in lesson['steps']:
                    if st.get('type') in ('dialogue', 'reading'):
                        after_text = True
                    elif st.get('type') == 'grammar':
                        after_text = False
                    elif st.get('type') == 'choice' and after_text and not st.get('say'):
                        st['needs_text'] = True
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


# ── Placement test (data/learn/placement/test.json) ──────────────────────
def get_placement():
    path = content_dir() / 'placement' / 'test.json'
    return json.loads(path.read_text(encoding='utf-8'))


def placement_level(test, answers):
    """Start level = the first block not passed (all passed → the top level).

    `answers` maps block index (as str) to the list of chosen option indexes.
    """
    for i, block in enumerate(test['blocks']):
        chosen = answers.get(str(i)) or []
        right = sum(1 for q, a in zip(block['questions'], chosen) if a == q['answer'])
        if right < test.get('pass_mark', 4):
            return block['level']
    return test['blocks'][-1]['level']


# ── Graded reading stories (data/learn/stories/*.json) ───────────────────
_story_cache = {'key': None, 'stories': None}


def get_stories():
    """{slug: story}, ordered by level then file name."""
    files = sorted((content_dir() / 'stories').glob('*.json'))
    key = tuple((p.name, p.stat().st_mtime_ns) for p in files)
    with _lock:
        if _story_cache['key'] != key:
            stories = [json.loads(p.read_text(encoding='utf-8')) for p in files]
            stories.sort(key=lambda s: (LEVELS.index(s['level']) if s.get('level') in LEVELS else 9, s.get('order', 0)))
            _story_cache['stories'] = {s['slug']: s for s in stories}
            _story_cache['key'] = key
        return _story_cache['stories']


def validate_stories():
    errors = []
    for slug, s in get_stories().items():
        for field in ('title', 'title_uz', 'level', 'paragraphs', 'questions'):
            if not s.get(field):
                errors.append(f"{slug}: '{field}' yo'q")
        if s.get('level') not in LEVELS:
            errors.append(f"{slug}: level noto'g'ri")
        for p in s.get('paragraphs', []):
            if not p.get('en'):
                errors.append(f"{slug}: bo'sh abzats")
        for q in s.get('questions', []):
            if not 0 <= q.get('answer', -1) < len(q.get('options', [])):
                errors.append(f"{slug}: savol javobi noto'g'ri: {q.get('q')}")
    return errors
