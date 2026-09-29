"""
Usage:
    python manage.py seed_cambridge                        # data/cambridge/ dagi barcha JSON fayllarni yuklaydi
    python manage.py seed_cambridge --file data/cambridge/test1.json
    python manage.py seed_cambridge --clear                # mavjud cambridge examlarni o'chirib qayta yuklaydi
"""
import json
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exams.models import Exam, Section, Question


def _same_file(field_file, src: Path) -> bool:
    if not field_file:
        return False
    try:
        with field_file.open('rb') as fh:
            return fh.read() == src.read_bytes()
    except FileNotFoundError:
        return False


class Command(BaseCommand):
    help = "Cambridge IELTS JSON fayllarini bazaga yuklaydi (seed data)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default=None,
            help='Bitta JSON fayl yo\'li (bo\'sh qoldirilsa data/cambridge/ dagi hammasini oladi)',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Yuklashdan oldin mavjud cambridge examlarni o\'chiradi',
        )

    def handle(self, *args, **options):
        # The project root itself — not a guess from the parent folder's
        # name: on the server the repo lives in ~/examab while an unrelated
        # ~/abexam.uz also exists, which the old guess resolved to instead.
        base_dir = Path(settings.BASE_DIR)
        data_dir = base_dir / 'data' / 'cambridge'

        if options['file']:
            files = [Path(options['file'])]
            if not files[0].is_absolute():
                files = [base_dir / options['file']]
        else:
            files = sorted(data_dir.glob('*.json'))

        if not files:
            raise CommandError(f"JSON fayllar topilmadi: {data_dir}")

        if options['clear']:
            deleted, _ = Exam.objects.filter(description__startswith='[cambridge]').delete()
            self.stdout.write(self.style.WARNING(f"  {deleted} ta exam o'chirildi"))

        total_exams = 0
        for path in files:
            try:
                count = self._load_file(path)
                total_exams += count
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  XATO {path.name}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\n✓ Jami {total_exams} ta exam yuklandi"))

    @transaction.atomic
    def _load_file(self, path: Path) -> int:
        self.stdout.write(f"\n→ {path.name} o'qilmoqda...")
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        exams_data = data if isinstance(data, list) else [data]
        count = 0

        for exam_data in exams_data:
            title = exam_data.get('title', path.stem)
            description = '[cambridge] ' + exam_data.get('description', '')

            exam, created = Exam.objects.update_or_create(
                title=title,
                defaults={
                    'description': description,
                    'exam_type': exam_data.get('exam_type', 'mock'),
                    'price': exam_data.get('price', 0),
                    'duration_minutes': exam_data.get('duration_minutes', 170),
                    'is_active': exam_data.get('is_active', True),
                },
            )
            action = 'yaratildi' if created else 'yangilandi'

            # Sections
            existing_section_ids = []
            for sec_data in exam_data.get('sections', []):
                section, _ = Section.objects.update_or_create(
                    exam=exam,
                    order=sec_data.get('order', 1),
                    defaults={
                        'title': sec_data['title'],
                        'section_type': sec_data['section_type'],
                        'content': sec_data.get('content', ''),
                        'duration_minutes': sec_data.get('duration_minutes', 0),
                    },
                )
                existing_section_ids.append(section.pk)
                self._attach_media(section, sec_data, path.parent)

                # Questions
                existing_q_ids = []
                for q_data in sec_data.get('questions', []):
                    defaults = {
                        'text': q_data['text'],
                        'question_type': q_data.get('question_type', 'gap_fill'),
                        'correct_answer': q_data.get('correct_answer', ''),
                        'options': q_data.get('options', []),
                        'explanation': q_data.get('explanation', ''),
                        'word_limit': q_data.get('word_limit', 0),
                    }
                    # Only when the JSON carries one — never blank out a
                    # model answer added later through the panel.
                    if q_data.get('model_answer'):
                        defaults['model_answer'] = q_data['model_answer']
                    q, _ = Question.objects.update_or_create(
                        section=section,
                        order=q_data.get('order', 1),
                        defaults=defaults,
                    )
                    existing_q_ids.append(q.pk)

                # Eski savollarni o'chirish
                section.questions.exclude(pk__in=existing_q_ids).delete()

            q_total = sum(
                s.questions.count()
                for s in exam.sections.filter(pk__in=existing_section_ids)
            )
            self.stdout.write(
                f"  {'✓' if created else '↻'} [{action}] {title} "
                f"— {len(exam_data.get('sections', []))} bo'lim, {q_total} savol"
            )
            count += 1

        return count

    def _attach_media(self, section, sec_data, json_dir: Path):
        """Optional per-section media:
        - "image": path relative to the JSON file (e.g. a Writing Task 1 chart)
        - "audio_url": Listening audio, downloaded once — skipped on re-runs
          while the section already holds audio from that same URL."""
        image = sec_data.get('image')
        if image:
            src = json_dir / image
            if not src.exists():
                raise CommandError(f"Rasm topilmadi: {src}")
            # Re-runs keep an identical uploaded copy instead of piling up
            # renamed duplicates (name_AbC123.png) in media/, but still pick
            # up an edited image.
            if not _same_file(section.image, src):
                if section.image:
                    section.image.delete(save=False)
                with open(src, 'rb') as fh:
                    section.image.save(src.name, File(fh), save=True)

        # "question_images": {"16": "images/plan.png"} — a map/plan shown
        # above the questions starting at that number (see TakeExamView).
        question_images = sec_data.get('question_images')
        if question_images:
            stored = {}
            for order, rel_path in question_images.items():
                src = json_dir / rel_path
                if not src.exists():
                    raise CommandError(f"Rasm topilmadi: {src}")
                name = f'exams/images/{src.name}'
                if default_storage.exists(name) and src.read_bytes() != default_storage.open(name).read():
                    default_storage.delete(name)
                if not default_storage.exists(name):
                    with open(src, 'rb') as fh:
                        name = default_storage.save(name, File(fh))
                stored[str(order)] = name
            section.extra_data = {**(section.extra_data or {}), 'question_images': stored}
            section.save(update_fields=['extra_data'])

        audio_url = sec_data.get('audio_url')
        if not audio_url:
            return
        extra = section.extra_data or {}
        if section.audio_file and extra.get('audio_url') == audio_url:
            return
        self.stdout.write(f"  ↓ Audio yuklanmoqda: {audio_url}")
        name = Path(unquote(urlparse(audio_url).path)).name or 'listening.mp3'
        with requests.get(audio_url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            with tempfile.TemporaryFile() as tmp:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    tmp.write(chunk)
                tmp.seek(0)
                section.audio_file.save(name, File(tmp), save=False)
        section.extra_data = {**extra, 'audio_url': audio_url}
        section.save(update_fields=['audio_file', 'extra_data'])
