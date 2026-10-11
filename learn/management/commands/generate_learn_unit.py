"""
AI yordamida yangi bo'lim (unit) darslarini yaratadi va data/learn/ ga JSON qilib yozadi.
Fayl tekshirib chiqilgach git'ga qo'shiladi — deploy'dan keyin saytda avtomatik paydo bo'ladi.

    python manage.py generate_learn_unit --level B1 --topic "Health and fitness" --lessons 3
    python manage.py generate_learn_unit --level A2 --topic "Shopping for clothes" --grammar "comparatives"
"""
import json
import re

from django.core.management.base import BaseCommand, CommandError

from core.ai_utils import client
from learn.content import LEVELS, content_dir, get_course, validate_lesson

PROMPT = """You are an expert EFL course designer writing lessons for Uzbek-speaking learners at CEFR {level}.
Methodology: comprehensible input first (a realistic dialogue or short text), then grammar noticing with a
short Uzbek explanation that targets typical mistakes of Uzbek speakers, then varied active-recall practice,
then speaking and a short writing task.

Create ONE unit about "{topic}" with {count} lessons.{grammar}
All Uzbek text must be natural Uzbek (Latin script, use ' for o' and g'). English must be natural, British spelling.

Return ONLY JSON with this exact shape:
{{"slug": "<{level_lc}-kebab-unit-slug>", "title": "<English>", "title_uz": "<Uzbek>", "icon": "<a lucide icon name>",
  "lessons": [<lesson>, ...]}}

Each <lesson> follows EXACTLY the format of this example (same keys and step types; new content):
{example}

Rules for each lesson:
- "slug" unique, starts with "{level_lc}-"; 8 words; steps in this order: words, dialogue or reading, 2 comprehension "choice"
  steps, grammar, then 8-10 practice steps mixing choice, gap, order, match, listen, translate (at least one "choice" with
  "audio": true and a "say" field), then 1 speak, then 1 write (with "example").
- "gap": "text" contains exactly one ___ ; "answer" is a list of accepted answers.
- "order": "answer" uses exactly the words in "words" (same tokens, no extra punctuation).
- "choice": "answer" is the 0-based index of the correct option.
- "translate": "answer" lists several natural correct translations."""


class Command(BaseCommand):
    help = "AI bilan ingliz tili kursi uchun yangi bo'lim (unit) yaratadi"

    def add_arguments(self, parser):
        parser.add_argument('--level', required=True, choices=LEVELS)
        parser.add_argument('--topic', required=True)
        parser.add_argument('--lessons', type=int, default=3)
        parser.add_argument('--grammar', default='', help="Ixtiyoriy: asosiy grammatika mavzusi")

    def handle(self, *args, **opts):
        level = opts['level']
        course = get_course()
        example = next((l for u in course['levels'][level]['units'] for l in u['lessons']), None) \
            or next(iter(course['lessons'].values()))
        prompt = PROMPT.format(
            level=level, level_lc=level.lower(), topic=opts['topic'], count=opts['lessons'],
            grammar=f" Main grammar focus: {opts['grammar']}." if opts['grammar'] else '',
            example=json.dumps({k: example[k] for k in ('slug', 'title', 'title_uz', 'goal_uz', 'minutes', 'words', 'steps')},
                               ensure_ascii=False),
        )
        self.stdout.write(f"AI {level} · \"{opts['topic']}\" bo'limini yozmoqda...")
        try:
            response = client.chat.completions.create(
                model='gpt-4o', messages=[{'role': 'user', 'content': prompt}],
                temperature=0.7, max_tokens=16000, response_format={'type': 'json_object'}, timeout=300,
            )
            unit = json.loads(response.choices[0].message.content)
        except Exception as e:
            raise CommandError(f"AI xatosi: {e}")

        errors = []
        for lesson in unit.get('lessons', []):
            if lesson.get('slug') in course['lessons']:
                lesson['slug'] = f"{lesson['slug']}-2"
            errors += validate_lesson(lesson)
        if not unit.get('lessons'):
            errors.append("Darslar yo'q")

        slug = re.sub(r'[^a-z0-9-]+', '-', unit.get('slug', opts['topic']).lower()).strip('-')
        number = len(list(content_dir().glob(f'{level}*.json'))) + 1
        path = content_dir() / f"{level}-{number:02d}-{slug}.json"
        if path.exists():
            raise CommandError(f"Fayl allaqachon bor: {path}")
        path.write_text(json.dumps({'level': level, 'units': [unit]}, ensure_ascii=False, indent=2), encoding='utf-8')

        if errors:
            self.stdout.write(self.style.WARNING("Tekshiruvda muammolar bor — faylni qo'lda tuzating:"))
            for e in errors:
                self.stdout.write(f"  - {e}")
        self.stdout.write(self.style.SUCCESS(
            f"Yozildi: {path} ({len(unit.get('lessons', []))} dars). "
            "Ko'rib chiqing, so'ng git'ga qo'shing."
        ))
