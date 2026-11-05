"""Records what happens on the site for the panel's notifications page."""
import logging
import re
from datetime import timedelta

from django.db import DatabaseError, transaction
from django.utils import timezone

from .models import StaffAlert

logger = logging.getLogger(__name__)

KEEP_DAYS = 90
PRUNE_EVERY = 200

_SYSTEMS = (('Android', 'Android'), ('iPhone', 'iPhone'), ('iPad', 'iPad'), ('Windows', 'Windows'),
            ('Mac OS', 'macOS'), ('Linux', 'Linux'))
_BROWSERS = (('Edge', r'Edg/(\d+)'), ('Opera', r'OPR/(\d+)'), ('Yandex', r'YaBrowser/(\d+)'),
             ('Firefox', r'Firefox/(\d+)'), ('Chrome', r'Chrome/(\d+)'), ('Safari', r'Version/(\d+).*Safari'))


def record_alert(kind, title, body='', url='', user=None):
    """Never raises: a notification must not fail the signup or payment behind it."""
    try:
        with transaction.atomic():
            alert = StaffAlert.objects.create(kind=kind, title=title[:200], body=body[:300], url=url[:255], user=user)
            if alert.pk % PRUNE_EVERY == 0:
                StaffAlert.objects.filter(created_at__lt=timezone.now() - timedelta(days=KEEP_DAYS)).delete()
    except DatabaseError:
        logger.exception('Staff alert not saved')


def _device(user_agent):
    """(browser, system, version) read from a User-Agent, blank when unknown."""
    system = next((label for key, label in _SYSTEMS if key in user_agent), '')
    for name, pattern in _BROWSERS:
        found = re.search(pattern, user_agent)
        if found:
            return name, system, found.group(1)
    return '', system, ''


def device_label(user_agent):
    browser, system, version = _device(user_agent)
    return ' · '.join(part for part in (f'{browser} {version}'.strip(), system) if part) or "Noma'lum qurilma"


def record_login(user, ip, user_agent, via='Sayt'):
    """Call before the login is written to LoginLog, so it compares with earlier ones."""
    where = f'{device_label(user_agent)} · IP {ip}'
    url = f'/panel/users/{user.pk}/'
    if user.is_staff:
        known = _device(user_agent)[:2]
        earlier = user.login_logs.filter(status='success').order_by('-id').values_list('user_agent', flat=True)[:50]
        if not any(_device(agent)[:2] == known for agent in earlier):
            record_alert('security', f'Xodim hisobiga yangi qurilmadan kirildi: {user.display_name}', where, url, user)
            return
    record_alert('login', f'Kirish: {user.display_name}', f'{via} · {where}', url, user)
