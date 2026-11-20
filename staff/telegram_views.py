import json
import logging

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from users.backends import normalize_phone, phone_variants
from . import telegram_api as api
from .models import StaffProfile, StaffTelegramAccount, Task

logger = logging.getLogger(__name__)


def _menu(account, prefix=''):
    if not account.user_id:
        text = (prefix + '\n\n' if prefix else '') + 'AB Staff botiga ulanish uchun telefon raqamingizni yuboring.'
        return api.send(account.chat_id, text, api.keyboard([[{'text': '📱 Raqamni yuborish', 'request_contact': True}]]))
    profile = StaffProfile.objects.filter(user=account.user, is_approved=True).first()
    if not profile:
        return api.send(account.chat_id, 'Profilingiz rahbariyat tomonidan hali tasdiqlanmagan.')
    active = Task.objects.filter(assignee=profile).exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED])
    late = active.filter(due_at__lt=timezone.now()).count()
    text = (f'<b>AB Staff</b>\n\n👤 {account.user.display_name}\n💼 {profile.get_role_display()}\n'
            f'📋 Faol vazifalar: <b>{active.count()}</b>\n🔴 Kechikkan: <b>{late}</b>')
    site = settings.SITE_URL.rstrip('/')
    return api.send(account.chat_id, text, api.inline([
        ('📋 Vazifalarim', site + '/staff/tasks/'),
        ('✅ Kunlik hisobot', site + '/staff/report/'),
        ('🏠 Staff kabineti', site + '/staff/'),
    ]))


def handle(update):
    message = update.get('message') or {}
    chat = message.get('chat') or {}
    if chat.get('type') != 'private':
        return
    account, _ = StaffTelegramAccount.objects.get_or_create(chat_id=chat['id'])
    account.username = chat.get('username', '')[:64]
    account.first_name = chat.get('first_name', '')[:128]
    account.last_seen_at = timezone.now()
    account.is_blocked = False
    account.save(update_fields=['username', 'first_name', 'last_seen_at', 'is_blocked'])
    if message.get('contact'):
        contact = message['contact']
        # Telegram may omit user_id on older clients.  A present, different
        # value means a forwarded contact and must not be used for login.
        if contact.get('user_id') is not None and contact.get('user_id') != chat['id']:
            return api.send(account.chat_id, 'Faqat o‘zingizning telefon raqamingizni yuboring.')
        phone = normalize_phone(contact.get('phone_number', ''))
        return _link_phone(account, phone)
    text = (message.get('text') or '').strip()
    # Desktop clients sometimes paste the number instead of sending a contact.
    phone = normalize_phone(text)
    if phone:
        return _link_phone(account, phone)
    command = text.split('@')[0]
    if command in {'/start', '/menu', '/tasks', '/report'}:
        return _menu(account)
    return _menu(account)


def _link_phone(account, phone):
    if not phone:
        return api.send(account.chat_id, 'Telefon raqami noto‘g‘ri. Masalan: +998901234567')
    User = get_user_model()
    user = User.objects.filter(phone_number__in=phone_variants(phone)).order_by('pk').first()
    if not user:
        return api.send(account.chat_id,
                        'Bu telefon raqami AbExam hisobida topilmadi. Saytdagi profilingizga shu raqamni kiriting.')
    profile = StaffProfile.objects.filter(user=user, is_approved=True).first()
    if not profile and user.is_superuser:
        profile, _ = StaffProfile.objects.update_or_create(
            user=user,
            defaults={'role': StaffProfile.Role.SUPER_ADMIN, 'job_title': 'Direktor', 'is_approved': True},
        )
    if not profile:
        return api.send(account.chat_id,
                        'AbExam hisobingiz topildi, lekin Staff profilingiz tasdiqlanmagan. Super admin tasdiqlashi kerak.')
    StaffTelegramAccount.objects.filter(user=user).exclude(pk=account.pk).update(user=None)
    account.user = user
    account.save(update_fields=['user'])
    return _menu(account, '✅ Hisobingiz muvaffaqiyatli ulandi.')


@csrf_exempt
@require_POST
def webhook(request, path_token):
    if not constant_time_compare(path_token, api.webhook_path_token()):
        return HttpResponse(status=404)
    if not constant_time_compare(request.headers.get('X-Telegram-Bot-Api-Secret-Token', ''), api.webhook_secret()):
        return HttpResponse(status=403)
    try:
        update = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=200)
    if cache.add(f"staff_tg_update:{update.get('update_id')}", 1, 86400):
        try:
            handle(update)
        except Exception:
            logger.exception('AB Staff Telegram update %s failed', update.get('update_id'))
    return JsonResponse({'ok': True})
