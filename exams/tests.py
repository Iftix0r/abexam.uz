import io
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Notification
from users.models import User
from .models import Exam, Question, Section, UserResult
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
