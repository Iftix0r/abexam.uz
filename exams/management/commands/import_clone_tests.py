"""
Clone_Testlar papkasidagi JSON eksport fayllarini bazaga yuklaydi.

Usage:
    python manage.py import_clone_tests
    python manage.py import_clone_tests --file "Clone_Testlar/Test 1_export.json"
    python manage.py import_clone_tests --clear   # mavjud import testlarni o'chirib qayta yuklaydi
"""
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exams.models import Exam, Section, Question

BLOCK_TYPE_TO_QUESTION_TYPE = {
    'shared_completion': 'gap_fill',
    'shared_completion_with_choice': 'gap_fill',
    'table_completion': 'gap_fill',
    'listening_multiple_choice': 'mcq',
    'reading_multiple_choice': 'mcq',
    'multiple_choice_limited': 'mcq',
    'true_false_not_given': 'tfng',
    'yes_no_not_given': 'tfng',
    'matching_headings': 'matching',
    'matching_sentence_endings': 'matching',
    'matching_information': 'matching',
    'listening_matching': 'matching',
    'graph_description': 'writing_task',
    'essay': 'writing_task',
}


def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML converter (no external lib needed)."""
    if not text:
        return ''
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Paragraph breaks
    paragraphs = text.split('\n\n')
    html_parts = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if para.startswith('[') and para.endswith(']'):
            # Drophere markers like [A-drophere] → anchor
            html_parts.append(f'<p class="passage-marker">{para}</p>')
        else:
            lines = para.split('\n')
            html_parts.append('<p>' + '<br>'.join(lines) + '</p>')
    return '\n'.join(html_parts)


def _build_listening_content(section_data: dict) -> tuple[str, str | None]:
    """Returns (html_content, audio_url) for a listening section."""
    content_parts = []
    audio_url = None

    if section_data.get('instructions'):
        content_parts.append(f'<p><em>{section_data["instructions"]}</em></p>')

    for part in section_data.get('parts', []):
        content_parts.append(f'<h4>{part["title"]}</h4>')
        for cb in part.get('content_blocks', []):
            if cb['content_type'] == 'audio' and not audio_url:
                audio_url = cb.get('file_url')
                content_parts.append(f'<p><em>{cb.get("title", "Listening Audio")}</em></p>')
            elif cb['content_type'] == 'text' and cb.get('text_content'):
                content_parts.append(_md_to_html(cb['text_content']))

    return '\n'.join(content_parts), audio_url


def _build_reading_content(section_data: dict) -> str:
    """Returns combined HTML for all reading passages."""
    content_parts = []

    for part in section_data.get('parts', []):
        content_parts.append(f'<h3 class="passage-title">{part["title"]}</h3>')
        for cb in part.get('content_blocks', []):
            if cb['content_type'] == 'text' and cb.get('text_content'):
                content_parts.append(_md_to_html(cb['text_content']))

    return '\n'.join(content_parts)


def _build_writing_content(section_data: dict) -> tuple[str, str | None]:
    """Returns (html_content, image_url) for writing section."""
    content_parts = []
    image_url = None

    for part in section_data.get('parts', []):
        content_parts.append(f'<h4>{part["title"]}</h4>')
        for cb in part.get('content_blocks', []):
            if cb['content_type'] == 'image' and not image_url:
                image_url = cb.get('file_url')
            elif cb['content_type'] == 'text' and cb.get('text_content'):
                content_parts.append(_md_to_html(cb['text_content']))

    return '\n'.join(content_parts), image_url


def _collect_questions(section_data: dict) -> list[dict]:
    """Flattens all parts → question_blocks → questions into ordered list."""
    questions = []
    for part in section_data.get('parts', []):
        part_title = part.get('title', '')
        for qb in part.get('question_blocks', []):
            block_type = qb.get('block_type', 'gap_fill')
            q_type = BLOCK_TYPE_TO_QUESTION_TYPE.get(block_type, 'gap_fill')
            instructions = qb.get('instructions', '')
            qb_title = qb.get('title', '')

            for i, q in enumerate(qb.get('questions', [])):
                q_text = q.get('question_text', '').strip()

                # Prefix first question in block with block instructions
                if i == 0 and (instructions or qb_title):
                    prefix_parts = []
                    if qb_title:
                        prefix_parts.append(f'[{qb_title}]')
                    if instructions:
                        prefix_parts.append(instructions)
                    prefix = ' | '.join(prefix_parts)
                    q_text = f'{prefix}\n{q_text}' if q_text else prefix

                q_num = q.get('question_number', q.get('order', 1))
                if q_type == 'writing_task':
                    word_limit = 250 if q_num >= 2 else 150
                else:
                    word_limit = 0

                questions.append({
                    'order': q_num,
                    'text': q_text,
                    'question_type': q_type,
                    'correct_answer': q.get('correct_answer', ''),
                    'options': q.get('options', []),
                    'word_limit': word_limit,
                    'part_title': part_title,
                })

    questions.sort(key=lambda x: x['order'])
    return questions


class Command(BaseCommand):
    help = "Clone_Testlar JSON eksportlarini bazaga yuklaydi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default=None,
            help='Bitta JSON fayl yo\'li',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Yuklashdan oldin mavjud [import] testlarni o\'chiradi',
        )
        parser.add_argument(
            '--skip-duplicates', action='store_true', default=True,
            help='Bir xil nomli testlarni o\'tkazib yuboradi (default: True)',
        )

    def handle(self, *args, **options):
        base_dir = Path(__file__).resolve().parents[4]
        clone_dir = base_dir / 'Clone_Testlar'

        if options['file']:
            path = Path(options['file'])
            if not path.is_absolute():
                path = base_dir / options['file']
            files = [path]
        else:
            if not clone_dir.exists():
                raise CommandError(f"Clone_Testlar papkasi topilmadi: {clone_dir}")
            all_files = sorted(clone_dir.glob('*.json'))
            # Dublikatlarni o'tkazib yuborish (Copy of... va (1), (2) versiyalar)
            seen_titles = {}
            files = []
            for f in all_files:
                if 'Copy of' in f.name:
                    self.stdout.write(f"  ⏭ O'tkazildi (copy): {f.name}")
                    continue
                try:
                    with open(f, encoding='utf-8') as fh:
                        data = json.load(fh)
                    title = data.get('title', f.stem)
                    if title in seen_titles:
                        self.stdout.write(f"  ⏭ O'tkazildi (dublikat '{title}'): {f.name}")
                        continue
                    seen_titles[title] = f
                    files.append(f)
                except Exception as e:
                    self.stderr.write(f"  XATO {f.name}: {e}")

        if not files:
            raise CommandError("Import qilinadigan JSON fayl topilmadi.")

        if options['clear']:
            deleted, _ = Exam.objects.filter(description__startswith='[import]').delete()
            self.stdout.write(self.style.WARNING(f"  {deleted} ta mavjud test o'chirildi"))

        total = 0
        for path in files:
            try:
                count = self._import_file(path)
                total += count
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  XATO {path.name}: {e}"))
                import traceback
                self.stderr.write(traceback.format_exc())

        self.stdout.write(self.style.SUCCESS(f"\n✓ Jami {total} ta test import qilindi"))

    @transaction.atomic
    def _import_file(self, path: Path) -> int:
        self.stdout.write(f"\n→ {path.name} o'qilmoqda...")
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        title = data.get('title', path.stem)
        description = '[import] ' + data.get('description', 'IELTS amaliyot testi')

        exam, created = Exam.objects.update_or_create(
            title=title,
            description=description,
            defaults={
                'exam_type': 'mock',
                'duration_minutes': 170,
                'is_active': True,
            },
        )
        action = 'yaratildi' if created else 'yangilandi'

        section_order = 0
        total_questions = 0

        for sec_data in data.get('sections', []):
            section_type = sec_data.get('section_type', 'listening')
            section_order += 1

            # Build content and collect questions based on section type
            if section_type == 'listening':
                content, audio_url = _build_listening_content(sec_data)
                image_url = None
                extra = {'audio_url': audio_url} if audio_url else {}
            elif section_type == 'reading':
                content = _build_reading_content(sec_data)
                audio_url = None
                image_url = None
                extra = {}
            elif section_type == 'writing':
                content, image_url = _build_writing_content(sec_data)
                audio_url = None
                extra = {'image_url': image_url} if image_url else {}
            else:
                content = ''
                audio_url = None
                image_url = None
                extra = {}

            section, _ = Section.objects.update_or_create(
                exam=exam,
                order=section_order,
                defaults={
                    'title': sec_data.get('title', section_type.capitalize()),
                    'section_type': section_type,
                    'content': content,
                    'duration_minutes': sec_data.get('duration_minutes', 0),
                    'extra_data': extra if extra else None,
                },
            )

            # Create questions
            questions_data = _collect_questions(sec_data)
            existing_q_ids = []
            for q_data in questions_data:
                q, _ = Question.objects.update_or_create(
                    section=section,
                    order=q_data['order'],
                    defaults={
                        'text': q_data['text'],
                        'question_type': q_data['question_type'],
                        'correct_answer': q_data['correct_answer'],
                        'options': q_data['options'],
                        'word_limit': q_data['word_limit'],
                    },
                )
                existing_q_ids.append(q.pk)

            # Eski savollarni o'chirish
            section.questions.exclude(pk__in=existing_q_ids).delete()
            total_questions += len(questions_data)

        # Eski sectionlarni o'chirish
        exam.sections.exclude(
            order__in=range(1, section_order + 1)
        ).delete()

        self.stdout.write(
            f"  {'✓' if created else '↻'} [{action}] {title} "
            f"— {section_order} bo'lim, {total_questions} savol"
        )
        return 1
