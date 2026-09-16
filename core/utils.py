import json
import logging
import re
import threading
from datetime import date, timedelta

from django.conf import settings
from django.db.models.functions import TruncDate, TruncMonth
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_client_ip(request):
    # Reverse proxy appends the real client IP as the last hop (nginx's
    # $proxy_add_x_forwarded_for); earlier entries can be forged by the
    # client, so the first entry must not be trusted.
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def notify_admin_telegram(message: str):
    """Fire-and-forget Telegram notification to the admin chat.

    No-ops silently if TELEGRAM_BOT_TOKEN/TELEGRAM_ADMIN_CHAT_ID aren't
    configured, and never raises into the caller — a Telegram outage or
    misconfiguration must not break login/registration/logout for users.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_ADMIN_CHAT_ID
    if not token or not chat_id:
        return

    def _send():
        import requests
        try:
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'},
                timeout=5,
            )
        except requests.RequestException:
            logger.warning('Telegram admin notification failed', exc_info=True)

    threading.Thread(target=_send, daemon=True).start()


_IMAGE_TYPE_LABELS = {
    'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP', 'image/svg+xml': 'SVG',
}


def validate_image_upload(file, max_mb, allowed_types):
    """Validate an uploaded image's size and content type.

    Returns an Uzbek error message if invalid, or None if the file is OK.
    """
    if file.size > max_mb * 1024 * 1024:
        return f"Rasm hajmi {max_mb}MB dan oshmasligi kerak"
    if file.content_type not in allowed_types:
        names = ', '.join(_IMAGE_TYPE_LABELS.get(t, t) for t in allowed_types)
        return f"Faqat {names} formatlar qabul qilinadi"
    return None


_AUDIO_TYPE_LABELS = {
    'audio/webm': 'WEBM', 'audio/mp4': 'MP4', 'audio/mpeg': 'MP3', 'audio/ogg': 'OGG', 'audio/wav': 'WAV',
}


def validate_audio_upload(file, max_mb, allowed_types):
    """Validate an uploaded audio file's size and content type.

    Returns an Uzbek error message if invalid, or None if the file is OK.
    """
    if file.size > max_mb * 1024 * 1024:
        return f"Audio hajmi {max_mb}MB dan oshmasligi kerak"
    if file.content_type not in allowed_types:
        names = ', '.join(_AUDIO_TYPE_LABELS.get(t, t) for t in allowed_types)
        return f"Faqat {names} formatlar qabul qilinadi"
    return None


def text_to_html_paragraphs(text):
    """Turn plain text into `<p>`/`<br>` HTML — blank-line-separated blocks
    become paragraphs (matching how AI-generated section content is
    formatted, see core/ai_utils.py's passage_text.replace(chr(10),
    '</p><p>')), single line breaks within a block become `<br>`, and the
    text is HTML-escaped. Section.content is dropped into the take-exam
    template with |safe, so unescaped `<`/`&`/etc. in staff-typed text would
    otherwise break the page — django.utils.html.linebreaks handles both
    concerns using Django's own well-tested implementation.
    """
    from django.utils.html import linebreaks
    text = (text or '').strip()
    return linebreaks(text, autoescape=True) if text else ''


def html_paragraphs_to_text(html):
    """Reverse of text_to_html_paragraphs — pulls plain-text paragraphs back
    out of <p>/<br> markup (unescaping HTML entities) so it can be
    shown/edited in a plain <textarea>. Falls back to stripping all tags for
    content that wasn't produced by text_to_html_paragraphs (e.g.
    AI-generated markup)."""
    import html as html_stdlib
    html = (html or '').strip()
    if not html:
        return ''
    paragraphs = re.findall(r'<p>(.*?)</p>', html, re.DOTALL)
    if not paragraphs:
        return html_stdlib.unescape(re.sub(r'<[^>]+>', '', html)).strip()
    texts = [html_stdlib.unescape(re.sub(r'<br\s*/?>', '\n', p)).strip() for p in paragraphs]
    return '\n\n'.join(texts)


def parse_json_body(request, error_message="Noto'g'ri so'rov", ok_field=False):
    """Parse `request.body` as JSON.

    Returns (data, None) on success, or (None, response) with a ready-made
    400 JsonResponse the caller should return immediately on failure:

        data, err = parse_json_body(request)
        if err:
            return err
    """
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError, ValueError):
        payload = {'error': error_message}
        if ok_field:
            payload['ok'] = False
        return None, JsonResponse(payload, status=400)


def daily_series(queryset, date_field, days, agg):
    """Bucket `queryset` into daily values for the last `days` days (oldest
    first) in a single query, instead of one query per day.

    `agg` is a keyword aggregate expression, e.g. Count('id') or Sum('amount').
    """
    now = timezone.now()
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        queryset.filter(**{f'{date_field}__gte': start})
        # Clear any ordering the caller's queryset carries — left in place,
        # Django folds the order-by field into GROUP BY too, splitting each
        # row into its own bucket instead of grouping by day.
        .order_by()
        .annotate(bucket=TruncDate(date_field))
        .values('bucket')
        .annotate(value=agg)
    )
    by_bucket = {row['bucket']: row['value'] for row in rows}
    labels, values = [], []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        labels.append(day.strftime('%d %b'))
        values.append(by_bucket.get(day) or 0)
    return labels, values


def monthly_series(queryset, date_field, months, agg):
    """Bucket `queryset` into monthly values for the last `months` calendar
    months (oldest first) in a single query.

    Steps back by real calendar months (not `i * 30` days, which drifts
    across months of different lengths), so the returned month for i=5 is
    always exactly 5 calendar months before the current one.
    """
    now = timezone.now()
    rows = (
        queryset.order_by()
        .annotate(bucket=TruncMonth(date_field))
        .values('bucket')
        .annotate(value=agg)
    )
    by_bucket = {(row['bucket'].year, row['bucket'].month): row['value'] for row in rows if row['bucket']}

    labels, values = [], []
    for i in range(months - 1, -1, -1):
        total_months = now.year * 12 + (now.month - 1) - i
        y, m = divmod(total_months, 12)
        m += 1
        labels.append(date(y, m, 1).strftime('%b %Y'))
        values.append(by_bucket.get((y, m)) or 0)
    return labels, values


_TASK_HISTORY_MAX = 200


def record_task_run(name, success, duration, note=''):
    """Appends one JSON line to logs/task_history.jsonl for a scheduled/cron
    command (e.g. backup_data), then trims the file to the last N runs.
    Used by /system/ to show whether background tasks are actually
    succeeding without needing to grep raw cron output."""
    path = settings.LOGS_DIR / 'task_history.jsonl'
    entry = {
        'name': name, 'success': success, 'duration': round(duration, 2),
        'note': note[:500], 'at': timezone.now().isoformat(),
    }
    lines = []
    if path.exists():
        lines = path.read_text().splitlines()
    lines.append(json.dumps(entry))
    lines = lines[-_TASK_HISTORY_MAX:]
    path.write_text('\n'.join(lines) + '\n')


def read_task_history(limit=50):
    path = settings.LOGS_DIR / 'task_history.jsonl'
    if not path.exists():
        return []
    lines = path.read_text().splitlines()[-limit:]
    entries = []
    for line in reversed(lines):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


_AUDIT_LOG_MAX = 500


def record_audit(username, action, detail=''):
    """Appends one line to logs/audit.jsonl — who did what in /system/ and
    when. Append-only on purpose: an admin action log that could itself be
    edited from the same panel wouldn't be trustworthy."""
    path = settings.LOGS_DIR / 'audit.jsonl'
    entry = {
        'user': username, 'action': action, 'detail': detail[:300],
        'at': timezone.now().isoformat(),
    }
    lines = []
    if path.exists():
        lines = path.read_text().splitlines()
    lines.append(json.dumps(entry))
    lines = lines[-_AUDIT_LOG_MAX:]
    path.write_text('\n'.join(lines) + '\n')


def read_audit(limit=100):
    path = settings.LOGS_DIR / 'audit.jsonl'
    if not path.exists():
        return []
    lines = path.read_text().splitlines()[-limit:]
    entries = []
    for line in reversed(lines):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries
