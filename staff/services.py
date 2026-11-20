from html import escape

from django.conf import settings
from django.urls import reverse

from . import telegram_api


def notify_user(user, title, text, path='/staff/'):
    account = getattr(user, 'staff_telegram', None)
    if not account or account.is_blocked:
        return False
    url = reverse('staff:dashboard') if path == '/staff/' else path
    message = f"<b>{escape(title)}</b>\n\n{escape(text)}\n\n🌐 abexam.uz{url}"
    telegram_api.send_async(account.chat_id, message)
    return True


def notify_task(task):
    return notify_user(task.assignee.user, '📋 Yangi vazifa',
                       f"{task.title}\nMuddat: {task.due_at:%d.%m.%Y %H:%M}", f'/staff/tasks/{task.pk}/')


def notify_profiles(profiles, title, text, path='/staff/'):
    sent = 0
    for profile in profiles.select_related('user', 'user__staff_telegram'):
        if profile.notifications_enabled and notify_user(profile.user, title, text, path):
            sent += 1
    return sent


def notify_group(title, text, path='/staff/announcements/'):
    """Send non-confidential company-wide news to the shared AbChat group."""
    chat_id = str(settings.STAFF_GROUP_CHAT_ID).strip()
    if not chat_id:
        return False
    message = (f"<b>{escape(title)}</b>\n\n{escape(text)}\n\n"
               f"🌐 abexam.uz{path}\n\n<i>AB Education · Umumiy xabar</i>")
    telegram_api.send_async(chat_id, message)
    return True
