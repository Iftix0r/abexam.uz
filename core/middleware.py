import logging
import time
import hashlib
import ipaddress

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from .models import SiteSettings

slow_query_logger = logging.getLogger('slow_queries')


class SecurityBoundaryMiddleware:
    """Protects privileged sessions and audits bulk/sensitive downloads.

    It records metadata only — never cookies, passwords, tokens, response
    bodies or exported personal data.
    """

    SENSITIVE = {
        '/panel/users/export/': ('data_export', 20, 3600),
        '/panel/results/export/': ('data_export', 20, 3600),
        '/panel/transactions/export/': ('data_export', 20, 3600),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _network(ip):
        try:
            address = ipaddress.ip_address(ip)
            prefix = 24 if address.version == 4 else 64
            return str(ipaddress.ip_network(f'{address}/{prefix}', strict=False))
        except ValueError:
            return 'unknown'

    @staticmethod
    def _ua(request):
        raw = request.META.get('HTTP_USER_AGENT', '')
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    def _guard_staff_session(self, request):
        user = request.user
        if not (user.is_authenticated and user.is_staff):
            return None
        now = int(time.time())
        started = request.session.get('staff_auth_at')
        if not started:
            request.session['staff_auth_at'] = now
            started = now
        if now - int(started) > settings.STAFF_SESSION_MAX_AGE:
            logout(request)
            return redirect('/login/?expired=1')
        if not settings.STAFF_SESSION_BINDING:
            return None

        from .utils import get_client_ip, notify_admin_telegram
        current = f'{self._network(get_client_ip(request))}|{self._ua(request)}'
        bound = request.session.get('staff_client_binding')
        if not bound:
            request.session['staff_client_binding'] = current
            return None
        if bound == current:
            return None

        from .alerts import record_alert
        from .audit import log_action
        from .security import record_threat
        name = user.display_name
        log_action(request, 'session_hijack', target=name,
                   details='Sessiya IP tarmog‘i yoki brauzeri o‘zgardi; sessiya bekor qilindi.')
        record_alert('security', f'Admin sessiyasi bekor qilindi: {name}',
                     f'IP yoki brauzer kutilmaganda o‘zgardi · {get_client_ip(request)}', '/panel/login-sessions/', user)
        record_threat('suspicious', request, user=user, sample='staff session binding changed')
        notify_admin_telegram(
            f'🚨 <b>Admin sessiyasi bekor qilindi</b>\n👤 {name}\n🌐 IP: {get_client_ip(request)}\n'
            'Sabab: IP tarmog‘i yoki brauzer o‘zgardi.')
        logout(request)
        return redirect('/login/?security=1')

    def _sensitive_kind(self, path):
        if path in self.SENSITIVE:
            return self.SENSITIVE[path]
        if path.startswith('/panel/groups/') and path.endswith('/export/'):
            return 'data_export', 20, 3600
        if path.startswith('/panel/exam-days/') and path.endswith('/export/'):
            return 'data_export', 20, 3600
        if path.startswith('/system/backups/') and path.endswith('/download/'):
            return 'backup_download', 2, 3600
        if path.startswith('/system/files/download/'):
            return 'sensitive_file', 5, 3600
        return None

    def __call__(self, request):
        guarded = self._guard_staff_session(request)
        if guarded is not None:
            return guarded

        sensitive = self._sensitive_kind(request.path)
        if sensitive and request.user.is_authenticated and request.user.is_staff:
            action, limit, window = sensitive
            key = f'sensitive:{request.user.pk}:{action}'
            count = cache.get(key, 0) + 1
            cache.set(key, count, window)
            if count > limit:
                from .alerts import record_alert
                from .security import record_threat
                record_threat('suspicious', request, user=request.user,
                              sample=f'{action} rate limit exceeded')
                record_alert('security', f'Ko‘p marotaba yuklab olish to‘xtatildi: {request.user.display_name}',
                             f'{action} · {count} ta urinish', '/panel/login-sessions/', request.user)
                response = HttpResponse('Yuklab olish limiti oshdi. Keyinroq urinib ko‘ring.', status=429)
                response['Retry-After'] = str(window)
                return response

        response = self.get_response(request)
        if sensitive and request.user.is_authenticated and request.user.is_staff and response.status_code < 400:
            from .alerts import record_alert
            from .audit import ACTIONS, log_action
            from .utils import get_client_ip, notify_admin_telegram
            action = sensitive[0]
            detail = (f'Yo‘l: {request.path} · IP: {get_client_ip(request)} · '
                      f'Brauzer: {request.META.get("HTTP_USER_AGENT", "")[:120]}')
            log_action(request, action, target=request.path, details=detail)
            record_alert('security', f'{ACTIONS[action]}: {request.user.display_name}', detail,
                         '/system/staff-audit/', request.user)
            if action in ('backup_download', 'sensitive_file'):
                notify_admin_telegram(
                    f'⚠️ <b>{ACTIONS[action]}</b>\n👤 {request.user.display_name}\n'
                    f'🌐 IP: {get_client_ip(request)}\n📁 {request.path}')
        return response


class SlowQueryLogMiddleware:
    """Times every SQL query for the request and logs the ones slower than
    settings.SLOW_QUERY_THRESHOLD to logs/slow_queries.log — works
    regardless of DEBUG (unlike connection.queries, which only fills in
    when DEBUG=True), since it hooks the query executor directly."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        threshold = settings.SLOW_QUERY_THRESHOLD
        if threshold <= 0:
            return self.get_response(request)

        def wrapper(execute, sql, params, many, context):
            start = time.monotonic()
            try:
                return execute(sql, params, many, context)
            finally:
                duration = time.monotonic() - start
                if duration >= threshold:
                    slow_query_logger.warning('%.3fs  %s  [%s]', duration, sql[:300], request.path)

        with connection.execute_wrapper(wrapper):
            return self.get_response(request)


class ThreatWatchMiddleware:
    """Checks each request's URL for attacks; see core/security.py."""

    def __init__(self, get_response):
        self.get_response = get_response

    PERMISSIONS = 'camera=(self), microphone=(self), geolocation=(self), payment=(), usb=()'

    def __call__(self, request):
        from .blocking import refuse_blocked
        from .security import inspect_request
        from .utils import get_client_ip
        if not request.path.startswith('/tg/'):  # Telegram's servers, never a visitor
            refused = refuse_blocked(request, get_client_ip(request))
            if refused is not None:
                refused.headers.setdefault('Permissions-Policy', self.PERMISSIONS)
                if getattr(settings, 'CONTENT_SECURITY_POLICY', ''):
                    refused.headers.setdefault('Content-Security-Policy', settings.CONTENT_SECURITY_POLICY)
                return refused
        inspect_request(request)

        if (request.path.startswith('/panel/') or request.path.startswith('/admin/')) \
                and request.user.is_authenticated and request.user.is_staff \
                and request.path != '/panel/location-required/' \
                and not request.session.get('staff_location_verified'):
            from django.shortcuts import redirect
            location_redirect = redirect('/panel/location-required/?next=' + request.path)
            location_redirect.headers.setdefault('Permissions-Policy', self.PERMISSIONS)
            if getattr(settings, 'CONTENT_SECURITY_POLICY', ''):
                location_redirect.headers.setdefault('Content-Security-Policy', settings.CONTENT_SECURITY_POLICY)
            return location_redirect

        response = self.get_response(request)
        # Staff panel actions require browser permissions for camera, microphone and location.
        response.headers.setdefault('Permissions-Policy', self.PERMISSIONS)
        if getattr(settings, 'CONTENT_SECURITY_POLICY', ''):
            response.headers.setdefault('Content-Security-Policy', settings.CONTENT_SECURITY_POLICY)
        return response


class PanelBadgeMiddleware:
    """Annotates request.pending_tx_count / pending_results_count for
    staff, used by the panel sidebar badges (templates/panel/base.html)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/panel/') and request.user.is_authenticated and request.user.is_staff:
            from payments.models import Transaction
            request.pending_tx_count = Transaction.objects.filter(status='pending').count()
            from exams.models import UserResult
            request.pending_results_count = UserResult.objects.pending().count()
            from django.utils import timezone
            from exams.models import ATTEMPT_ONLINE_WINDOW, ExamAttempt
            request.active_attempts_count = ExamAttempt.objects.filter(
                submitted_at__isnull=True, last_seen_at__gte=timezone.now() - ATTEMPT_ONLINE_WINDOW,
            ).count()
            from chat.models import ChatReport
            request.chat_reports_count = (ChatReport.objects.filter(resolved_at__isnull=True)
                                          .values('message').distinct().count())
            from chat.services import support_unread_total, team_unread
            request.chat_support_unread = support_unread_total()
            request.chat_team_unread = team_unread(request.user)
            from .models import StaffAlert
            request.staff_alerts_unread = StaffAlert.unread_for(request.user).count()
            request.staff_alerts_last = (StaffAlert.objects.exclude(kind__in=StaffAlert.QUIET).order_by('-id')
                                         .values_list('id', flat=True).first() or 0)
        return self.get_response(request)


class MaintenanceModeMiddleware:
    """When SiteSettings.maintenance_mode is on, blocks everyone except
    staff (who still need /panel/ and /admin/ to turn it back off)."""

    _ALLOWED_PREFIXES = ('/panel/', '/admin/', '/static/', '/media/', '/login/', '/users/logout/', '/tg/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(self._ALLOWED_PREFIXES):
            return self.get_response(request)

        settings_obj = SiteSettings.get()
        if settings_obj.maintenance_mode and not (request.user.is_authenticated and request.user.is_staff):
            # Exam submission, top-up, and chat all expect JSON and would
            # otherwise choke trying to parse the HTML maintenance page.
            wants_json = (
                request.content_type == 'application/json'
                or request.headers.get('x-requested-with') == 'XMLHttpRequest'
                or 'application/json' in request.headers.get('accept', '')
            )
            if wants_json:
                return JsonResponse({
                    'error': settings_obj.maintenance_message or "Sayt texnik ishlar uchun vaqtincha to'xtatilgan.",
                }, status=503)
            return render(request, 'maintenance.html', {
                'message': settings_obj.maintenance_message,
                'site_name': settings_obj.site_name,
            }, status=503)

        return self.get_response(request)
