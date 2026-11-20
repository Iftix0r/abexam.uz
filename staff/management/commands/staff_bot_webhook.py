from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from staff import telegram_api as api


COMMANDS = [
    ('start', 'AB Staff bosh menyusi'),
    ('tasks', 'Mening vazifalarim'),
    ('report', 'Kunlik hisobot'),
    ('menu', 'Bosh menyu'),
]


class Command(BaseCommand):
    help = "Alohida AB Staff Telegram bot webhookini boshqaradi."

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['set', 'info', 'delete'])

    def handle(self, *args, **options):
        if not api.enabled():
            raise CommandError(".env faylida STAFF_BOT_TOKEN yo'q.")
        action = options['action']
        if action == 'set':
            url = settings.SITE_URL.rstrip('/') + f'/staff/bot/webhook/{api.webhook_path_token()}/'
            result = api.call('setWebhook', url=url, secret_token=api.webhook_secret(), max_connections=10,
                              allowed_updates=['message'], drop_pending_updates=True)
            if not result:
                raise CommandError('Webhook o‘rnatilmadi. SITE_URL HTTPS ekanini tekshiring.')
            api.call('setMyCommands', commands=[{'command': c, 'description': d} for c, d in COMMANDS])
            self.stdout.write(self.style.SUCCESS(f'AB Staff webhook o‘rnatildi: {url}'))
        elif action == 'delete':
            api.call('deleteWebhook')
            self.stdout.write(self.style.SUCCESS("AB Staff webhook o'chirildi."))
        info = api.call('getWebhookInfo') or {}
        self.stdout.write(f"URL: {info.get('url') or '—'}")
        self.stdout.write(f"Navbat: {info.get('pending_update_count', 0)}")
        if info.get('last_error_message'):
            self.stdout.write(self.style.WARNING(info['last_error_message']))
