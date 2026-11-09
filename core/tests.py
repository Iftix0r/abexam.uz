from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from users.models import User

from .middleware import SecurityBoundaryMiddleware
from .models import AuditLog


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    STAFF_SESSION_BINDING=True,
    STAFF_SESSION_MAX_AGE=14400,
)
class SecurityBoundaryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.staff = User.objects.create_superuser('security-boss', password='Strong-Pass-77')

    def request(self, path, ip='198.51.100.10', session=None):
        request = self.factory.get(path, REMOTE_ADDR=ip, HTTP_USER_AGENT='Test Browser 1')
        if session is None:
            SessionMiddleware(lambda r: HttpResponse()).process_request(request)
            request.session.save()
        else:
            request.session = session
        request.user = self.staff
        return request

    def test_export_is_audited_without_exported_data_in_log(self):
        request = self.request('/panel/users/export/')
        response = SecurityBoundaryMiddleware(lambda r: HttpResponse('private csv'))(request)
        self.assertEqual(response.status_code, 200)
        audit = AuditLog.objects.get(action='data_export')
        self.assertEqual(audit.target, '/panel/users/export/')
        self.assertNotIn('private csv', audit.details)

    def test_staff_session_change_is_terminated_and_logged(self):
        first = self.request('/dashboard/', ip='198.51.100.10')
        middleware = SecurityBoundaryMiddleware(lambda r: HttpResponse('ok'))
        self.assertEqual(middleware(first).status_code, 200)
        second = self.request('/dashboard/', ip='203.0.113.20', session=first.session)
        self.assertEqual(middleware(second).status_code, 302)
        self.assertTrue(AuditLog.objects.filter(action='session_hijack').exists())

    def test_backup_download_is_rate_limited(self):
        request = self.request('/system/backups/db.json.gz/download/')
        middleware = SecurityBoundaryMiddleware(lambda r: HttpResponse('backup'))
        self.assertEqual(middleware(request).status_code, 200)
        self.assertEqual(middleware(request).status_code, 200)
        self.assertEqual(middleware(request).status_code, 429)
