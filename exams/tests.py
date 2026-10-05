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
        post = {'next': ''}
        for n, scores in ((1, (6, 6, 6, 6)), (2, (7, 7, 7, 7))):
            for key, val in zip(('task_achievement', 'coherence_cohesion', 'lexical_resource', 'grammatical_accuracy'), scores):
                post[f'task{n}_{key}'] = str(val)
            post[f'task{n}_feedback'] = f'feedback {n}'
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

    def test_exam_without_writing_is_graded_immediately(self):
        Question.objects.filter(question_type='writing_task').delete()
        Section.objects.filter(section_type='writing').delete()
        data = self._submit({str(self.q_read.id): 'SECRETANSWER'})
        self.assertNotIn('pending', data)
        self.assertGreater(data['score'], 0)
        page = self.client.get(reverse('exams:result_detail', args=[data['result_id']]))
        self.assertContains(page, '1/1 to')
        self.assertNotContains(page, 'SECRETANSWER')

    def test_staff_still_sees_answers(self):
        data = self._submit({str(self.q_read.id): 'wrong', str(self.w1.id): 'a', str(self.w2.id): 'b'})
        self.client.force_login(self.admin)
        url = reverse('exams:result_detail', args=[data['result_id']])
        self.assertNotContains(self.client.get(url), 'SECRETANSWER')
        self.assertContains(self.client.get(url + '?answers=1'), 'SECRETANSWER')
        # A student can't unlock them with the same query param
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(url + '?answers=1'), 'SECRETANSWER')

    def test_band_rounding(self):
        self.assertEqual(round_band(6.25), 6.5)
        self.assertEqual(round_band(6.75), 7.0)
        self.assertEqual(round_band(6.1), 6.0)
        self.assertEqual(calc_writing_band([6.0, 7.0]), 6.5)
        self.assertEqual(calc_writing_band([6.5]), 6.5)
