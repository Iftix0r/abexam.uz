"""
Telegram bot webhook'ini boshqaradi.

    python manage.py tg_webhook set     # maxfiy URL ga ulaydi
    python manage.py tg_webhook info    # Telegram tomonidagi holat, oxirgi xato
    python manage.py tg_webhook delete

Bot doimiy ishlab turadigan jarayon emas: Telegram har bir xabarni saytga
POST qiladi, shuning uchun cPanel/Passenger'da "o'chib qolmaydi".
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tgbot import api

COMMANDS = [
    ('start', 'Bosh menyu'),
    ('yozilish', 'Imtihonga yozilish'),
    ('navbat', 'Navbatlarim'),
    ('natijalar', 'Natijalarim'),
    ('hisob', 'Hisobim'),
    ('savol', 'Adminga yozish'),
    ('ball', 'Ball kalkulyatori: /ball 32'),
    ('help', 'Yordam'),
]


class Command(BaseCommand):
    help = "Telegram bot webhook'ini o'rnatadi / ko'rsatadi / o'chiradi."

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['set', 'info', 'delete'])

    def handle(self, *args, **options):
        if not api.enabled():
            raise CommandError(".env faylida TELEGRAM_BOT_TOKEN yo'q.")
        action = options['action']
        if action == 'set':
            url = settings.SITE_URL.rstrip('/') + f'/tg/webhook/{api.webhook_path_token()}/'
            ok = api.call('setWebhook', url=url, secret_token=api.webhook_secret(),
                          max_connections=10, allowed_updates=['message', 'callback_query'],
                          drop_pending_updates=True)
            if not ok:
                raise CommandError("setWebhook muvaffaqiyatsiz (logs'ga qarang). SITE_URL https bo'lishi kerak.")
            api.call('setMyCommands', commands=[{'command': c, 'description': d} for c, d in COMMANDS])
            self.stdout.write(self.style.SUCCESS(f'Webhook o\'rnatildi: {url}'))
            self.stdout.write(self.style.WARNING(
                "Tekshirgach .env ga TELEGRAM_HIDDEN_WEBHOOK_ONLY=True qo'shing va ilovani qayta yuklang."))
        elif action == 'delete':
            api.call('deleteWebhook')
            self.stdout.write(self.style.SUCCESS("Webhook o'chirildi."))
        info = api.call('getWebhookInfo') or {}
        self.stdout.write(f"URL: {info.get('url') or '—'}")
        self.stdout.write(f"Navbatda turgan xabarlar: {info.get('pending_update_count', 0)}")
        if info.get('last_error_message'):
            self.stdout.write(self.style.WARNING(f"Oxirgi xato: {info['last_error_message']}"))
