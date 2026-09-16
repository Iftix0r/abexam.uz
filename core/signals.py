"""Site-wide crash alerting: any unhandled exception (a real bug, not a
404/permission-denied) pings the admin Telegram chat immediately, so a
crash surfaces without anyone needing to check Sentry or the server logs
first. Sentry (if configured) still gets the full trace — this is just the
"something broke, go look" push notification."""
import sys

from django.core.signals import got_request_exception
from django.dispatch import receiver

from .utils import notify_admin_telegram


@receiver(got_request_exception)
def alert_on_server_error(sender, request=None, **kwargs):
    exc_type, exc_value, _ = sys.exc_info()
    if exc_type is None:
        return
    path = request.path if request is not None else '?'
    notify_admin_telegram(
        f"🔥 <b>Server xatosi</b>\n"
        f"📍 {path}\n"
        f"⚠️ {exc_type.__name__}: {str(exc_value)[:200]}"
    )
