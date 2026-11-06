"""Uses a linked student's Telegram profile photo as their site avatar.

A photo the student uploaded on the site always wins. Files taken from
Telegram are told apart by their name (avatars/tg_<user pk>_<photo id>.jpg),
which also says whether the current Telegram photo is already stored.
"""
import logging
import threading

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import connection
from django.db.models import Q

from users.models import User

from . import api
from .models import TelegramAccount

logger = logging.getLogger(__name__)

PREFIX = 'tg_'
TARGET_WIDTH = 320  # Telegram offers 160/320/640; the largest avatar on the site is 80px
MAX_BYTES = 2 * 1024 * 1024
RECHECK_SECONDS = 86400

UPDATED, UNCHANGED, REMOVED, NO_PHOTO, SKIPPED, FAILED = (
    'updated', 'unchanged', 'removed', 'no_photo', 'skipped', 'failed')


def _basename(user):
    return user.avatar.name.rsplit('/', 1)[-1] if user.avatar else ''


def from_telegram(user):
    return _basename(user).startswith(PREFIX)


def _download(file_id):
    info = api.call('getFile', file_id=file_id)
    if not info or not info.get('file_path'):
        return None
    url = f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{info['file_path']}"
    try:
        resp = requests.get(url, timeout=15)
    except requests.RequestException:
        # No exc_info: the exception text carries the URL, and with it the bot token.
        logger.warning('Telegram photo download failed')
        return None
    if resp.status_code != 200 or not resp.content or len(resp.content) > MAX_BYTES:
        return None
    return resp.content


def clear(user):
    """Drops a Telegram photo (unlinked, or removed in Telegram). Own uploads stay."""
    if user is None or not from_telegram(user):
        return False
    name = user.avatar.name
    User.objects.filter(pk=user.pk, avatar=name).update(avatar=None)
    user.avatar.storage.delete(name)
    user.avatar = None
    return True


def refresh(acc):
    """Brings the linked user's avatar in line with Telegram; returns what happened."""
    user = acc.user
    if user is None or (user.avatar and not from_telegram(user)):
        return SKIPPED
    result = api.call('getUserProfilePhotos', user_id=acc.chat_id, limit=1)
    if result is None:
        return FAILED  # says nothing about the photo, so the current one stays
    photos = result.get('photos') or []
    if not photos or not photos[0]:
        return REMOVED if clear(user) else NO_PHOTO

    sizes = photos[0]
    photo = next((s for s in sizes if s.get('width', 0) >= TARGET_WIDTH), sizes[-1])
    filename = f"{PREFIX}{user.pk}_{photo['file_unique_id']}.jpg"
    if _basename(user) == filename:
        return UNCHANGED
    content = _download(photo['file_id'])
    if content is None:
        return FAILED

    old = user.avatar.name if user.avatar else ''
    storage = user.avatar.storage
    # Saved directly: the field's upload_to would rename it to a random uuid and
    # lose the PREFIX that from_telegram() relies on.
    stored = storage.save(f'avatars/{filename}', ContentFile(content))
    # Only if the avatar is still what was read above: the student may have
    # uploaded their own photo while this one was downloading.
    unchanged = Q(avatar=old) if old else Q(avatar='') | Q(avatar__isnull=True)
    if not User.objects.filter(unchanged, pk=user.pk).update(avatar=stored):
        storage.delete(stored)
        return SKIPPED
    if old:
        storage.delete(old)
    user.avatar = stored
    return UPDATED


def _refresh_in_thread(account_id):
    try:
        acc = TelegramAccount.objects.select_related('user').filter(pk=account_id).first()
        if acc:
            refresh(acc)
    except Exception:
        logger.exception('Telegram avatar refresh failed')
    finally:
        connection.close()


def refresh_async(acc, force=False):
    """Refreshes in the background so the webhook answers at once. Without
    `force`, at most once a day per chat: this runs on every bot update."""
    if not api.enabled() or not acc.user_id:
        return
    key = f'tg_avatar_checked:{acc.chat_id}'
    if force:
        cache.set(key, 1, RECHECK_SECONDS)
    elif not cache.add(key, 1, RECHECK_SECONDS):
        return
    threading.Thread(target=_refresh_in_thread, args=(acc.pk,), daemon=True).start()
