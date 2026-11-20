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
