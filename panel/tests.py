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

    def test_publish_app_release(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from learn.models import AppRelease
        apk = SimpleUploadedFile('app-release.apk', b'PK fake apk', content_type='application/vnd.android.package-archive')
        resp = self.client.post(reverse('panel:english_app'), {'version': '1.4.0', 'build': 6, 'apk': apk, 'notes': 'Yangi'})
        self.assertRedirects(resp, reverse('panel:english_app'))
        release = AppRelease.objects.get()
        self.assertTrue(release.apk.name.startswith('app/'))
        self.assertContains(self.client.get(reverse('panel:english_app')), '1.4.0')
        self.client.post(reverse('panel:english_app_delete', args=[release.pk]))
        self.assertFalse(AppRelease.objects.exists())


class ExamToolsPanelTests(TestCase):
    """Test import, question analysis, notes editor and the progress chart."""

    def setUp(self):
        import tempfile
        from django.test import override_settings
        from exams.models import Exam, Question, Section
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(
            MEDIA_ROOT=self.media.name,
            STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
        self.override.enable()
        self.admin = User.objects.create_user('boss', password='pw', is_staff=True)
        self.client.force_login(self.admin)
        self.exam = Exam.objects.create(title='Panel tools', duration_minutes=60)
        self.section = Section.objects.create(exam=self.exam, title='Listening', section_type='listening', order=1)
        self.q = [Question.objects.create(section=self.section, order=n, question_type='gap_fill',
                                          correct_answer=ans, text=f'[Form] Complete.\nItem {n}: ___' if n == 1 else f'Item {n}: ___')
                  for n, ans in ((1, 'bed'), (2, 'post'), (3, 'airport'))]

    def tearDown(self):
        self.override.disable()
        self.media.cleanup()

    def test_import_lists_and_loads_a_seed_file(self):
        from exams.models import Exam
        page = self.client.get(reverse('panel:exam_import'))
        self.assertContains(page, 'ielts_full_mock_test_10.json')
        resp = self.client.post(reverse('panel:exam_import'), {'file': 'ielts_full_mock_test_10.json'})
        exam = Exam.objects.get(title='IELTS Full Mock Test 10')
        self.assertRedirects(resp, reverse('panel:exam_detail', args=[exam.pk]), fetch_redirect_response=False)
        self.assertEqual(exam.sections.get(order=1).questions.count(), 40)
        # only names from the listing are accepted
        self.client.post(reverse('panel:exam_import'), {'file': '../../core/settings.py'})
        self.assertEqual(Exam.objects.filter(title__startswith='IELTS').count(), 1)

    def test_analysis_flags_a_suspicious_key(self):
        from exams.models import UserAnswer, UserResult
        for i in range(6):
            student = User.objects.create_user(f's{i}', password='pw')
            result = UserResult.objects.create(user=student, exam=self.exam)
            # everyone writes "beds" for Q1 — the key is probably wrong
            for q, ans in zip(self.q, ('beds', 'post', '' if i < 2 else 'airport')):
                UserAnswer.objects.create(result=result, question=q, user_answer=ans)
        resp = self.client.get(reverse('panel:exam_analysis', args=[self.exam.pk]))
        self.assertEqual(resp.context['flagged'], 1)
        rows = resp.context['groups'][0]['rows']
        self.assertEqual((rows[0]['pct'], rows[0]['top_wrong']), (0, [('beds', 6)]))
        self.assertTrue(rows[0]['suspect'])
        self.assertEqual((rows[2]['right'], rows[2]['blank']), (4, 2))
        # fixing the key shows up straight away
        self.q[0].correct_answer = 'bed/beds'
        self.q[0].save()
        resp = self.client.get(reverse('panel:exam_analysis', args=[self.exam.pk]))
        self.assertEqual(resp.context['flagged'], 0)

    def test_notes_editor_saves_and_validates(self):
        url = reverse('panel:section_notes', args=[self.section.pk])
        self.assertContains(self.client.get(url), '[[1]]')
        resp = self.client.post(url, {'block': ['<p>Bed [[1]] and [[3]]</p>']})
        self.assertContains(resp, "ketma-ket")
        resp = self.client.post(url, {'block': ['<p>Bed [[9]]</p>']})
        self.assertContains(resp, "9 tartibli savol yo")
        self.client.post(url, {'block': ['<p>Bed [[1]] post [[2]]</p>', '']})
        self.section.refresh_from_db()
        self.assertEqual(self.section.extra_data['notes'], {'1': '<p>Bed [[1]] post [[2]]</p>'})
        self.client.post(url, {'block': ['']})
        self.section.refresh_from_db()
        self.assertNotIn('notes', self.section.extra_data)

    def test_user_progress_chart(self):
        from exams.models import UserResult
        student = User.objects.create_user('ali', password='pw')
        UserResult.objects.create(user=student, exam=self.exam, score=5.5, listening_score=6.0)
        UserResult.objects.create(user=student, exam=self.exam, score=6.5, listening_score=7.0, reading_score=6.5)
        resp = self.client.get(reverse('panel:user_detail', args=[student.pk]))
        self.assertContains(resp, 'progressChart')
        import json
        rows = json.loads(resp.context['progress_json'])
        self.assertEqual([r['l'] for r in rows], [6.0, 7.0])
        self.assertIsNone(rows[0]['r'])
