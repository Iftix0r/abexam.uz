import json
import logging
import secrets
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import api, handlers
from .models import ExamDay
from .services import fmt_date

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook(request):
    """Telegram POSTs every update here (setWebhook: manage.py tg_webhook set).
    Always answers 200 once the secret matches — a non-2xx makes Telegram
    resend the same update over and over."""
    if not constant_time_compare(request.headers.get('X-Telegram-Bot-Api-Secret-Token', ''), api.webhook_secret()):
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
