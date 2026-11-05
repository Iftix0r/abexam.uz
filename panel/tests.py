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

