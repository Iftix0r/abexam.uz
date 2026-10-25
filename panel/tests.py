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

    def test_dashboard_todo_links_to_pending_work(self):
        from exams.models import UserResult
        student = User.objects.create_user('vali', password='pw')
        UserResult.objects.create(user=student, exam=self.exam, status=UserResult.STATUS_PENDING)
        resp = self.client.get(reverse('panel:dashboard'))
        self.assertEqual(resp.context['todo']['pending_results'], 1)
        self.assertContains(resp, 'Writing baholash')
        self.assertContains(resp, f"{reverse('panel:result_grade', args=[UserResult.objects.get().pk])}")


class PanelWorkflowTests(TestCase):
    """Re-grading, audit log, key editing, groups, Telegram alerts, report."""

    def setUp(self):
        from exams.models import Exam, Question, Section
        self.admin = User.objects.create_superuser('boss', password='pw')
        self.client.force_login(self.admin)
        self.exam = Exam.objects.create(title='Workflow', duration_minutes=60)
        self.listening = Section.objects.create(exam=self.exam, title='Listening', section_type='listening', order=1)
        self.qs = [Question.objects.create(section=self.listening, order=n, question_type='gap_fill',
                                           correct_answer=ans, text=f'Item {n}: ___')
                   for n, ans in ((1, 'bed'), (2, 'post'))]
        self.reading = Section.objects.create(exam=self.exam, title='Reading', section_type='reading', order=2)
        self.yn = Question.objects.create(section=self.reading, order=41, question_type='tfng', correct_answer='NO',
                                          text='Claim', options=[{'key': k, 'text': k} for k in ('YES', 'NO', 'NOT GIVEN')])

    def _result(self, username, answers):
        from exams.views import create_result
        student = User.objects.create_user(username, password='pw')
        return create_result(student, self.exam, {str(q.id): a for q, a in answers})

    def test_regrade_after_key_fix(self):
        from core.models import AuditLog
        result = self._result('ali', [(self.qs[0], 'beds'), (self.qs[1], 'post'), (self.yn, 'YES')])
        self.assertFalse(result.answers.get(question=self.qs[0]).is_correct)
        old_listening = result.listening_score
        self.qs[0].correct_answer = 'bed/beds'
        self.qs[0].save()
        resp = self.client.post(reverse('panel:exam_regrade', args=[self.exam.pk]))
        self.assertRedirects(resp, reverse('panel:exam_analysis', args=[self.exam.pk]), fetch_redirect_response=False)
        result.refresh_from_db()
        self.assertTrue(result.answers.get(question=self.qs[0]).is_correct)
        self.assertGreater(result.listening_score, old_listening)
        self.assertEqual(AuditLog.objects.get().action, 'exam_regrade')

    def test_key_edit_keeps_yes_no_and_choose_two(self):
        from core.models import AuditLog
        from exams.models import Question
        url = reverse('panel:question_edit', args=[self.yn.pk])
        self.assertContains(self.client.get(url), 'value="yn:NO" selected')
        self.client.post(url, {'text': 'Claim', 'question_type': 'tfng', 'correct_answer_tfng': 'yn:YES'})
        self.yn.refresh_from_db()
        self.assertEqual(self.yn.correct_answer, 'YES')
        self.assertEqual([o['key'] for o in self.yn.options], ['YES', 'NO', 'NOT GIVEN'])
        log = AuditLog.objects.get(action='question_key')
        self.assertEqual(log.details, 'NO → YES')

        two = Question.objects.create(section=self.listening, order=3, question_type='mcq', correct_answer='C/E',
                                      text='Which TWO?', options=[{'key': k, 'text': k} for k in 'ABCDE'])
        resp = self.client.post(reverse('panel:question_edit', args=[two.pk]), {
            'text': 'Which TWO?', 'question_type': 'mcq', 'option_text': list('ABCDE'),
            'correct_option': '-1', 'correct_answer_multi': 'b / d'})
        self.assertEqual(resp.status_code, 302)
        two.refresh_from_db()
        self.assertEqual(two.correct_answer, 'B/D')

    def test_balance_change_is_logged_and_audit_page_is_superuser_only(self):
        import json
        from core.models import AuditLog
        student = User.objects.create_user('vali', password='pw')
        self.client.post(reverse('panel:user_balance', args=[student.pk]),
                         data=json.dumps({'amount': 50000, 'note': 'naqd'}), content_type='application/json')
        entry = AuditLog.objects.get(action='balance')
        self.assertIn('+50,000', entry.details)
        self.assertEqual(entry.staff, self.admin)
        self.assertContains(self.client.get(reverse('panel:audit')), "Balans o&#x27;zgartirildi")
        staff = User.objects.create_user('helper', password='pw', is_staff=True)
        self.client.force_login(staff)
        self.assertRedirects(self.client.get(reverse('panel:audit')), reverse('panel:dashboard'), fetch_redirect_response=False)

    def test_groups_members_and_filters(self):
        from users.models import StudyGroup
        self.client.post(reverse('panel:groups'), {'name': 'Ertalabki'})
        group = StudyGroup.objects.get()
        ali = User.objects.create_user('ali', password='pw', first_name='Ali')
        vali = User.objects.create_user('vali', password='pw')
        self.assertEqual(self.client.get(reverse('panel:group_member_search', args=[group.pk]), {'q': 'ali'}).json()['users'][0]['id'], ali.pk)
        self.client.post(reverse('panel:group_detail', args=[group.pk]), {'action': 'add', 'user_id': ali.pk})
        self.assertEqual(list(group.members.all()), [ali])
        self._result('x', [])  # someone outside the group
        from exams.views import create_result
        create_result(ali, self.exam, {str(self.qs[0].id): 'bed'})
        resp = self.client.get(reverse('panel:results'), {'group': group.pk})
        self.assertEqual([r.user for r in resp.context['results']], [ali])
        page = self.client.get(reverse('panel:group_detail', args=[group.pk]))
        self.assertEqual(page.context['rows'][0]['user'], ali)
        import json
        self.client.post(reverse('panel:users_bulk'), data=json.dumps({'action': 'add_group', 'ids': [vali.pk], 'group': group.pk}),
                         content_type='application/json')
        self.assertEqual(group.members.count(), 2)
        self.client.post(reverse('panel:group_detail', args=[group.pk]),
                         {'action': 'remove', 'user_id': ali.pk, 'back': reverse('panel:user_detail', args=[ali.pk])})
        self.assertEqual(group.members.count(), 1)

    def test_telegram_alerts(self):
        from unittest import mock
        from exams.models import Section, Question
        writing = Section.objects.create(exam=self.exam, title='Writing', section_type='writing', order=3)
        task = Question.objects.create(section=writing, order=81, question_type='writing_task', text='Essay')
        with mock.patch('core.utils.notify_admin_telegram') as tg:
            self._result('w1', [(task, 'my essay')])
        self.assertIn('Writing baholash kerak', tg.call_args[0][0])
        # five students all answer Q1 "beds" → the key "bed" looks wrong
        with mock.patch('core.utils.notify_admin_telegram') as tg:
            for i in range(5):
                self._result(f's{i}', [(self.qs[0], 'beds'), (self.qs[1], 'post')])
        alerts = [c[0][0] for c in tg.call_args_list if 'Kalitni tekshiring' in c[0][0]]
        self.assertEqual(len(alerts), 1)
        self.assertIn('beds', alerts[0])

    def test_progress_report(self):
        from exams.views import create_result
        ali = User.objects.create_user('ali', password='pw', first_name='Ali')
        create_result(ali, self.exam, {str(self.qs[0].id): 'bed', str(self.yn.id): 'YES'})
        create_result(ali, self.exam, {str(self.qs[0].id): 'bed', str(self.qs[1].id): 'post', str(self.yn.id): 'NO'})
        resp = self.client.get(reverse('panel:user_report', args=[ali.pk]))
        self.assertContains(resp, 'IELTS progress hisoboti')
        self.assertEqual(len(resp.context['results']), 2)
        self.assertGreater(resp.context['change'], 0)
