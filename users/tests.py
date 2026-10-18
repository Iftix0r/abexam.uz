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


class AccountDeleteTests(TestCase):
    """Google Play talabi: hisobni saytda ham o'chirish mumkin."""

    def setUp(self):
        self.user = User.objects.create_user('ali', password='right-pw-1')

    def test_needs_login(self):
        resp = self.client.get(reverse('account_delete'))
        self.assertRedirects(resp, f"{reverse('login')}?next={reverse('account_delete')}", fetch_redirect_response=False)

    def test_wrong_password_keeps_account(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('account_delete'), {'password': 'nope'})
        self.assertContains(resp, "Parol noto")
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_deletes_account_and_logs_out(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('account_delete'), {'password': 'right-pw-1'})
        self.assertContains(resp, "Hisobingiz o'chirildi")
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_staff_cannot_delete_here(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        self.client.post(reverse('account_delete'), {'password': 'right-pw-1'})
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_privacy_page_is_public(self):
        self.assertContains(self.client.get(reverse('privacy')), 'Maxfiylik siyosati')
