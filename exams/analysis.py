"""Answer-key tools: per-question statistics (which questions students get
wrong, and the same way), re-grading stored results after a key is fixed,
and a Telegram heads-up when a key looks wrong."""
import logging
import re
from collections import Counter, defaultdict
from itertools import groupby

from django.core.cache import cache
from django.db import transaction
from django.utils.html import escape

from .models import Section, UserAnswer, UserResult

logger = logging.getLogger(__name__)

ANALYSIS_TYPES = {'mcq', 'tfng', 'gap_fill', 'matching'}


def _answer_key(text):
    return re.sub(r'\s+', ' ', (text or '').strip()).lower()


def _answers_by_result(exam):
    by_result = defaultdict(dict)
    for result_id, qid, ans in (UserAnswer.objects.filter(result__exam=exam, question__isnull=False)
                                .values_list('result_id', 'question_id', 'user_answer')):
        by_result[result_id][qid] = ans
    return by_result


def question_stats(exam):
    """Per skill, per question: right / blank / wrong counts and the most
    common wrong answers — graded against the *current* key, so a key fixed
    in the panel shows up straight away. A question most students "get
    wrong" with the same answer is marked suspect (its key is likely wrong).
    Returns [{'label', 'rows'}]."""
    from .views import grade_answers

    sections = list(exam.sections.prefetch_related('questions').all())
    by_result = _answers_by_result(exam)
    groups = []
    for stype, group_iter in groupby(sections, key=lambda s: s.section_type):
        counter, rows = 0, []
        for section in group_iter:
            questions = list(section.questions.all())
            gradable = [q for q in questions if q.question_type in ANALYSIS_TYPES]
            stats = {q.id: {'right': 0, 'blank': 0, 'wrong': Counter(), 'shown': {}} for q in gradable}
            for answers in by_result.values():
                if not any(q.id in answers for q in gradable):
                    continue
                verdicts = grade_answers(gradable, lambda q: answers.get(q.id, ''))
                for q in gradable:
                    raw = (answers.get(q.id) or '').strip()
                    st = stats[q.id]
                    if verdicts[q.id]:
                        st['right'] += 1
                    elif not raw:
                        st['blank'] += 1
                    else:
                        key = _answer_key(raw)
                        st['wrong'][key] += 1
                        st['shown'].setdefault(key, raw)
            for q in questions:
                counter += 1
                if q.question_type not in ANALYSIS_TYPES:
                    continue
                st = stats[q.id]
                wrong_total = sum(st['wrong'].values())
                total = st['right'] + st['blank'] + wrong_total
                top = [(st['shown'][k], n) for k, n in st['wrong'].most_common(3)]
                pct = round(st['right'] * 100 / total) if total else None
                suspect = bool(total >= 5 and pct is not None and pct < 40 and top
                               and top[0][1] >= max(3, wrong_total * 0.5))
                rows.append({'q': q, 'number': counter, 'total': total, 'right': st['right'],
                             'blank': st['blank'], 'wrong': wrong_total, 'pct': pct,
                             'top_wrong': top, 'suspect': suspect})
        if rows:
            groups.append({'label': dict(Section.SECTION_TYPES).get(stype, stype), 'rows': rows})
    return groups


def regrade_exam(exam):
    """Re-marks every stored result of `exam` against the current answer
    key: each answer's is_correct, then the Listening/Reading bands and the
    overall band. Writing/Speaking bands (graded by staff) are kept.
    Returns (results checked, results whose band changed)."""
    from .views import calc_band, compute_overall_band, grade_answers, present_section_types

    sections = [s for s in exam.sections.prefetch_related('questions').all()
                if s.section_type in ('listening', 'reading')]
    present = present_section_types(exam)
    by_result = _answers_by_result(exam)
    rows = defaultdict(dict)
    for ua in UserAnswer.objects.filter(result__exam=exam, question__isnull=False):
        rows[ua.result_id][ua.question_id] = ua

    checked = changed = 0
    with transaction.atomic():
        for result in UserResult.objects.filter(exam=exam, pk__in=list(by_result)).select_for_update():
            answers = by_result[result.pk]
            counts, updates = defaultdict(lambda: [0, 0]), []
            for section in sections:
                questions = [q for q in section.questions.all() if q.question_type != 'writing_task']
                verdicts = grade_answers(questions, lambda q: answers.get(q.id, ''))
                for q in questions:
                    counts[section.section_type][1] += 1
                    counts[section.section_type][0] += verdicts[q.id]
                    ua = rows[result.pk].get(q.id)
                    if ua is not None and ua.is_correct != verdicts[q.id]:
                        ua.is_correct = verdicts[q.id]
                        updates.append(ua)
            UserAnswer.objects.bulk_update(updates, ['is_correct'])
            checked += 1
            l_band = calc_band(*counts['listening']) if 'listening' in counts else result.listening_score
            r_band = calc_band(*counts['reading']) if 'reading' in counts else result.reading_score
            if (l_band, r_band) == (result.listening_score, result.reading_score):
                continue
            result.listening_score, result.reading_score = l_band, r_band
            if not result.is_pending:
                result.score = compute_overall_band({
                    'listening': l_band, 'reading': r_band,
                    'writing': result.writing_score, 'speaking': result.speaking_score,
                }, present)
            result.save(update_fields=['listening_score', 'reading_score', 'score'])
            changed += 1
    return checked, changed


def alert_suspect_keys(exam):
    """Telegram heads-up for questions that newly look like they have a
    wrong key. Called after each submission; never raises."""
    from core.models import SiteSettings
    from core.utils import notify_admin_telegram
    try:
        if not SiteSettings.get().telegram_work_alerts:
            return
        suspects = [r for g in question_stats(exam) for r in g['rows'] if r['suspect']]
        cache_key = f'suspect_keys_alerted_{exam.pk}'
        alerted = cache.get(cache_key) or set()
        new = [r for r in suspects if r['q'].pk not in alerted]
        if not new:
            return
        lines = '\n'.join(
            f"• №{r['number']}: kalit <b>{escape(r['q'].correct_answer)}</b>, "
            f"ko'pchilik yozgan: <b>{escape(r['top_wrong'][0][0])}</b> ({r['top_wrong'][0][1]} ta)"
            for r in new[:8])
        notify_admin_telegram(f"⚠ <b>Kalitni tekshiring</b> — {escape(exam.title)}\n{lines}")
        cache.set(cache_key, alerted | {r['q'].pk for r in new}, 60 * 60 * 24 * 30)
    except Exception:
        logger.exception('suspect key alert failed for exam %s', exam.pk)
