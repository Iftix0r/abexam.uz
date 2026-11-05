import logging
import time

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from .models import SiteSettings

slow_query_logger = logging.getLogger('slow_queries')


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
