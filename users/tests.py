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


class PhoneSignupTests(TestCase):
    """Ro'yxat: ism, familiya, telefon, parol. Kirish: telefon + parol."""

    def _register(self, **overrides):
        data = {'first_name': 'Ali', 'last_name': 'Valiyev', 'phone_number': '+998 90 412 09 77',
                'password': 'Very-Strong-77', **overrides}
        return self.client.post(reverse('register'), data)

    def test_register_logs_in_and_normalizes_phone(self):
        resp = self._register()
        self.assertRedirects(resp, reverse('dashboard'), fetch_redirect_response=False)
        user = User.objects.get()
        self.assertEqual((user.phone_number, user.username, user.get_full_name()),
                         ('+998904120977', '998904120977', 'Ali Valiyev'))
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))

    def test_only_real_uzbek_mobile_numbers(self):
        for fake in ('12345', '+1 202 555 0143', '+998 12 345 67 89', '+998 90 000 00 00',
                     '+998 90 123 45 67 8', '90 123 4567 89', '+998 91 234 56 78x'):
            resp = self._register(phone_number=fake)
            self.assertEqual(resp.status_code, 200, fake)
        self.assertFalse(User.objects.exists())
        for ok in ('+998 33 412 09 77', '99 870 15 42'):
            self.client.logout()
            self.assertEqual(self._register(phone_number=ok).status_code, 302, ok)
        self.assertEqual(User.objects.count(), 2)

    def test_all_four_fields_required(self):
        for field in ('first_name', 'last_name', 'phone_number', 'password'):
            self._register(**{field: ''})
        self.assertFalse(User.objects.exists())

    def test_same_phone_in_another_format_is_rejected(self):
        User.objects.create_user('old', password='x', phone_number='904120977')
        resp = self._register(phone_number='998904120977')
        self.assertContains(resp, 'allaqachon bor')
        self.assertEqual(User.objects.count(), 1)

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_login_with_phone_in_any_format_or_old_username(self):
        user = User.objects.create_user('ali', password='right-pw-1', phone_number='+998904120977')
        for login_as in ('90 412 09 77', '+998 (90) 412-09-77', 'ali'):
            self.client.logout()
            resp = self.client.post(reverse('login'), {'username': login_as, 'password': 'right-pw-1'})
            self.assertEqual(resp.status_code, 302, login_as)
            self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))
        self.client.logout()
        resp = self.client.post(reverse('login'), {'username': '904120977', 'password': 'nope'})
        self.assertContains(resp, "Telefon raqam yoki parol")


class StaffLoginFieldTests(TestCase):
    """Admins sign in with a username; on iPhone a tel field can't type letters."""

    def test_panel_redirect_gives_a_text_login_field(self):
        resp = self.client.get(reverse('panel:dashboard'))
        login_page = self.client.get(resp.url)
        self.assertContains(login_page, 'type="text" autocomplete="username"')
        self.assertContains(login_page, 'Login (username yoki telefon)')
        self.assertContains(self.client.get(reverse('login')), 'type="tel"')

    def test_admin_logs_in_with_username_from_panel(self):
        User.objects.create_user('boss', password='Very-Strong-77', is_staff=True)
        resp = self.client.post(reverse('login') + '?next=/panel/',
                                {'username': 'boss', 'password': 'Very-Strong-77', 'next': '/panel/'})
        self.assertRedirects(resp, '/panel/', fetch_redirect_response=False)

    def test_failed_username_attempt_keeps_the_text_field(self):
        page = self.client.post(reverse('login'), {'username': 'boss', 'password': 'wrong'})
        self.assertContains(page, 'type="text" autocomplete="username"')


class HiddenSectionsTests(TestCase):
    def test_vocabulary_is_off_the_menu_but_still_opens(self):
        user = User.objects.create_user('ali', password='pw')
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse('dashboard')), reverse('vocabulary'))
        self.assertEqual(self.client.get(reverse('vocabulary')).status_code, 200)


class PublicNameTests(TestCase):
    def test_full_name_and_no_phone_number(self):
        self.assertEqual(User(username='x', first_name='Ali', last_name='Valiyev').public_name, 'Ali Valiyev')
        self.assertEqual(User(username='alijon').public_name, 'alijon')
        phone_signup = User(username='998901234567', phone_number='+998901234567')
        self.assertEqual(phone_signup.public_name, 'Talaba')


class AdminPanelLinkTests(TestCase):
    def test_only_staff_see_the_link(self):
        self.client.force_login(User.objects.create_user('ali', password='pw'))
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Admin panel')
        self.assertNotContains(self.client.get(reverse('learn:hub')), 'Admin panel')
        self.client.force_login(User.objects.create_user('boss', password='pw', is_staff=True))
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'Admin panel')
        self.assertContains(page, reverse('panel:dashboard'))
        self.assertContains(self.client.get(reverse('learn:hub')), 'Admin panel')


class ProfileDetailsTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user('ali', password='pw', first_name='Ali')
        self.client.force_login(self.user)
        self.good = {'birth_day': 15, 'birth_month': 3, 'birth_year': 2000,
                     'region': "Farg'ona viloyati", 'district': "Qo'qon shahri"}

    def _save(self, **changes):
        return self.client.post(reverse('profile_details'), {**self.good, **changes}).json()

    def test_window_shows_until_the_details_are_saved(self):
        self.assertContains(self.client.get(reverse('dashboard')), 'detailsAsk')
        self.assertTrue(self._save()['ok'])
        self.assertNotContains(self.client.get(reverse('dashboard')), 'detailsAsk')

    def test_details_are_stored(self):
        self._save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.birth_date.isoformat(), '2000-03-15')
        self.assertEqual((self.user.region, self.user.district), ("Farg'ona viloyati", "Qo'qon shahri"))
        self.assertFalse(self.user.needs_details)

    def test_staff_are_not_asked(self):
        self.user.is_staff = True
        self.user.save()
        self.assertNotContains(self.client.get(reverse('dashboard')), 'detailsAsk')

    def test_impossible_date_is_refused(self):
        self.assertFalse(self._save(birth_day=31, birth_month=2)['ok'])

    def test_children_under_thirteen_are_refused_and_not_stored(self):
        from django.utils import timezone
        self.assertFalse(self._save(birth_year=timezone.localdate().year - 5)['ok'])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.birth_date)

    def test_district_must_belong_to_the_region(self):
        self.assertFalse(self._save(district='Chilonzor')['ok'])

    def test_missing_field_is_refused(self):
        self.assertFalse(self._save(region='')['ok'])

    def test_anonymous_visitors_cannot_save(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse('profile_details'), self.good).status_code, 302)

    def test_profile_page_edits_details_without_a_window(self):
        page = self.client.get(reverse('profile'))
        self.assertContains(page, 'birth_year')
        self.assertNotContains(page, 'detailsAsk')
        self.client.post(reverse('profile'), {'first_name': 'Ali', **self.good})
        self.user.refresh_from_db()
        self.assertEqual(self.user.district, "Qo'qon shahri")

    def test_profile_form_without_details_still_saves(self):
        self.client.post(reverse('profile'), {'first_name': 'Vali', 'birth_day': '', 'region': ''})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Vali')

    def test_bad_details_on_the_profile_save_nothing(self):
        self.client.post(reverse('profile'), {'first_name': 'Vali', **self.good, 'district': 'Chilonzor'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Ali')

    def test_other_students_never_see_the_details(self):
        self._save()
        # The other student has filled theirs in, so no window lists the districts.
        other = User.objects.create_user('vali', password='pw', birth_date='2000-01-01',
                                         region='Toshkent shahri', district='Chilonzor')
        self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse('rating')), "Qo&#x27;qon shahri")
        self.assertNotContains(self.client.get(reverse('rating')), "Qo'qon shahri")

    def test_admin_sees_filters_and_exports_them(self):
        self._save()
        boss = User.objects.create_superuser('boss', password='pw')
        self.client.force_login(boss)
        self.assertContains(self.client.get(reverse('panel:user_detail', args=[self.user.pk])), "Qo&#x27;qon shahri")
        page = self.client.get(reverse('panel:users'), {'region': "Farg'ona viloyati"})
        self.assertEqual([u.pk for u in page.context['users']], [self.user.pk])
        body = self.client.get(reverse('panel:users_export')).content.decode('utf-8-sig')
        self.assertIn('2000-03-15', body)

