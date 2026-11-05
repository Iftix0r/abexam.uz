"""Rules a message has to pass, and the actions shared by reports and moderators."""
import re
from datetime import timedelta
from html import escape

from django.core.cache import cache
from django.db import DatabaseError
from django.db.models import F, Max, Q
from django.utils import timezone

from core.alerts import record_alert
from core.utils import notify_staff_work, site_link
from users.models import User

from .models import (ChatBlock, ChatMessage, ChatMute, ChatPresence, ChatReaction, ChatReport, ChatThread,
                     StaffMessage, StaffRead, SupportThread)

MAX_LENGTH = 1000
MIN_SECONDS_BETWEEN = 2
MAX_PER_MINUTE = 15
AUTO_HIDE_REPORTS = 3
MAX_REQUESTS_PER_DAY = 10
MAX_REQUESTS_PER_DAY_PREMIUM = 30
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


def rule_error(user, text, contacts_ok=False):
    """Why `text` cannot be posted, or None. Talking to AB Admin, a student may
    give a phone number or a payment detail: `contacts_ok`."""
    if not text:
        return "Xabar bo'sh"
    if len(text) > MAX_LENGTH:
        return f"Xabar {MAX_LENGTH} belgidan oshmasin"
    if not contacts_ok and not user.is_staff and (_PHONE.search(text) or _LINK.search(text) or _HANDLE.search(text)):
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
        record_alert('report', f'AbChat shikoyati: {message.user.display_name}', message.text[:200],
                     '/panel/chat/reports/', message.user)
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
    if message.room_id is not None:
        return True
    if message.support_id is not None:
        return message.support.user_id == user.pk or user.is_staff
    return message.thread.has(user)


# ── Presence ───────────────────────────────────────────────────────────────────
def touch_presence(room, user):
    if not cache.add(f'chat_seen:{room.pk}:{user.pk}', 1, PRESENCE_WRITE_EVERY):
        return
    try:
        ChatPresence.objects.update_or_create(room=room, user=user, defaults={'last_seen': timezone.now()})
    except DatabaseError:
        # Opening a room sends two requests at once, and both can try to create
        # this row. Presence is a nicety: it must never fail the chat itself.
        pass


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
        limit = MAX_REQUESTS_PER_DAY_PREMIUM if user.is_premium else MAX_REQUESTS_PER_DAY
        if cache.incr(key) > limit and not user.is_staff:
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
    private = live.filter(Q(user_a=user, last_message_id__gt=F('a_read'))
                          | Q(user_b=user, last_message_id__gt=F('b_read'))).count()
    support = (SupportThread.objects.filter(user=user, last_message_id__gt=F('user_read'))
               .exclude(last_message__user=user).count())
    return private + support


# ── AB Admin ───────────────────────────────────────────────────────────────────
def support_of(user):
    return SupportThread.objects.get_or_create(user=user)[0]


def message_from_admin(student, by, text, auto=False):
    """Puts a message from AB Admin into a student's chat, and into Telegram
    when their bot is linked."""
    from tgbot import api as tg_api
    from tgbot.models import TelegramAccount
    thread = support_of(student)
    message = ChatMessage.objects.create(support=thread, user=by, text=text, is_auto=auto)
    after_support_message(thread, message)
    account = TelegramAccount.objects.filter(user=student, is_blocked=False).first()
    if account:
        tg_api.send_async(account.chat_id, escape(text))


def welcome_text(user):
    name = user.first_name.strip()
    greeting = f'Salom, {name}!' if name else 'Salom!'
    return f"{greeting} AbExam'ga xush kelibsiz. Men AB Admin. Qanday yordam bera olaman?"


def send_welcome(user):
    """Opens the student's AB Admin chat with a greeting. It needs an author,
    so it waits until the site has a superuser; the student sees "AB Admin"."""
    sender = User.objects.filter(is_superuser=True).order_by('pk').first()
    if sender is None or user.is_staff:
        return
    thread = support_of(user)
    if thread.messages.exists():
        return
    message = ChatMessage.objects.create(support=thread, user=sender, text=welcome_text(user), is_auto=True)
    # staff_read too: nobody has to answer a greeting.
    SupportThread.objects.filter(pk=thread.pk).update(last_message=message, staff_read=message.pk)


def _waiting_for_staff():
    return SupportThread.objects.filter(last_message__user=F('user'), last_message_id__gt=F('staff_read'))


def support_unread_total():
    return _waiting_for_staff().count()


def after_support_message(thread, message):
    from_student = message.user_id == thread.user_id
    already_waiting = from_student and _waiting_for_staff().filter(pk=thread.pk).exists()
    thread.last_message = message
    field = 'user_read' if from_student else 'staff_read'
    setattr(thread, field, message.pk)
    thread.save(update_fields=['last_message', field, 'updated_at'])
    if from_student and not already_waiting:  # one alert per waiting chat, not per message
        tag = ' ⭐ Premium' if thread.user.is_premium else ''
        record_alert('support', f'AB Admin chatiga xabar: {thread.user.display_name}', message.text[:200],
                     f'/panel/chat/?t={thread.pk}', thread.user)
        notify_staff_work(f"💬 <b>AB Admin</b>{tag}\n{escape(thread.user.display_name)}: {escape(message.text[:200])}",
                          [[("Javob berish", site_link(f'/panel/chat/?t={thread.pk}'))]])


def mark_support_read(thread, message_id, staff):
    field = 'staff_read' if staff else 'user_read'
    if message_id > getattr(thread, field):
        setattr(thread, field, message_id)
        SupportThread.objects.filter(pk=thread.pk).update(**{field: message_id})


# ── Admins among themselves ────────────────────────────────────────────────────
GROUP = 'group'
STAFF_ONLINE_SECONDS = 40
STAFF_MAX_LENGTH = 2000


def touch_staff(user):
    cache.set(f'staff_seen:{user.pk}', 1, STAFF_ONLINE_SECONDS)


def staff_online(user_ids):
    found = cache.get_many([f'staff_seen:{pk}' for pk in user_ids])
    return {pk for pk in user_ids if f'staff_seen:{pk}' in found}


def staff_conversation(user, other):
    """Messages of the group (other is None) or of a private chat."""
    if other is None:
        return StaffMessage.objects.filter(recipient__isnull=True)
    return StaffMessage.objects.filter(Q(sender=user, recipient=other) | Q(sender=other, recipient=user))


def _read_map(user):
    return dict(StaffRead.objects.filter(user=user).values_list('conversation', 'last_id'))


def mark_staff_read(user, conversation, message_id):
    StaffRead.objects.update_or_create(user=user, conversation=str(conversation), defaults={'last_id': message_id})


def staff_rows(user):
    """The group, then every other admin; conversations waiting to be read first."""
    reads = _read_map(user)
    others = list(User.objects.filter(is_staff=True, is_active=True).exclude(pk=user.pk))
    online = staff_online([u.pk for u in others])

    def row(key, other, name, initials, color):
        messages = staff_conversation(user, other)
        last = messages.select_related('sender').order_by('-pk').first()
        unread = messages.filter(pk__gt=reads.get(str(key), 0)).exclude(sender=user).count()
        return {
            'key': str(key), 'name': name, 'initials': initials, 'color': color, 'unread': unread,
            'online': other is not None and other.pk in online, 'last_id': last.pk if last else 0,
            'preview': (('Siz: ' if last.sender_id == user.pk else '') + last.text[:60]) if last else '',
        }

    people = [row(u.pk, u, u.display_name, u.initials, u.avatar_color) for u in others]
    people.sort(key=lambda r: (-bool(r['unread']), -r['last_id'], not r['online'], r['name']))
    return [row(GROUP, None, 'Adminlar guruhi', 'AD', '#d32f2f')] + people


def team_unread(user):
    """Conversations with something new, for the panel badge."""
    reads = _read_map(user)
    latest = (StaffMessage.objects.filter(recipient=user).values('sender').annotate(last=Max('id')))
    private = sum(1 for r in latest if r['last'] > reads.get(str(r['sender']), 0))
    group = StaffMessage.objects.filter(recipient__isnull=True, pk__gt=reads.get(GROUP, 0)).exclude(sender=user).exists()
    return private + int(group)
