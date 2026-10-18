import io
import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Notification
from users.models import User
from .models import Exam, ExamAttempt, Question, Section, UserResult
from .views import calc_writing_band, round_band


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class ManualWritingGradingTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user('student', password='pw')
        self.admin = User.objects.create_user('admin', password='pw', is_staff=True)
        self.exam = Exam.objects.create(title='Mock 1', price=0)
        reading = Section.objects.create(exam=self.exam, title='Reading', section_type='reading', order=1)
        self.q_read = Question.objects.create(
            section=reading, text='Capital of France?', question_type='gap_fill',
            correct_answer='SECRETANSWER', order=1,
        )
        writing = Section.objects.create(exam=self.exam, title='Writing', section_type='writing', order=2)
        self.w1 = Question.objects.create(section=writing, text='Task 1 prompt', question_type='writing_task', order=1)
        self.w2 = Question.objects.create(section=writing, text='Task 2 prompt', question_type='writing_task', order=2)

    def _submit(self, answers):
        self.client.force_login(self.student)
        resp = self.client.post(
            reverse('exams:submit_exam', args=[self.exam.pk]),
            data=json.dumps({'answers': answers}), content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_writing_exam_is_held_pending_until_graded(self):
        data = self._submit({str(self.q_read.id): 'SECRETANSWER', str(self.w1.id): 'essay one', str(self.w2.id): 'essay two'})
        self.assertTrue(data['pending'])
        self.assertNotIn('score', data)
        result = UserResult.objects.get(pk=data['result_id'])
        self.assertTrue(result.is_pending)

        page = self.client.get(reverse('exams:result_detail', args=[result.pk]))
        self.assertContains(page, 'Natija hisoblanmoqda')
        self.assertNotContains(page, 'SECRETANSWER')
        self.assertNotContains(page, 'IELTS Band Score')

        self.client.force_login(self.admin)
        listing = self.client.get(reverse('panel:results') + '?status=pending')
        self.assertContains(listing, reverse('panel:result_grade', args=[result.pk]))
        form = self.client.get(reverse('panel:result_grade', args=[result.pk]))
        self.assertContains(form, 'essay two')
        self.assertContains(form, '1/1 to')  # reading correct-count shown to the grader
        # Band values must be posted in a parseable form regardless of the
        # site locale ('uz' renders floats as "6,0").
        self.assertContains(form, 'name="task1_band" id="task1_b11" value="6.0"')

        # Missing a task band → error, nothing released
        resp = self.client.post(reverse('panel:result_grade', args=[result.pk]), {'task1_band': '6.0'})
        self.assertEqual(resp.status_code, 200)
        result.refresh_from_db()
        self.assertTrue(result.is_pending)

        post = {
            'task1_band': '6.0', 'task1_feedback': 'feedback 1',
            'task2_band': '7.0', 'task2_lexical_resource': '7.5', 'task2_feedback': 'feedback 2',
            'speaking_band': '',
        }
        resp = self.client.post(reverse('panel:result_grade', args=[result.pk]), post)
        self.assertEqual(resp.status_code, 302)

        result.refresh_from_db()
        self.assertFalse(result.is_pending)
        self.assertEqual(result.writing_score, 6.5)  # (6 + 2*7) / 3 = 6.67 → 6.5
        self.assertEqual(result.graded_by, self.admin)
        self.assertTrue(Notification.objects.filter(user=self.student).exists())

        self.client.force_login(self.student)
        page = self.client.get(reverse('exams:result_detail', args=[result.pk]))
        self.assertContains(page, 'IELTS Band Score')
        self.assertContains(page, 'feedback 2')
        # Correct answers stay hidden from students even after grading
        self.assertNotContains(page, 'SECRETANSWER')

    def test_in_person_speaking_counts_toward_overall(self):
        data = self._submit({str(self.q_read.id): 'SECRETANSWER', str(self.w1.id): 'a', str(self.w2.id): 'b'})
        self.client.force_login(self.admin)
        url = reverse('panel:result_grade', args=[data['result_id']])
        self.client.post(url, {'task1_band': '6.0', 'task2_band': '6.0', 'speaking_band': '7.0',
                               'speaking_pronunciation': '7.0', 'speaking_feedback': 'good fluency'})
        result = UserResult.objects.get(pk=data['result_id'])
        self.assertEqual(result.speaking_score, 7.0)
        # reading 9.0 (1/1), writing 6.0, speaking 7.0 → 22/3 = 7.33 → 7.5
        self.assertEqual(result.score, 7.5)

        self.client.force_login(self.student)
        page = self.client.get(reverse('exams:result_detail', args=[result.pk]))
        self.assertContains(page, 'good fluency')

        # Clearing speaking later removes it from the overall band
        self.client.force_login(self.admin)
        self.client.post(url, {'task1_band': '6.0', 'task2_band': '6.0', 'speaking_band': ''})
        result.refresh_from_db()
        self.assertEqual(result.speaking_score, 0.0)
        self.assertEqual(result.score, 7.5)  # (9 + 6) / 2

    def test_exam_without_writing_is_graded_immediately(self):
        Question.objects.filter(question_type='writing_task').delete()
        Section.objects.filter(section_type='writing').delete()
        data = self._submit({str(self.q_read.id): 'SECRETANSWER'})
        self.assertNotIn('pending', data)
        self.assertGreater(data['score'], 0)
        page = self.client.get(reverse('exams:result_detail', args=[data['result_id']]))
        self.assertContains(page, '1/1 to')
        self.assertNotContains(page, 'SECRETANSWER')

    def test_answers_hidden_from_everyone(self):
        # Result pages never carry the answer key — not even for staff, and
        # no query param unlocks it.
        data = self._submit({str(self.q_read.id): 'wrong', str(self.w1.id): 'a', str(self.w2.id): 'b'})
        url = reverse('exams:result_detail', args=[data['result_id']])
        for user in (self.admin, self.student):
            self.client.force_login(user)
            self.assertNotContains(self.client.get(url), 'SECRETANSWER')
            self.assertNotContains(self.client.get(url + '?answers=1'), 'SECRETANSWER')

    def test_band_rounding(self):
        self.assertEqual(round_band(6.25), 6.5)
        self.assertEqual(round_band(6.75), 7.0)
        self.assertEqual(round_band(6.1), 6.0)
        self.assertEqual(calc_writing_band([6.0, 7.0]), 6.5)
        self.assertEqual(calc_writing_band([6.5]), 6.5)


class TestlarFilesTests(TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / '7').mkdir()
        (root / '7' / 'Listening 1.html').write_text('<html>L1</html>')
        (root / '7' / 'listening1.mp3').write_bytes(bytes(range(100)))
        (root / '7' / 'secret.pdf').write_bytes(b'pdf')
        (root / 'notes.html').write_text('top-level')
        self.override = override_settings(TESTLAR_DIR=root)
        self.override.enable()
        self.user = User.objects.create_user('student', password='pw')

    def tearDown(self):
        self.override.disable()
        self.tmp.cleanup()

    def _url(self, name):
        return reverse('testlar_file', args=[7, name])

    def test_requires_login(self):
        self.assertEqual(self.client.get(reverse('testlar')).status_code, 302)
        self.assertEqual(self.client.get(self._url('Listening 1.html')).status_code, 302)

    @override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
    def test_list_shows_html_tests(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('testlar'))
        self.assertContains(resp, 'Listening 1')
        self.assertNotContains(resp, 'secret')

    def test_serves_test_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(self._url('Listening 1.html'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b''.join(resp.streaming_content), b'<html>L1</html>')

    def test_blocks_raw_files_and_traversal(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self._url('secret.pdf')).status_code, 404)
        self.assertEqual(self.client.get(self._url('..')).status_code, 404)
        self.assertEqual(self.client.get(self._url('missing.html')).status_code, 404)

    def test_audio_range_request(self):
        self.client.force_login(self.user)
        resp = self.client.get(self._url('listening1.mp3'), HTTP_RANGE='bytes=10-19')
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp['Content-Range'], 'bytes 10-19/100')
        self.assertEqual(b''.join(resp.streaming_content), bytes(range(10, 20)))
        resp = self.client.get(self._url('listening1.mp3'), HTTP_RANGE='bytes=200-')
        self.assertEqual(resp.status_code, 416)


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class SeedTestlar7Tests(TestCase):
    """TESTLAR/7 dan yasalgan Full Mock Test 6/7 seed fayllari to'g'ri yuklanishi."""

    def setUp(self):
        import tempfile
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media.cleanup()

    def test_seed_and_open(self):
        from django.core.management import call_command
        for n in (6, 7):
            call_command('seed_cambridge', file=f'data/cambridge/ielts_full_mock_test_{n}.json', stdout=io.StringIO())
            exam = Exam.objects.get(title=f'IELTS Full Mock Test {n}')
            listening, reading, writing = exam.sections.order_by('order')
            self.assertEqual(listening.questions.count(), 40)
            self.assertEqual(reading.questions.count(), 40)
            self.assertEqual(writing.questions.count(), 2)
            self.assertTrue(listening.audio_file.name.startswith('exams/audio/listening'))
            self.assertTrue(writing.image)

        # qayta yuklash audio/rasmni ko'paytirmaydi
        call_command('seed_cambridge', file='data/cambridge/ielts_full_mock_test_7.json', stdout=io.StringIO())
        exam = Exam.objects.get(title='IELTS Full Mock Test 7')
        self.assertEqual(exam.sections.get(order=1).audio_file.name, 'exams/audio/listening2.mp3')

        user = User.objects.create_user('student', password='pw')
        self.client.force_login(user)
        resp = self.client.get(reverse('exams:take_exam', args=[exam.pk]))
        self.assertContains(resp, 'Rethinking the Past')
        # audio bor Listening'da transkript (javoblar) sahifaga chiqmaydi
        self.assertNotContains(resp, 'The idea is hugely popular with local chefs')

    def test_seed_testlar8(self):
        from django.core.management import call_command
        for n in (8, 9):
            call_command('seed_cambridge', file=f'data/cambridge/ielts_full_mock_test_{n}.json', stdout=io.StringIO())
            exam = Exam.objects.get(title=f'IELTS Full Mock Test {n}')
            listening, reading, writing = exam.sections.order_by('order')
            self.assertEqual(listening.questions.count(), 40)
            self.assertEqual(reading.questions.count(), 40)
            self.assertEqual(writing.questions.count(), 2)
            self.assertTrue(listening.audio_file)
            self.assertTrue(writing.image)
        exam = Exam.objects.get(title='IELTS Full Mock Test 8')
        self.assertIn('16', exam.sections.get(order=1).extra_data['question_images'])


class QuestionHeadingTests(TestCase):
    """Guruh nomi va ko'rsatmasi ("[Title] Instructions\\n…") 1-savol matniga
    qo'shilib ketmasdan, alohida sarlavha bo'lib chiqadi."""

    def test_split(self):
        from .views import _split_question_heading
        self.assertEqual(
            _split_question_heading('[The coconut palm] Complete the notes below.\nCoconuts grow on ___'),
            ('The coconut palm', 'Complete the notes below.', 'Coconuts grow on ___'))
        self.assertEqual(
            _split_question_heading('Choose the correct letter, A, B or C.\nWhy?'),
            ('', 'Choose the correct letter, A, B or C.', 'Why?'))
        self.assertEqual(_split_question_heading('Plain question'), ('', '', 'Plain question'))

    def test_take_exam_renders_heading_separately(self):
        exam = Exam.objects.create(title='Heading test', duration_minutes=60)
        section = Section.objects.create(exam=exam, title='Reading', section_type='reading', order=1)
        Question.objects.create(section=section, order=1, question_type='gap_fill', correct_answer='x',
                                text='[Customer Satisfaction Survey] Complete the form below.\nName: ___')
        Question.objects.create(section=section, order=2, question_type='gap_fill', correct_answer='y',
                                text='Occupation: ___')
        user = User.objects.create_user('reader', password='pw')
        self.client.force_login(user)
        resp = self.client.get(reverse('exams:take_exam', args=[exam.pk]))
        self.assertContains(resp, '<div class="q-heading-title">Customer Satisfaction Survey</div>', html=True)
        self.assertContains(resp, '<div class="q-heading-instr">Complete the form below.</div>', html=True)
        self.assertNotContains(resp, '[Customer Satisfaction Survey]')


class ChooseTwoGradingTests(TestCase):
    """"Choose TWO letters" juftligida bir xil to'g'ri harf ikki marta ball bermaydi."""

    def setUp(self):
        self.user = User.objects.create_user('student', password='pw')
        self.exam = Exam.objects.create(title='Pair test', price=0)
        section = Section.objects.create(exam=self.exam, title='Reading', section_type='reading', order=1)
        options = [{'key': k, 'text': k} for k in 'ABCDE']
        self.q1 = Question.objects.create(section=section, text='first answer', question_type='mcq',
                                          options=options, correct_answer='C/E', order=1)
        self.q2 = Question.objects.create(section=section, text='second answer', question_type='mcq',
                                          options=options, correct_answer='C/E', order=2)

    def _correct_count(self, a1, a2):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse('exams:submit_exam', args=[self.exam.pk]),
            data=json.dumps({'answers': {str(self.q1.id): a1, str(self.q2.id): a2}}),
            content_type='application/json',
        )
        result = UserResult.objects.get(pk=resp.json()['result_id'])
        return result.answers.filter(is_correct=True).count()

    def test_both_letters_score_two(self):
        self.assertEqual(self._correct_count('E', 'C'), 2)

    def test_same_letter_twice_scores_once(self):
        self.assertEqual(self._correct_count('C', 'C'), 1)

    def test_one_wrong_letter(self):
        self.assertEqual(self._correct_count('A', 'e'), 1)


class ExamAttemptTests(TestCase):
    """Javoblar serverga autosave qilinadi, retry ikkinchi natija yaratmaydi,
    yuborilmagan urinishdan admin natija yarata oladi."""

    def setUp(self):
        self.user = User.objects.create_user('student', password='pw')
        self.admin = User.objects.create_user('admin', password='pw', is_staff=True)
        self.exam = Exam.objects.create(title='Attempt test', price=0)
        section = Section.objects.create(exam=self.exam, title='Reading', section_type='reading', order=1)
        self.q = Question.objects.create(section=section, text='q', question_type='gap_fill',
                                         correct_answer='paris', order=1)
        self.answers = {str(self.q.id): 'paris'}
        self.client.force_login(self.user)

    def _post(self, name, **payload):
        return self.client.post(reverse(f'exams:{name}', args=[self.exam.pk]),
                                data=json.dumps(payload), content_type='application/json')

    def test_autosave_keeps_latest_answers(self):
        self._post('autosave', attempt_id='a1', answers={str(self.q.id): 'lon'}, section='reading')
        self._post('autosave', attempt_id='a1', answers=self.answers, section='reading')
        attempt = ExamAttempt.objects.get()
        self.assertEqual(attempt.answers, self.answers)
        self.assertEqual(attempt.answered_count, 1)
        self.assertFalse(attempt.is_submitted)

    def test_retry_with_same_attempt_replays_first_result(self):
        first = self._post('submit_exam', attempt_id='a1', answers=self.answers).json()
        again = self._post('submit_exam', attempt_id='a1', answers=self.answers).json()
        self.assertEqual(first, again)
        self.assertEqual(UserResult.objects.filter(user=self.user).count(), 1)
        attempt = ExamAttempt.objects.get()
        self.assertEqual(attempt.result_id, first['result_id'])
        # a late autosave doesn't overwrite what was graded
        self._post('autosave', attempt_id='a1', answers={str(self.q.id): 'x'})
        attempt.refresh_from_db()
        self.assertEqual(attempt.answers, self.answers)

    def test_new_attempt_gets_new_result(self):
        self._post('submit_exam', attempt_id='a1', answers=self.answers)
        self._post('submit_exam', attempt_id='a2', answers=self.answers)
        self.assertEqual(UserResult.objects.filter(user=self.user).count(), 2)

    def test_failed_submit_keeps_answers_on_server(self):
        from unittest import mock
        with mock.patch('exams.views.create_result', side_effect=RuntimeError('boom')), \
                self.assertLogs('exams.submit', level='ERROR'):
            resp = self._post('submit_exam', attempt_id='a1', answers=self.answers)
        self.assertEqual(resp.status_code, 500)
        attempt = ExamAttempt.objects.get()
        self.assertEqual(attempt.answers, self.answers)
        self.assertFalse(attempt.is_submitted)
        self.assertIn('boom', attempt.last_error)
        self.assertFalse(UserResult.objects.exists())

    def test_submit_still_grades_when_attempt_storage_fails(self):
        from unittest import mock
        with mock.patch('exams.views.save_attempt', side_effect=RuntimeError('no such column')), \
                self.assertLogs('exams.submit', level='ERROR'):
            resp = self._post('submit_exam', attempt_id='a1', answers=self.answers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(UserResult.objects.get().reading_score, 9.0)

    def test_admin_finalizes_unsent_attempt(self):
        self._post('autosave', attempt_id='a1', answers=self.answers, section='reading')
        attempt = ExamAttempt.objects.get()
        ExamAttempt.objects.filter(pk=attempt.pk).update(last_seen_at=attempt.last_seen_at - timedelta(minutes=10))

        self.client.force_login(self.admin)
        page = self.client.get(reverse('panel:attempts_live') + '?tab=unsent')
        self.assertContains(page, 'Natija yaratish')
        resp = self.client.post(reverse('panel:attempt_finalize', args=[attempt.pk])).json()
        self.assertTrue(resp['ok'])
        result = UserResult.objects.get(pk=resp['result_id'])
        self.assertEqual(result.user, self.user)
        self.assertEqual(result.reading_score, 9.0)
        self.assertTrue(Notification.objects.filter(user=self.user, title='Javoblaringiz qabul qilindi').exists())
        # finalizing twice is refused
        self.assertFalse(self.client.post(reverse('panel:attempt_finalize', args=[attempt.pk])).json()['ok'])

        # the student's own later resubmit gets that same result back
        self.client.force_login(self.user)
        data = self._post('submit_exam', attempt_id='a1', answers=self.answers).json()
        self.assertEqual(data['result_id'], result.pk)
        self.assertEqual(UserResult.objects.count(), 1)


class LiveMonitoringTests(TestCase):
    """Jonli imtihon: nazorat ma'lumotlari, admin xabari/qo'shimcha vaqti, hammasini yakunlash."""

    def setUp(self):
        self.student = User.objects.create_user('student', password='pw')
        self.admin = User.objects.create_user('admin', password='pw', is_staff=True)
        self.exam = Exam.objects.create(title='Live test', price=0)
        section = Section.objects.create(exam=self.exam, title='Writing', section_type='writing', order=1)
        self.w = Question.objects.create(section=section, text='Task 1', question_type='writing_task', order=1)

    def _autosave(self, **payload):
        self.client.force_login(self.student)
        return self.client.post(reverse('exams:autosave', args=[self.exam.pk]),
                                data=json.dumps({'attempt_id': 'a1', **payload}),
                                content_type='application/json').json()

    def test_meta_counters_only_grow_and_heartbeat_keeps_answers(self):
        self._autosave(answers={str(self.w.id): 'one two three'}, meta={'leave_count': 4, 'pasted_chars': 300, 'time_left': 600})
        self._autosave(meta={'leave_count': 1, 'time_left': 580})  # reloaded page, heartbeat without answers
        attempt = ExamAttempt.objects.get()
        self.assertEqual(attempt.leave_count, 4)
        self.assertEqual(attempt.pasted_chars, 300)
        self.assertEqual(attempt.time_left, 580)
        self.assertEqual(attempt.answers, {str(self.w.id): 'one two three'})

        self.client.force_login(self.admin)
        page = self.client.get(reverse('panel:attempts_live'))
        self.assertContains(page, 'T1: 3 so')
        self.assertContains(page, '4 marta')
        detail = self.client.get(reverse('panel:attempt_detail', args=[attempt.pk]))
        self.assertContains(detail, 'one two three')

    def test_staff_commands_reach_the_page(self):
        self._autosave(answers={})
        self.client.force_login(self.admin)
        url = reverse('panel:attempts_command')
        self.client.post(url, data=json.dumps({'all_active': True, 'type': 'message', 'text': '10 daqiqa qoldi'}),
                         content_type='application/json')
        self.client.post(url, data=json.dumps({'all_active': True, 'type': 'extra_time', 'minutes': 5}),
                         content_type='application/json')
        commands = self._autosave()['commands']
        self.assertEqual([c['type'] for c in commands], ['message', 'extra_time'])
        self.assertEqual(commands[0]['text'], '10 daqiqa qoldi')
        self.assertEqual(commands[1]['seconds'], 300)
        self.assertLess(commands[0]['id'], commands[1]['id'])

    def test_finish_all_stops_open_pages(self):
        self._autosave(answers={str(self.w.id): 'essay'})
        self.client.force_login(self.admin)
        resp = self.client.post(reverse('panel:attempts_finish_all'), data=json.dumps({'exam': self.exam.pk}),
                                content_type='application/json').json()
        self.assertEqual(resp['done'], 1)
        reply = self._autosave(answers={str(self.w.id): 'essay plus more'})
        self.assertTrue(reply['submitted'])
        self.assertEqual(UserResult.objects.get().pk, reply['result_id'])
        self.assertEqual(ExamAttempt.objects.get().answers, {str(self.w.id): 'essay'})

    def test_two_devices_flagged(self):
        self._autosave(answers={})
        self.client.post(reverse('exams:autosave', args=[self.exam.pk]),
                         data=json.dumps({'attempt_id': 'other-pc', 'answers': {}}), content_type='application/json')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('panel:attempts_live')), '2 qurilma', count=2)


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
                   STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class ProctorAlarmSettingTests(TestCase):
    def test_alarm_follows_site_setting(self):
        from core.models import SiteSettings
        from django.core.cache import cache
        cache.clear()
        user = User.objects.create_user('student', password='pw')
        exam = Exam.objects.create(title='Alarm test', price=0)
        section = Section.objects.create(exam=exam, title='Reading', section_type='reading', order=1)
        Question.objects.create(section=section, text='q', question_type='gap_fill', correct_answer='a', order=1)
        self.client.force_login(user)
        url = reverse('exams:take_exam', args=[exam.pk])
        self.assertContains(self.client.get(url), 'const PROCTOR_ALARM = true;')
        site = SiteSettings.get()
        site.proctor_alarm = False
        site.save()
        self.assertContains(self.client.get(url), 'const PROCTOR_ALARM = false;')
