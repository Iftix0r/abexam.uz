"""Thin Telegram Bot API client (plain `requests`, no bot framework).

The bot runs as a webhook inside the Django site: Telegram POSTs each
update to /tg/webhook/ and nothing has to stay running in the background,
which a cPanel/Passenger host would kill anyway.
"""
import hashlib
import logging
import threading

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def enabled():
    return bool(settings.TELEGRAM_BOT_TOKEN)


def call(method, **params):
    """Calls a Bot API method; returns its `result`, or None on any error so
    a Telegram hiccup never turns into a 500 for the caller."""
    if not enabled():
        return None
    params = {k: v for k, v in params.items() if v is not None}
    try:
        resp = requests.post(f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}',
                             json=params, timeout=10)
        data = resp.json()
    except (requests.RequestException, ValueError):
        logger.warning('Telegram %s failed', method, exc_info=True)
        return None
    if not data.get('ok'):
        logger.warning('Telegram %s: %s', method, data.get('description'))
        return None
    return data['result']


def send(chat_id, text, reply_markup=None):
    """Sends an HTML message. Returns False when the user has blocked the bot
    (or the chat is gone), so the caller can stop messaging them."""
    if not enabled():
        return True
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
                  'disable_web_page_preview': True, **({'reply_markup': reply_markup} if reply_markup else {})},
            timeout=10,
        )
    except requests.RequestException:
        logger.warning('Telegram sendMessage failed', exc_info=True)
        return True
    return resp.status_code != 403


def send_async(chat_id, text, reply_markup=None):
    """Fire-and-forget send for site code paths (submitting an exam, grading)
    that must not wait on Telegram."""
    if enabled():
        threading.Thread(target=send, args=(chat_id, text, reply_markup), daemon=True).start()


def edit(chat_id, message_id, text, reply_markup=None):
    return call('editMessageText', chat_id=chat_id, message_id=message_id, text=text,
                parse_mode='HTML', disable_web_page_preview=True, reply_markup=reply_markup)


def answer_callback(callback_id, text=None, alert=False):
    return call('answerCallbackQuery', callback_query_id=callback_id, text=text, show_alert=alert or None)


def webhook_secret():
    """Secret Telegram echoes back in X-Telegram-Bot-Api-Secret-Token, so
    nobody else can post fake updates to the webhook URL."""
    if settings.TELEGRAM_WEBHOOK_SECRET:
        return settings.TELEGRAM_WEBHOOK_SECRET
    return hashlib.sha256(f'{settings.SECRET_KEY}:tg-webhook'.encode()).hexdigest()[:40]


def bot_username():
    if settings.TELEGRAM_BOT_USERNAME:
        return settings.TELEGRAM_BOT_USERNAME.lstrip('@')
    name = cache.get('tg_bot_username')
    if name is None:
        me = call('getMe')
        name = (me or {}).get('username', '')
        cache.set('tg_bot_username', name, 86400 if name else 300)
    return name


def deep_link(payload=''):
    """t.me link that opens the bot and sends /start <payload>."""
    name = bot_username()
    if not name:
        return ''
    return f'https://t.me/{name}' + (f'?start={payload}' if payload else '')


def inline_keyboard(rows):
    """[[(text, callback_data_or_url), ...], ...] → InlineKeyboardMarkup."""
    return {'inline_keyboard': [
        [{'text': text, ('url' if data.startswith('http') else 'callback_data'): data} for text, data in row]
        for row in rows
    ]}
