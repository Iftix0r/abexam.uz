import json
from datetime import time, timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from exams.models import Exam, UserResult
from users.models import User

from . import api
from .models import Booking, ExamDay, TelegramAccount
from .services import notify_result_ready, send_reminders

CHAT = 555


@override_settings(TELEGRAM_BOT_TOKEN='123:abc', TELEGRAM_BOT_USERNAME='abexam_bot', TELEGRAM_ADMIN_CHAT_ID='',
                   SITE_URL='https://abexam.uz')
class BotTests(TestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch('tgbot.api.requests.post')
        self.post = patcher.start()
        self.post.return_value.status_code = 200
        self.post.return_value.json.return_value = {'ok': True, 'result': True}
        self.addCleanup(patcher.stop)
        self.day = ExamDay.objects.create(date=timezone.localdate() + timedelta(days=3), start_time=time(10),
                                          capacity=2, location='Chilonzor')
        self.update_id = 0

    def _webhook(self, payload, secret=None):
        self.update_id += 1
        return self.client.post(reverse('tgbot:webhook'), json.dumps({'update_id': self.update_id, **payload}),
                                content_type='application/json',
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret or api.webhook_secret())

    def say(self, text='', **extra):
        return self._webhook({'message': {'message_id': 1, 'chat': {'id': CHAT, 'type': 'private', 'first_name': 'Vali'},
                                          'from': {'id': CHAT}, 'text': text, **extra}})

    def press(self, data):
        return self._webhook({'callback_query': {'id': 'q', 'data': data, 'from': {'id': CHAT},
                                                 'message': {'message_id': 9, 'chat': {'id': CHAT, 'type': 'private'}}}})

    def last_text(self):
        return self.post.call_args.kwargs['json']['text']

    def sent_texts(self):
        return [c.kwargs['json'].get('text', '') for c in self.post.call_args_list]

    def test_webhook_rejects_wrong_secret(self):
        self.assertEqual(self._webhook({'message': {}}, secret='nope').status_code, 403)
        self.assertFalse(TelegramAccount.objects.exists())

    def test_full_booking_dialogue(self):
        self.assertEqual(self.say('/start').status_code, 200)
        self.assertIn('xush kelibsiz', self.last_text())
        self.say('📅 Imtihonga yozilish')
        self.assertEqual(self.post.call_args.kwargs['json']['reply_markup']['inline_keyboard'][0][0]['callback_data'],
                         f'book:{self.day.pk}')
        self.press(f'book:{self.day.pk}')
        self.assertIn('Ism va familiyangizni', self.last_text())
        self.say('Aliyev Vali')
        self.say('90 123 45 67')
        self.say("Cambridge o'quv markazi")
        self.assertIn("Ma'lumotlarni tekshiring", self.last_text())
        self.press('bok')

        b = Booking.objects.get()
        self.assertEqual((b.queue_number, b.full_name, b.phone, b.center),
                         (1, 'Aliyev Vali', '+998901234567', "Cambridge o'quv markazi"))
        self.assertTrue(any('Siz navbatga yozildingiz' in t for t in self.sent_texts()))
        acc = TelegramAccount.objects.get()
        self.assertEqual(acc.state, '')

        # Second booking for the same day is refused; saved details skip the questions.
        self.press(f'book:{self.day.pk}')
        self.assertIn('allaqachon yozilgansiz', self.last_text())

    def test_full_day_and_cancel(self):
        Booking.objects.create(day=self.day, full_name='A', phone='+998900000001', queue_number=1)
        Booking.objects.create(day=self.day, full_name='B', phone='+998900000002', queue_number=2)
        self.say('/start')
        self.press(f'book:{self.day.pk}')
        self.assertIn('joy qolmagan', self.last_text())

        Booking.objects.filter(full_name='B').update(status=Booking.STATUS_CANCELLED)
        acc = TelegramAccount.objects.get()
        acc.full_name, acc.phone = 'Vali', '+998901234567'
        acc.save()
        self.press(f'book:{self.day.pk}')
        self.press('bok')
        mine = Booking.objects.get(account=acc)
        self.assertEqual(mine.queue_number, 3)  # numbers are never reused
        self.press(f'unbook:{mine.pk}')
        mine.refresh_from_db()
        self.assertEqual(mine.status, Booking.STATUS_CANCELLED)

    def test_link_by_contact_and_results(self):
        user = User.objects.create_user('vali', password='pw', phone_number='+998901234567', first_name='Vali')
        exam = Exam.objects.create(title='Mock 1')
        UserResult.objects.create(user=user, exam=exam, score=6.5, listening_score=7.0, reading_score=6.0)

        self.say('📊 Natijalarim')
        self.assertIn('hisobingizni ulang', self.last_text())
        # Someone else's contact doesn't link.
        self.say(contact={'phone_number': '998901234567', 'user_id': 777})
        self.assertIsNone(TelegramAccount.objects.get().user)
        self.say(contact={'phone_number': '998901234567', 'user_id': CHAT})
        self.assertEqual(TelegramAccount.objects.get().user, user)

        self.say('📊 Natijalarim')
        self.assertIn('Mock 1', self.last_text())
        self.assertIn('6.5', self.last_text())

    def test_link_from_profile(self):
        user = User.objects.create_user('vali', password='pw')
        self.client.force_login(user)
        resp = self.client.get(reverse('tgbot:link'))
        self.assertTrue(resp.url.startswith('https://t.me/abexam_bot?start=link_'))
        token = resp.url.split('link_')[1]
        self.say(f'/start link_{token}')
        self.assertEqual(TelegramAccount.objects.get().user, user)
        # One-time token.
        self.assertIsNone(cache.get(f'tg_link:{token}'))

    def test_deep_link_starts_booking_for_that_day(self):
        self.say(f'/start day_{self.day.pk}')
        self.assertEqual(TelegramAccount.objects.get().state, 'ask_name')

    def test_result_ready_and_reminders(self):
        user = User.objects.create_user('vali', password='pw')
        acc = TelegramAccount.objects.create(chat_id=CHAT, user=user)
        result = UserResult.objects.create(user=user, exam=Exam.objects.create(title='Mock 2'), score=7.0)
        with mock.patch('tgbot.api.send_async') as send_async:
            notify_result_ready(result)
        self.assertIn('Natijangiz tayyor', send_async.call_args.args[1])

        tomorrow = ExamDay.objects.create(date=timezone.localdate() + timedelta(days=1), start_time=time(9))
        Booking.objects.create(day=tomorrow, account=acc, full_name='Vali', phone='+998901234567', queue_number=1)
        self.assertEqual(send_reminders(), 1)
        self.assertEqual(send_reminders(), 0)  # only once

    def test_public_schedule(self):
        resp = self.client.get(reverse('schedule'))
        self.assertContains(resp, 'Chilonzor')
        self.assertContains(resp, f'https://t.me/abexam_bot?start=day_{self.day.pk}')


@override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_ADMIN_CHAT_ID='')
class PanelExamDayTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('boss', password='pw', is_staff=True)
        self.client.force_login(self.admin)

    def test_create_day_add_booking_and_export(self):
        date = timezone.localdate() + timedelta(days=5)
        self.client.post(reverse('panel:exam_days'), {'date': date.isoformat(), 'start_time': '10:00', 'capacity': '20',
                                                      'title': 'IELTS Mock', 'location': 'Yunusobod'})
        day = ExamDay.objects.get()
        self.assertContains(self.client.get(reverse('panel:exam_days')), 'Yunusobod')
        self.client.post(reverse('panel:exam_day_detail', args=[day.pk]),
                         {'form': 'booking', 'full_name': 'Karimov Ali', 'phone': '901112233', 'center': 'Inter'})
        b = Booking.objects.get()
        self.assertEqual((b.phone, b.queue_number), ('+998901112233', 1))
        self.client.post(reverse('panel:booking_status', args=[b.pk]), {'status': 'came'})
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_CAME)
        csv_body = self.client.get(reverse('panel:exam_day_export', args=[day.pk])).content.decode('utf-8-sig')
        self.assertIn('Karimov Ali', csv_body)
        self.assertContains(self.client.get(reverse('panel:exam_day_detail', args=[day.pk])), 'Karimov Ali')
        self.client.post(reverse('panel:exam_day_delete', args=[day.pk]))
        self.assertFalse(ExamDay.objects.exists())
