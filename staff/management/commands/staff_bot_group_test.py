from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from staff import telegram_api


class Command(BaseCommand):
    help = "AB Staff botning AbChat guruhiga test xabari yuboradi."

    def handle(self, *args, **options):
        chat_id = str(settings.STAFF_GROUP_CHAT_ID).strip()
        if not chat_id:
            raise CommandError(".env faylida STAFF_GROUP_CHAT_ID yo'q.")
        if not telegram_api.enabled():
            raise CommandError(".env faylida STAFF_BOT_TOKEN yo'q.")
        result = telegram_api.send(chat_id, '<b>✅ AB Staff Bot ulandi</b>\n\nUmumiy jamoa xabarlari endi shu guruhga yuboriladi.')
        if not result:
            raise CommandError("Xabar yuborilmadi. Botni guruhga qo'shib, xabar yuborish huquqini bering.")
        self.stdout.write(self.style.SUCCESS('AbChat guruhiga test xabari yuborildi.'))
