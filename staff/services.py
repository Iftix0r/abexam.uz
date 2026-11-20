from html import escape

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
