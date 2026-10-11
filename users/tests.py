from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class LoginThrottleTests(TestCase):
    """Bitta Wi-Fi (bitta IP) dagi o'quvchilardan birining xatolari boshqalarni bloklamaydi."""

    def setUp(self):
        cache.clear()
        User.objects.create_user('ali', password='right-pw-1')
        User.objects.create_user('vali', password='right-pw-2')

    def _login(self, username, password):
        return self.client.post(reverse('login'), {'username': username, 'password': password})

    def test_wrong_password_shows_error(self):
        resp = self._login('ali', 'nope')
        self.assertContains(resp, "parol noto&#x27;g&#x27;ri")

    def test_one_users_typos_dont_block_classmates(self):
        for _ in range(6):
            self._login('ali', 'nope')
        # ali is locked out, even with the right password...
        resp = self._login('ali', 'right-pw-1')
        self.assertRedirects(resp, reverse('login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)
        # ...but the login page still opens and vali on the same IP gets in.
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        resp = self._login('vali', 'right-pw-2')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session['_auth_user_id'], str(User.objects.get(username='vali').pk))

    def test_whole_ip_blocked_only_after_many_failures(self):
        from users import views
        for i in range(views._MAX_FAILS_PER_IP):
            self._login(f'nobody{i}', 'nope')
        self._login('vali', 'right-pw-2')
        self.assertNotIn('_auth_user_id', self.client.session)
