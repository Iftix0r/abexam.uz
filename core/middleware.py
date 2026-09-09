from django.http import JsonResponse
from django.shortcuts import render

from .models import SiteSettings


class PanelBadgeMiddleware:
    """Annotates request.pending_tx_count for staff, used by the panel
    sidebar's transaction badge (templates/panel/base.html)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/panel/') and request.user.is_authenticated and request.user.is_staff:
            from payments.models import Transaction
            request.pending_tx_count = Transaction.objects.filter(status='pending').count()
        return self.get_response(request)


class MaintenanceModeMiddleware:
    """When SiteSettings.maintenance_mode is on, blocks everyone except
    staff (who still need /panel/ and /admin/ to turn it back off)."""

    _ALLOWED_PREFIXES = ('/panel/', '/admin/', '/static/', '/media/', '/login/', '/users/logout/')

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
