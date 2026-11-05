"""Spots attacks on the site and records them for the panel's security tab.

Only the URL is inspected, never POST bodies: essays and chat messages may
quote anything, and passwords must stay out of the log. Counters live in this
process's memory because the file cache also holds the login throttle, and a
key per visitor would evict it.
"""
import ipaddress
import logging
import re
import time
from collections import Counter
from datetime import timedelta
from html import escape
from urllib.parse import unquote_plus

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import F, Q
from django.utils import timezone

from .alerts import record_alert
from .models import SecurityIncident
from .utils import get_client_ip, notify_admin_telegram

logger = logging.getLogger(__name__)

INCIDENT_WINDOW = timedelta(hours=1)  # hits inside this become one incident
LOGIN_WINDOW = timedelta(minutes=15)
KEEP_DAYS = 90
MAX_SAMPLES = 10
WRITE_EVERY = 2  # seconds: a scanner's hits are saved in batches, not one write each

# A classroom shares one IP, so visitors with a session get a far higher limit.
FLOOD_LIMIT_ANONYMOUS = 600  # requests per minute per IP, in one worker process
FLOOD_LIMIT_SESSION = 6000

SPRAY_ACCOUNTS = 8  # different accounts tried from one IP
DISTRIBUTED_IPS = 4  # different IPs trying one account
STAFF_FAILS = 3
BREACH_FAILS_STAFF = 3
BREACH_FAILS_STUDENT = 5

_SKIP_PREFIXES = ('/static/', '/media/', '/tg/')
_SCANNER_PATH = re.compile(
    r'(?:^|/)(?:\.env|\.git|\.svn|\.aws|\.ssh|\.htaccess|\.ds_store|wp-admin|wp-login|wp-content|wp-includes'
    r'|xmlrpc|phpmyadmin|adminer|cgi-bin|vendor/phpunit|actuator|server-status|boaform|hnap1|manager/html'
    r'|_ignition|telescope|id_rsa|web\.config|dump\.sql|db\.sql|database\.sql|backup\.(?:sql|zip|tar|gz))'
    r'(?:[/.?]|$)|\.(?:php\d?|asp|aspx|jsp|cgi|bak|sql)$')
_INJECTIONS = (
    ('sql_injection', re.compile(
        r"union\s+(?:all\s+)?select|\bor\s+\d+\s*=\s*\d+|'\s*or\s*'|\bsleep\(\d|benchmark\(|information_schema"
        r"|;\s*drop\s+table|load_file\(")),
    ('xss', re.compile(r'<script|javascript:|\bonerror\s*=|\bonload\s*=|document\.cookie')),
    ('traversal', re.compile(r'\.\./\.\./|/etc/passwd|/proc/self|c:\\windows')),
    ('code_exec', re.compile(
        r';\s*(?:cat|wget|curl|bash|sh|nc)\s|\|\s*(?:bash|sh)\b|\$\{jndi:|\{\{\s*\d+\s*\*\s*\d+\s*\}\}|\$\{\d+\*\d+\}')),
)

_writes = {}
_flood = {'minute': 0, 'hits': Counter()}


def _clean_ip(ip):
    try:
        return str(ipaddress.ip_address(str(ip).strip()))
    except ValueError:
        return '0.0.0.0'


def _batch(key, sample):
    """(hits, samples) to save now; no hits while they are still being gathered."""
    if len(_writes) > 5000:
        _writes.clear()
    now = time.monotonic()
    entry = _writes.setdefault(key, {'saved': 0.0, 'hits': 0, 'samples': []})
    entry['hits'] += 1
    if sample and sample not in entry['samples'] and len(entry['samples']) < MAX_SAMPLES:
        entry['samples'].append(sample)
    if now - entry['saved'] < WRITE_EVERY:
        return 0, []
    hits, samples = entry['hits'], entry['samples']
    entry.update(saved=now, hits=0, samples=[])
    return hits, samples


def record_threat(kind, request=None, ip=None, user_agent='', sample='', user=None):
    """Adds to this IP's open incident or opens one. Never raises."""
    if request is not None:
        ip = ip or get_client_ip(request)
        user_agent = user_agent or request.META.get('HTTP_USER_AGENT', '')
        sample = sample or unquote_plus(request.get_full_path())
    ip = _clean_ip(ip)
    hits, samples = _batch((kind, ip), str(sample)[:200])
    if not hits:
        return
    try:
        with transaction.atomic():
            incident = SecurityIncident.objects.filter(
                kind=kind, ip=ip, last_seen__gte=timezone.now() - INCIDENT_WINDOW).first()
            if incident:
                _extend(incident, hits, samples)
            else:
                _open(kind, ip, user_agent[:300], samples, user, hits)
    except DatabaseError:
        logger.exception('Security incident not saved')


def _extend(incident, hits, samples):
    kept = incident.samples + [sample for sample in samples if sample not in incident.samples]
    SecurityIncident.objects.filter(pk=incident.pk).update(
        hits=F('hits') + hits, last_seen=timezone.now(), samples=kept[-MAX_SAMPLES:])


def _open(kind, ip, user_agent, samples, user, hits):
    incident = SecurityIncident.objects.create(
        kind=kind, ip=ip, user_agent=user_agent, user=user, hits=hits, samples=samples, last_seen=timezone.now())
    if incident.pk % 200 == 0:
        SecurityIncident.objects.filter(last_seen__lt=timezone.now() - timedelta(days=KEEP_DAYS)).delete()
    if incident.severity == 'low':
        return
    first = samples[0] if samples else ''
    record_alert('security', f'{incident.label}: IP {ip}', first or incident.what,
                 f'/panel/threats/{incident.pk}/', user)
    if incident.severity == 'high':
        notify_admin_telegram(f'🚨 <b>{escape(incident.label)}</b>\n🌐 IP: {ip}\n🔎 {escape(first)}')


def _too_many_requests(request, ip):
    minute = int(time.time() // 60)
    if _flood['minute'] != minute:
        _flood['minute'], _flood['hits'] = minute, Counter()
    has_session = settings.SESSION_COOKIE_NAME in request.COOKIES
    _flood['hits'][ip, has_session] += 1
    limit = FLOOD_LIMIT_SESSION if has_session else FLOOD_LIMIT_ANONYMOUS
    return _flood['hits'][ip, has_session] % limit == 0


def _is_staff(request):
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated and user.is_staff)


def inspect_request(request):
    path = request.path
    if path.startswith(_SKIP_PREFIXES):
        return
    from .honeypot import check_request
    check_request(request)
    ip = get_client_ip(request)
    if _too_many_requests(request, ip):
        record_threat('flood', request)
    url = unquote_plus(unquote_plus(request.META.get('QUERY_STRING', '')[:2000]))
    target = f'{unquote_plus(path)}?{url}'.lower()
    for kind, pattern in _INJECTIONS:
        if pattern.search(target):
            if not _is_staff(request):  # panel searches may quote anything
                record_threat(kind, request)
            return
    if _SCANNER_PATH.search(path.lower()):
        record_threat('scan', request)


def record_from_log(record):
    """Django's own security warnings: forged forms, wrong Host headers, and the like."""
    request = getattr(record, 'request', None)
    if request is None:
        return
    if record.name == 'django.security.csrf':
        record_threat('csrf', request)
    elif record.name == 'django.security.DisallowedHost':
        record_threat('bad_host', request, sample=request.META.get('HTTP_HOST', ''))
    else:
        record_threat('suspicious', request)


def watch_failed_login(username, ip, user_agent):
    """Call after the failed attempt is in LoginLog."""
    from users.models import LoginLog, User
    fails = LoginLog.objects.filter(status__in=('failed', 'blocked'), created_at__gte=timezone.now() - LOGIN_WINDOW)
    if fails.filter(ip=ip).values('username_attempt').distinct().count() >= SPRAY_ACCOUNTS:
        record_threat('spray', ip=ip, user_agent=user_agent, sample=username)
    same_account = fails.filter(username_attempt=username)
    if same_account.values('ip').distinct().count() >= DISTRIBUTED_IPS:
        record_threat('distributed', ip=ip, user_agent=user_agent, sample=username)
    target = User.objects.filter(Q(username=username) | Q(phone_number=username), is_staff=True).first()
    if target and same_account.count() >= STAFF_FAILS:
        record_threat('staff_target', ip=ip, user_agent=user_agent, sample=username, user=target)


def watch_login_success(user, ip, user_agent):
    """Call before this login is in LoginLog. Many failures, then a success, may
    mean the password was guessed."""
    from users.models import LoginLog
    fails = LoginLog.objects.filter(
        Q(username_attempt=user.username) | Q(username_attempt=user.phone_number or user.username),
        status__in=('failed', 'blocked'), created_at__gte=timezone.now() - LOGIN_WINDOW).count()
    if fails >= (BREACH_FAILS_STAFF if user.is_staff else BREACH_FAILS_STUDENT):
        record_threat('breach', ip=ip, user_agent=user_agent, sample=f"{fails} ta xato urinishdan keyin kirdi", user=user)
