from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from learn.models import ApiToken, DailyXP, LearnerProfile, LessonProgress, Mistake
from users.models import User


class EnglishPanelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('boss', password='pw', is_staff=True)
        self.student = User.objects.create_user('ali', password='pw', first_name='Ali')
        LearnerProfile.objects.create(user=self.student, level='A1', xp=40, streak=2, last_active=timezone.localdate())
        DailyXP.objects.create(user=self.student, date=timezone.localdate(), xp=40)
        LessonProgress.objects.create(user=self.student, lesson_slug='a1-hello', best_score=80, attempts=2)
        LessonProgress.objects.create(user=self.student, lesson_slug='story:a1-malikas-cat', best_score=100, attempts=1)
        Mistake.objects.create(user=self.student, lesson_slug='a1-hello', step_index=3)
        self.token = ApiToken.objects.create(user=self.student, key_hash='x' * 64, device='Samsung SM-A515F',
                                             platform='Android 14', app_version='1.2.0', ip='1.2.3.4')
        self.client.force_login(self.admin)

    def test_pages_need_staff(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('panel:english')).status_code, 302)

    def test_overview_learners_and_devices_render(self):
        overview = self.client.get(reverse('panel:english'))
        self.assertContains(overview, 'Tugallangan darslar')
        self.assertContains(overview, 'Hello! Nice to meet you')
        learners = self.client.get(reverse('panel:english_learners'), {'level': 'A1'})
        self.assertContains(learners, '@ali')
        self.assertContains(learners, 'Samsung SM-A515F')
        devices = self.client.get(reverse('panel:english_devices'), {'q': 'samsung'})
        self.assertContains(devices, 'Android 14')
        self.assertContains(self.client.get(reverse('panel:user_detail', args=[self.student.pk])), 'Ilova qurilmalari')

    def test_revoke_signs_the_device_out(self):
        resp = self.client.post(reverse('panel:english_device_revoke', args=[self.token.pk]), {'next': 'https://evil.example/'})
        self.assertRedirects(resp, reverse('panel:english_devices'), fetch_redirect_response=False)
        self.assertFalse(ApiToken.objects.exists())
