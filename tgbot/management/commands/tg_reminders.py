"""
Ertangi imtihonga yozilganlarga Telegram'da eslatma yuboradi.

Kunlik cron orqali (masalan har kuni 18:00 da):
    python manage.py tg_reminders

Har bir navbatga eslatma bir marta boradi — qayta ishga tushirish xavfsiz.
"""
import time

from django.core.management.base import BaseCommand

from core.utils import record_task_run
from tgbot.services import send_reminders


class Command(BaseCommand):
    help = "Ertangi imtihon navbatidagilarga Telegram eslatma yuboradi."

    def handle(self, *args, **options):
        start = time.monotonic()
        try:
            sent = send_reminders()
        except Exception as e:
            record_task_run('tg_reminders', False, time.monotonic() - start, note=str(e))
            raise
        record_task_run('tg_reminders', True, time.monotonic() - start, note=f'{sent} ta eslatma')
        self.stdout.write(self.style.SUCCESS(f'{sent} ta eslatma yuborildi.'))
