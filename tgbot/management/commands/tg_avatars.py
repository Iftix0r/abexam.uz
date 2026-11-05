"""
Botga ulangan foydalanuvchilarning Telegram rasmini saytga oladi.

Yangi ulanganlar uchun bu avtomatik ishlaydi; buyruq oldindan ulanganlar uchun:
    python manage.py tg_avatars

Saytga o'zi rasm yuklaganlarga tegmaydi — qayta ishga tushirish xavfsiz.
"""
import time
from collections import Counter

from django.core.management.base import BaseCommand

from tgbot import api, avatars
from tgbot.models import TelegramAccount


class Command(BaseCommand):
    help = "Botga ulangan foydalanuvchilarning Telegram rasmini saytga oladi."

    def handle(self, *args, **options):
        if not api.enabled():
            self.stderr.write('TELEGRAM_BOT_TOKEN sozlanmagan')
            return
        counts = Counter()
        for acc in TelegramAccount.objects.filter(user__isnull=False).select_related('user'):
            counts[avatars.refresh(acc)] += 1
            time.sleep(0.1)  # Bot API rate limit
        self.stdout.write(
            f"Yangilandi: {counts[avatars.UPDATED]}, o'zgarmagan: {counts[avatars.UNCHANGED]}, "
            f"rasmi yo'q yoki yopiq: {counts[avatars.NO_PHOTO] + counts[avatars.REMOVED]}, "
            f"o'z rasmi bor: {counts[avatars.SKIPPED]}, xato: {counts[avatars.FAILED]}")
