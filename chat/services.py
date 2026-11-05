"""Rules a message has to pass, and the actions shared by reports and moderators."""
import re
from datetime import timedelta
from html import escape

from django.core.cache import cache
from django.utils import timezone

from core.utils import notify_staff_work, site_link

from .models import ChatMessage, ChatMute, ChatReport

MAX_LENGTH = 1000
MIN_SECONDS_BETWEEN = 2
MAX_PER_MINUTE = 15
AUTO_HIDE_REPORTS = 3

# Contact details and links move a conversation out of sight of moderators,
# so students cannot post them. Staff can, for announcements.
_PHONE = re.compile(r'(?:\+?\d[\s\-().]*){9,}')
_LINK = re.compile(r'https?://|www\.|t\.me/|\b[\w-]+\.(?:com|uz|ru|org|net|me|io|app|info)\b', re.I)
_HANDLE = re.compile(r'(?<![\w@])@[A-Za-z]\w{3,}')


def clean_text(text):
    text = re.sub(r'\n{3,}', '\n\n', (text or '').replace('\r', '')).strip()
    return text


def rule_error(user, text):
    """Why `text` cannot be posted, or None."""
    if not text:
        return "Xabar bo'sh"
    if len(text) > MAX_LENGTH:
        return f"Xabar {MAX_LENGTH} belgidan oshmasin"
    if not user.is_staff and (_PHONE.search(text) or _LINK.search(text) or _HANDLE.search(text)):
        return "Xavfsizlik uchun telefon raqam, havola va @username yuborib bo'lmaydi"
    return None


def rate_error(user):
    if cache.add(f'chat_gap:{user.pk}', 1, MIN_SECONDS_BETWEEN) is False:
        return "Biroz sekinroq yozing"
    key = f'chat_minute:{user.pk}'
    cache.add(key, 0, 60)
    try:
        if cache.incr(key) > MAX_PER_MINUTE:
            return "Juda ko'p xabar yubordingiz, bir daqiqa kuting"
    except ValueError:
        pass
    return None


def active_mute(user):
    mute = ChatMute.objects.filter(user=user).first()
    return mute if mute and mute.active else None


def hide(message, by=None):
    message.deleted_at = timezone.now()
    message.deleted_by = by
    message.save(update_fields=['deleted_at', 'deleted_by'])


def resolve_reports(message):
    message.reports.filter(resolved_at__isnull=True).update(resolved_at=timezone.now())


def report(message, reporter):
    """Files a report once per student; returns False for a repeat."""
    _, created = ChatReport.objects.get_or_create(message=message, reporter=reporter)
    if not created:
        return False
    open_reports = message.reports.filter(resolved_at__isnull=True).count()
    if open_reports == 1:
        notify_staff_work(
            f"🚩 <b>AbChat shikoyati</b> — {escape(message.room.title)}\n"
            f"{escape(message.user.display_name)}: {escape(message.text[:200])}",
            [[("Ko'rib chiqish", site_link('/panel/chat/'))]])
    if open_reports >= AUTO_HIDE_REPORTS and message.deleted_at is None:
        hide(message)  # stays hidden until a moderator looks at it
    return True


def mute(user, days, by):
    ChatMute.objects.update_or_create(user=user, defaults={
        'until': timezone.now() + timedelta(days=days), 'created_by': by})


def open_report_messages():
    # Through ChatReport: filtering on reports__resolved_at__isnull directly
    # would also match every message that has no report at all.
    reported = ChatReport.objects.filter(resolved_at__isnull=True).values('message')
    return ChatMessage.objects.filter(pk__in=reported).select_related('user', 'room').order_by('-pk')
