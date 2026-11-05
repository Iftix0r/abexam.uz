"""Traps: decoy pages no real visitor opens, and canary credentials that sit
in the decoy `admin_passwords` table. Whoever opens a decoy page is probing;
whoever uses a canary has read the database or a backup of it.

Reading the table itself cannot be seen from here (that needs auditing in the
database server); using what is in it can.
"""
import time

from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.db.models import F
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import CanaryToken
from .security import record_threat

DECOY_PATHS = ('/administrator/', '/backup/')
REFRESH_SECONDS = 60
_known = {'at': 0.0, 'login': frozenset(), 'api_key': frozenset()}


def _canaries():
    if time.monotonic() - _known['at'] > REFRESH_SECONDS:
        values = list(CanaryToken.objects.values_list('kind', 'value'))
        _known.update(at=time.monotonic(),
                      login=frozenset(v for k, v in values if k == 'login'),
                      api_key=frozenset(v for k, v in values if k == 'api_key'))
    return _known


def _tripped(kind, value, request=None, ip=None):
    CanaryToken.objects.filter(kind=kind, value=value).update(hits=F('hits') + 1, last_hit_at=timezone.now())
    label = 'Login' if kind == 'login' else 'API kalit'
    record_threat('canary', request, ip=ip, sample=f'{label}: {value}')


def check_request(request):
    """Called for every request by core.security: a canary key sent anywhere."""
    keys = _canaries()['api_key']
    if not keys:
        return
    header = request.headers.get('Authorization', '')
    sent = {header[7:].strip() if header.startswith('Bearer ') else header.strip(),
            request.headers.get('X-Api-Token', '').strip()}
    query = request.META.get('QUERY_STRING', '')
    for key in keys:
        if key in sent or key in query:
            _tripped('api_key', key, request)
            return


@receiver(user_login_failed)
def watch_canary_login(sender, credentials, request=None, **kwargs):
    """Fires for the site, the app and /admin/ logins alike. The password
    arrives masked, so only the username is compared."""
    username = str(credentials.get('username', '')).strip()
    if username and username in _canaries()['login']:
        _tripped('login', username, request)


@csrf_exempt
def decoy_login(request):
    """Looks like an admin login. Nothing behind it works."""
    if request.method == 'POST':
        username = str(request.POST.get('username', ''))[:60]
        record_threat('honeypot_login', request, sample=f'{request.path} · login: {username}')
        return render(request, 'honeypot/login.html', {'error': True}, status=200)
    record_threat('honeypot_visit', request)
    return render(request, 'honeypot/login.html')


def decoy_folder(request):
    record_threat('honeypot_visit', request)
    return HttpResponseForbidden('<h1>403 Forbidden</h1>')


def robots_txt(request):
    lines = ['User-agent: *', 'Disallow: /panel/', 'Disallow: /system/']
    lines += [f'Disallow: {path}' for path in DECOY_PATHS]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')
