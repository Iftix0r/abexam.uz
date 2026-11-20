import hashlib
import logging
import threading

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def enabled():
    return bool(settings.STAFF_BOT_TOKEN)


def webhook_secret():
    return settings.STAFF_BOT_WEBHOOK_SECRET or hashlib.sha256(
        (settings.SECRET_KEY + ':staff-bot-secret').encode()).hexdigest()[:48]


def webhook_path_token():
    return hashlib.sha256((settings.SECRET_KEY + ':staff-bot-path').encode()).hexdigest()[:32]


def call(method, **params):
    if not enabled():
        return None
    try:
        response = requests.post(f'https://api.telegram.org/bot{settings.STAFF_BOT_TOKEN}/{method}',
                                 json=params, timeout=12)
        data = response.json()
    except (requests.RequestException, ValueError):
        logger.warning('Staff Telegram %s failed', method, exc_info=True)
        return None
    if not data.get('ok'):
        logger.warning('Staff Telegram %s: %s', method, data.get('description'))
        return None
    return data.get('result')


def send(chat_id, text, reply_markup=None):
    return call('sendMessage', chat_id=chat_id, text=text, parse_mode='HTML',
                disable_web_page_preview=True, reply_markup=reply_markup)


def send_async(chat_id, text, reply_markup=None):
    if enabled():
        threading.Thread(target=send, args=(chat_id, text, reply_markup), daemon=True).start()


def keyboard(rows):
    return {'keyboard': rows, 'resize_keyboard': True}


def inline(rows):
    return {'inline_keyboard': [[{'text': text, 'url': url}] for text, url in rows]}
