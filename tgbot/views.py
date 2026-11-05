import json
import logging
import secrets
from itertools import groupby

from core.security import record_threat
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import api, avatars, handlers
from .models import ExamDay, TelegramAccount
from .services import fmt_date, site_url

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook(request):
    """Telegram POSTs every update here (setWebhook: manage.py tg_webhook set).
    Always answers 200 once the secret matches — a non-2xx makes Telegram
    resend the same update over and over."""
    if not constant_time_compare(request.headers.get('X-Telegram-Bot-Api-Secret-Token', ''), api.webhook_secret()):
        record_threat('webhook', request)
        return HttpResponseForbidden()
    try:
        update = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=200)
    # Telegram redelivers an update if we were slow to answer; handle it once.
    if cache.add(f"tg_update:{update.get('update_id')}", 1, 86400):
        try:
            handlers.handle_update(update)
        except Exception:
            logger.exception('Telegram update %s failed', update.get('update_id'))
    return JsonResponse({'ok': True})


def bot_page(request):
    """/telegram/ — what the bot does and how to connect it; signed-in users
    see their own link status here and can connect or disconnect."""
    return render(request, 'tgbot/bot_page.html', {
        'base_template': 'base.html' if request.user.is_authenticated else 'public_base.html',
    })


@login_required
@require_POST
def unlink(request):
    acc = TelegramAccount.objects.filter(user=request.user).first()
    if acc:
        avatars.clear(request.user)
        acc.user = None
        acc.save(update_fields=['user'])
        api.send_async(acc.chat_id, f"🔌 Sayt hisobingiz botdan uzildi. Qayta ulash: {site_url('/telegram/')}")
        messages.success(request, "Telegram bot hisobingizdan uzildi.")
    return redirect('telegram')


@login_required
def link(request):
    """Profile → «Telegramni ulash»: opens the bot with a one-time token
    that ties the chat to this site account."""
    token = secrets.token_urlsafe(16)
    url = api.deep_link(f'link_{token}')
    if not url:
        messages.error(request, "Telegram bot hozircha sozlanmagan.")
        return redirect('profile')
    cache.set(handlers.link_token_key(token), request.user.pk, 600)
    return redirect(url)


def schedule(request):
    """Public exam calendar: which days are planned and how full they are."""
    today = timezone.localdate()
    days = list(ExamDay.objects.filter(date__gte=today).with_booked())
    for d in days:
        d.book_url = api.deep_link(f'day_{d.pk}') if d.accepts_bookings() else ''
    return render(request, 'tgbot/schedule.html', {
        'by_date': [(fmt_date(date), list(items)) for date, items in groupby(days, key=lambda d: d.date)],
        'bot_url': api.deep_link(),
    })
