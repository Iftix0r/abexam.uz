"""Rules a message has to pass, and the actions shared by reports and moderators."""
import re
from datetime import timedelta
from html import escape

from django.core.cache import cache
from django.db.models import F, Q
from django.utils import timezone

from core.utils import notify_staff_work, site_link
from users.models import User

from .models import ChatBlock, ChatMessage, ChatMute, ChatPresence, ChatReaction, ChatReport, ChatThread

MAX_LENGTH = 1000
MIN_SECONDS_BETWEEN = 2
MAX_PER_MINUTE = 15
AUTO_HIDE_REPORTS = 3
MAX_REQUESTS_PER_DAY = 10
ONLINE_WINDOW = timedelta(seconds=75)
PRESENCE_WRITE_EVERY = 30  # seconds; polling must not turn into a write per request

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
            f"🚩 <b>AbChat shikoyati</b> — {escape(message.room.title if message.room else 'Lichka')}\n"
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


def can_access(message, user):
    return message.room_id is not None or message.thread.has(user)


# ── Presence ───────────────────────────────────────────────────────────────────
def touch_presence(room, user):
    if cache.add(f'chat_seen:{room.pk}:{user.pk}', 1, PRESENCE_WRITE_EVERY):
        ChatPresence.objects.update_or_create(room=room, user=user, defaults={'last_seen': timezone.now()})


def online_since():
    return timezone.now() - ONLINE_WINDOW


def compact_number(number):
    """999, 1k, 2,5k, 100k, 1 mln. Rounded down, so 999 999 never reads as 1000k."""
    if number < 1000:
        return str(number)
    divisor, unit = (1000, 'k') if number < 1_000_000 else (1_000_000, ' mln')
    tenths = number * 10 // divisor
    whole, part = divmod(tenths, 10)
    return f'{whole},{part}{unit}' if part else f'{whole}{unit}'


def member_total():
    """Every room is open to all, so its members are all active accounts.
    Cached: this is read on each poll."""
    return cache.get_or_set('chat_member_total', lambda: User.objects.filter(is_active=True).count(), 300)


def room_counts(room):
    online = room.presence.filter(last_seen__gte=online_since()).count()
    return {'members': compact_number(member_total()), 'online': compact_number(online)}


def is_online(user):
    return ChatPresence.objects.filter(user=user, last_seen__gte=online_since()).exists()


# ── Reactions ──────────────────────────────────────────────────────────────────
def toggle_reaction(message, user, kind):
    current = ChatReaction.objects.filter(message=message, user=user).first()
    if current and current.kind == kind:
        current.delete()
    elif current:
        current.kind = kind
        current.save(update_fields=['kind'])
    else:
        ChatReaction.objects.create(message=message, user=user, kind=kind)


def reaction_map(message_ids, viewer):
    """{message id: {'counts': {kind: n}, 'mine': kind or None}}"""
    result = {}
    rows = ChatReaction.objects.filter(message_id__in=message_ids).values_list('message_id', 'kind', 'user_id')
    for message_id, kind, user_id in rows:
        entry = result.setdefault(message_id, {'counts': {}, 'mine': None})
        entry['counts'][kind] = entry['counts'].get(kind, 0) + 1
        if user_id == viewer.pk:
            entry['mine'] = kind
    return result


# ── Private chats ──────────────────────────────────────────────────────────────
def is_blocked(user, other):
    return ChatBlock.objects.filter(Q(blocker=user, blocked=other) | Q(blocker=other, blocked=user)).exists()


def thread_between(user, other):
    a, b = sorted((user, other), key=lambda u: u.pk)
    return ChatThread.objects.filter(user_a=a, user_b=b).first()


def start_thread(user, other):
    """Returns (thread, error)."""
    if user.pk == other.pk:
        return None, "O'zingizga yozib bo'lmaydi"
    if active_mute(user):
        return None, "Siz hozir yoza olmaysiz"
    if is_blocked(user, other):
        return None, "Bu foydalanuvchiga yozib bo'lmaydi"
    thread = thread_between(user, other)
    if thread:
        return thread, None
    key = f'chat_requests:{user.pk}'
    cache.add(key, 0, 86400)
    try:
        if cache.incr(key) > MAX_REQUESTS_PER_DAY and not user.is_staff:
            return None, "Bugun juda ko'p so'rov yubordingiz, ertaga urinib ko'ring"
    except ValueError:
        pass
    a, b = sorted((user, other), key=lambda u: u.pk)
    # Staff write to students directly; students go through a request.
    status = ChatThread.ACCEPTED if user.is_staff else ChatThread.REQUEST
    return ChatThread.objects.create(user_a=a, user_b=b, requested_by=user, status=status), None


def thread_send_error(thread, user):
    if is_blocked(user, thread.other(user)):
        return "Bu foydalanuvchiga yozib bo'lmaydi"
    if thread.status == ChatThread.ACCEPTED:
        return None
    if user.pk != thread.requested_by_id:
        return "Avval so'rovni qabul qiling"
    if thread.messages.exists():
        return "So'rovingiz qabul qilinishi kutilmoqda"
    return None


def after_thread_message(thread, message):
    thread.last_message = message
    thread.save(update_fields=['last_message', 'updated_at'])
    mark_read(thread, message.user, message.pk)


def mark_read(thread, user, message_id):
    field = 'a_read' if user.pk == thread.user_a_id else 'b_read'
    if message_id > getattr(thread, field):
        setattr(thread, field, message_id)
        ChatThread.objects.filter(pk=thread.pk).update(**{field: message_id})


def threads_of(user):
    return (ChatThread.objects.filter(Q(user_a=user) | Q(user_b=user), last_message__isnull=False)
            .exclude(Q(status=ChatThread.DECLINED) & ~Q(requested_by=user))
            .select_related('user_a', 'user_b', 'last_message'))


def unread_count(user):
    live = ChatThread.objects.exclude(status=ChatThread.DECLINED).exclude(last_message__user=user)
    return live.filter(Q(user_a=user, last_message_id__gt=F('a_read'))
                       | Q(user_b=user, last_message_id__gt=F('b_read'))).count()
