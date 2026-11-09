import json
import logging
import secrets
import time
from collections import Counter
from itertools import groupby
from threading import Lock

from core.security import record_threat
from core.utils import get_client_ip
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import api, avatars, handlers
from .models import ExamDay, TelegramAccount
from .services import fmt_date, site_url

logger = logging.getLogger(__name__)

# Invalid webhook calls never reach the bot handler.  Keep this limiter in
# memory: writing one cache file for every hostile request would make a flood
# more expensive for us than simply rejecting it.
_bad_webhooks = {'minute': 0, 'hits': Counter()}
_bad_webhooks_lock = Lock()
BAD_WEBHOOKS_PER_MINUTE = 30


def _reject_fake_webhook(request):
    ip = get_client_ip(request)
    minute = int(time.time() // 60)
    with _bad_webhooks_lock:
        if _bad_webhooks['minute'] != minute:
            _bad_webhooks['minute'] = minute
            _bad_webhooks['hits'].clear()
        _bad_webhooks['hits'][ip] += 1
        limited = _bad_webhooks['hits'][ip] > BAD_WEBHOOKS_PER_MINUTE

    # record_threat batches these hits in memory and writes them periodically,
    # so the security panel remains useful without one database write per hit.
    record_threat('webhook', request)
    response = HttpResponse(status=429 if limited else 403)
    response['Cache-Control'] = 'no-store'
    if limited:
        response['Retry-After'] = '60'
    return response


@csrf_exempt
@require_POST
def webhook(request):
    """Telegram POSTs every update here (setWebhook: manage.py tg_webhook set).
    Always answers 200 once the secret matches — a non-2xx makes Telegram
    resend the same update over and over."""
    if not constant_time_compare(request.headers.get('X-Telegram-Bot-Api-Secret-Token', ''), api.webhook_secret()):
        return _reject_fake_webhook(request)
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


@csrf_exempt
@require_POST
def legacy_webhook(request):
    """Transition endpoint; disable after `tg_webhook set` switches Telegram."""
    from django.conf import settings
    if settings.TELEGRAM_HIDDEN_WEBHOOK_ONLY:
        return HttpResponse(status=404)
    return webhook(request)


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
