"""
Usage:
    python manage.py seed_cambridge                        # data/cambridge/ dagi barcha JSON fayllarni yuklaydi
    python manage.py seed_cambridge --file data/cambridge/test1.json
    python manage.py seed_cambridge --clear                # mavjud cambridge examlarni o'chirib qayta yuklaydi
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exams.models import Exam, Section, Question


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
        base_dir = Path(__file__).resolve().parents[4] / 'abexam.uz'
        if not base_dir.exists():
            base_dir = Path(__file__).resolve().parents[4]
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

                # Questions
                existing_q_ids = []
                for q_data in sec_data.get('questions', []):
                    q, _ = Question.objects.update_or_create(
                        section=section,
                        order=q_data.get('order', 1),
                        defaults={
                            'text': q_data['text'],
                            'question_type': q_data.get('question_type', 'gap_fill'),
                            'correct_answer': q_data.get('correct_answer', ''),
                            'options': q_data.get('options', []),
                            'explanation': q_data.get('explanation', ''),
                            'word_limit': q_data.get('word_limit', 0),
                        },
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
