from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import SiteSettings
from exams.models import Exam, Section
from exams.views import clear_exam_paid, exam_is_paid
from users.models import User

from . import premium
from .models import PremiumPurchase


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class PremiumTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('ali', password='pw', first_name='Ali', balance=Decimal('120000'))
        self.boss = User.objects.create_user('boss', password='pw', is_staff=True)
        self.client.force_login(self.user)

    def test_finance_now_leads_to_premium(self):
        self.assertRedirects(self.client.get(reverse('finance')), reverse('premium'))
        self.assertContains(self.client.get(reverse('premium')), 'AB Premium')

    def test_menu_has_no_finance_section(self):
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'AB Premium')
        self.assertNotContains(page, 'Moliya')

    def test_buying_charges_once_and_activates(self):
        self.assertFalse(self.user.is_premium)
        self.client.post(reverse('premium_buy'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_premium)
        self.assertEqual(self.user.balance, Decimal('21000'))
        self.assertEqual(PremiumPurchase.objects.get().amount, Decimal('99000'))

    def test_short_balance_changes_nothing(self):
        User.objects.filter(pk=self.user.pk).update(balance=1000)
        self.client.post(reverse('premium_buy'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_premium)
        self.assertEqual(self.user.balance, 1000)
        self.assertFalse(PremiumPurchase.objects.exists())

    def test_get_cannot_buy(self):
        self.assertEqual(self.client.get(reverse('premium_buy')).status_code, 405)

    def test_renewal_adds_to_time_left(self):
        until = timezone.now() + timedelta(days=10)
        User.objects.filter(pk=self.user.pk).update(premium_until=until)
        self.user.refresh_from_db()
        premium.buy(self.user)
        self.assertEqual((self.user.premium_until - until).days, 30)

    def test_expired_premium_is_off_and_restarts_from_today(self):
        User.objects.filter(pk=self.user.pk).update(premium_until=timezone.now() - timedelta(days=3))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_premium)
        self.assertEqual(self.user.premium_days_left, 0)
        premium.buy(self.user)
        self.assertEqual(self.user.premium_days_left, 30)

    def test_price_comes_from_settings(self):
        settings_obj = SiteSettings.get()
        settings_obj.premium_price, settings_obj.premium_days = Decimal('50000'), 7
        settings_obj.save()
        cache.clear()
        premium.buy(self.user)
        self.assertEqual(self.user.balance, Decimal('70000'))
        self.assertEqual(self.user.premium_days_left, 7)

    def _paid_exam(self):
        exam = Exam.objects.create(title='Pullik', price=30000)
        Section.objects.create(exam=exam, title='R', section_type='reading')
        settings_obj = SiteSettings.get()
        settings_obj.exam_password_required = False
        settings_obj.save()
        cache.clear()
        clear_exam_paid(self.user.pk, exam.pk)
        return exam

    def test_premium_opens_paid_exam_without_charge(self):
        exam = self._paid_exam()
        User.objects.filter(pk=self.user.pk).update(premium_until=timezone.now() + timedelta(days=5), balance=0)
        response = self.client.get(reverse('exams:take_exam', args=[exam.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(exam_is_paid(self.user.pk, exam.pk))  # submit works even if Premium ends mid-exam
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, 0)

    def test_without_premium_the_exam_is_still_charged(self):
        exam = self._paid_exam()
        self.client.get(reverse('exams:take_exam', args=[exam.pk]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, Decimal('90000'))

    def test_staff_can_give_and_cancel(self):
        self.client.force_login(self.boss)
        url = reverse('panel:user_premium', args=[self.user.pk])
        self.client.post(url, '{"days": 14}', content_type='application/json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.premium_days_left, 14)
        self.assertEqual(PremiumPurchase.objects.get().granted_by, self.boss)
        self.client.post(url, '{"days": 0}', content_type='application/json')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_premium)

    def test_student_cannot_give_premium(self):
        self.client.post(reverse('panel:user_premium', args=[self.user.pk]), '{"days": 14}',
                         content_type='application/json')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_premium)
