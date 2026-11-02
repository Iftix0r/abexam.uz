"""Result sheet as a PDF, built on the server (Telegram bot «📄 PDF» button;
the site page makes its own PDF in the browser)."""
import io
from pathlib import Path

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from .models import UserResult

# DejaVu covers Uzbek Latin (oʻ, gʻ) and Cyrillic names; the built-in PDF
# fonts don't.
_FONTS = Path(__file__).resolve().parent / 'fonts'
pdfmetrics.registerFont(TTFont('DejaVu', str(_FONTS / 'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVu-Bold', str(_FONTS / 'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('DejaVu', normal='DejaVu', bold='DejaVu-Bold')

RED = colors.HexColor('#d32f2f')
MUTED = colors.HexColor('#6b6b73')
LINE = colors.HexColor('#e4e4e8')

SECTIONS = (('listening', 'Listening'), ('reading', 'Reading'), ('writing', 'Writing'), ('speaking', 'Speaking'))


def _style(name, size=10, font='DejaVu', color=colors.black, **kw):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=size * 1.35, textColor=color, **kw)


def _section_counts(result):
    """{section_type: (correct, total)} for the auto-graded questions."""
    rows = (result.answers.filter(question__isnull=False).exclude(question__question_type='writing_task')
            .values('question__section__section_type')
            .annotate(correct=Count('id', filter=Q(is_correct=True)), total=Count('id')))
    return {r['question__section__section_type']: (r['correct'], r['total']) for r in rows}


def result_pdf(result: UserResult) -> bytes:
    from .views import band_label

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f'AbExam — {result.exam.title}', author='AbExam.uz')
    user = result.user
    site = settings.SITE_URL.rstrip('/')
    story = []

    head = Table([[Paragraph('Ab<font color="#d32f2f">Exam</font>.uz', _style('logo', 20, 'DejaVu-Bold')),
                   Paragraph('IELTS Mock imtihon natijasi<br/><font size="8" color="#6b6b73">Mock Test Report</font>',
                             _style('h', 11, 'DejaVu-Bold', alignment=2))]],
                 colWidths=[80 * mm, None])
    head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                              ('LINEBELOW', (0, 0), (-1, 0), 2, RED), ('BOTTOMPADDING', (0, 0), (-1, 0), 8)]))
    story += [head, Spacer(1, 8 * mm)]

    label, value = _style('l', 8.5, color=MUTED), _style('v', 11, 'DejaVu-Bold')
    info = [
        ('Nomzod / Candidate', user.display_name),
        ('Imtihon / Test', result.exam.title),
        ('Sana / Date', timezone.localtime(result.completed_at).strftime('%d.%m.%Y')),
        ('Natija raqami / Result ID', f'#{result.pk}'),
    ]
    info_table = Table([[Paragraph(escape(k), label), Paragraph(escape(str(v)), value)] for k, v in info],
                       colWidths=[52 * mm, None])
    info_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))

    overall = Table([[Paragraph('OVERALL BAND', _style('ob', 9, 'DejaVu-Bold', colors.white, alignment=1))],
                     [Paragraph(f'{result.score:.1f}', _style('obv', 34, 'DejaVu-Bold', colors.white, alignment=1))],
                     [Paragraph(escape(band_label(result.score)), _style('obl', 9, color=colors.white, alignment=1))]],
                    colWidths=[45 * mm], rowHeights=[8 * mm, 16 * mm, 8 * mm])
    overall.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), RED), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                 ('ROUNDEDCORNERS', [6, 6, 6, 6])]))
    top = Table([[info_table, overall]], colWidths=[None, 48 * mm])
    top.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
    story += [top, Spacer(1, 8 * mm)]

    counts = _section_counts(result)
    th = _style('th', 9, 'DejaVu-Bold', MUTED)
    rows = [[Paragraph("Bo'lim / Section", th), Paragraph("To'g'ri javoblar / Correct", th), Paragraph('Band', th)]]
    for key, name in SECTIONS:
        band = getattr(result, f'{key}_score')
        correct = counts.get(key)
        rows.append([Paragraph(name, _style('td', 11, 'DejaVu-Bold')),
                     Paragraph(f'{correct[0]} / {correct[1]}' if correct and correct[1] else '—', _style('td2', 11)),
                     Paragraph(f'{band:.1f}' if band else '—', _style('tb', 13, 'DejaVu-Bold', RED))])
    table = Table(rows, colWidths=[60 * mm, None, 30 * mm])
    table.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), 0.6, LINE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    story += [table, Spacer(1, 8 * mm)]

    fb = result.writing_feedback or {}
    if fb.get('tasks'):
        story.append(Paragraph('Writing bahosi', _style('wh', 12, 'DejaVu-Bold')))
        story.append(Spacer(1, 3 * mm))
        criteria = (('task_achievement', 'TA'), ('coherence_cohesion', 'CC'),
                    ('lexical_resource', 'LR'), ('grammatical_accuracy', 'GA'))
        for i, task in enumerate(fb['tasks'], 1):
            marks = ' · '.join(f'{short} {task[k]:.1f}' for k, short in criteria if task.get(k))
            line = f"<b>Task {task.get('task_num') or i}</b> — band {float(task.get('band') or 0):.1f}"
            if marks:
                line += f'  <font color="#6b6b73">({marks})</font>'
            story.append(Paragraph(line, _style('wt', 10)))
            if task.get('feedback'):
                story.append(Paragraph(escape(str(task['feedback'])[:900]).replace('\n', '<br/>'),
                                       _style('wf', 9, color=MUTED, leftIndent=4 * mm)))
            story.append(Spacer(1, 3 * mm))

    story += [Spacer(1, 6 * mm), Paragraph(
        f"Saytda ko'rish: {site}/exams/result/{result.pk}/<br/>"
        "Bu AbExam.uz mock imtihon natijasi, rasmiy IELTS sertifikati emas. "
        "This is a practice (mock) test report, not an official IELTS Test Report Form.<br/>"
        f"Yaratilgan: {timezone.localtime():%d.%m.%Y %H:%M}", _style('foot', 8, color=MUTED))]

    doc.build(story)
    return buf.getvalue()
