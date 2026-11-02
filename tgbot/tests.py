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
        # Run "fire-and-forget" sends inline so tests can see them.
        async_patcher = mock.patch('tgbot.api.send_async', side_effect=api.send)
        async_patcher.start()
        self.addCleanup(async_patcher.stop)
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

    def sent_to(self, chat_id):
        return [c.kwargs['json']['text'] for c in self.post.call_args_list
                if c.kwargs.get('json', {}).get('chat_id') == chat_id and 'text' in c.kwargs['json']]

    def make_admin(self, chat_id=900):
        staff = User.objects.create_user('boss', password='pw', is_staff=True, first_name='Boss')
        return TelegramAccount.objects.create(chat_id=chat_id, user=staff, first_name='Boss')

    def press_as(self, chat_id, data):
        return self._webhook({'callback_query': {'id': 'q', 'data': data, 'from': {'id': chat_id},
                                                 'message': {'message_id': 9, 'text': 'alert',
                                                             'chat': {'id': chat_id, 'type': 'private'}}}})

    def say_as(self, chat_id, text):
        return self._webhook({'message': {'message_id': 1, 'chat': {'id': chat_id, 'type': 'private'},
                                          'from': {'id': chat_id}, 'text': text}})

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

    def test_new_member_and_booking_alert_admins(self):
        self.make_admin()
        self.say('/start day_%d' % self.day.pk)
        alert = self.sent_to(900)[-1]
        self.assertIn("Botga yangi a'zo", alert)
        self.assertIn('jadvaldagi', alert)
        acc = TelegramAccount.objects.get(chat_id=CHAT)
        acc.full_name, acc.phone = 'Vali', '+998901234567'
        acc.state = ''
        acc.save()
        self.press(f'book:{self.day.pk}')
        self.press('bok')
        self.assertIn('Yangi navbat', self.sent_to(900)[-1])
        b = Booking.objects.get()
        self.press_as(900, f'bcame:{b.pk}')
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_CAME)
        # Only staff can press admin buttons.
        self.press(f'acancel:{b.pk}')
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_CAME)
        self.press_as(900, f'acancel:{b.pk}')
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.STATUS_CANCELLED)
        self.assertIn('Navbatingiz bekor qilindi', self.sent_to(CHAT)[-1])

    def test_support_question_reply_and_ban(self):
        admin = self.make_admin()
        self.say('/start')
        self.say('✉️ Adminga yozish')
        self.say('Imtihon narxi qancha?')
        self.assertIn('Imtihon narxi qancha?', self.sent_to(900)[-1])
        acc = TelegramAccount.objects.get(chat_id=CHAT)
        self.press_as(900, f'reply:{acc.pk}')
        self.say_as(900, '150 000 so\'m')
        self.assertIn("150 000 so'm", self.sent_to(CHAT)[-1])
        admin.refresh_from_db()
        self.assertEqual(admin.state, '')

        self.press_as(900, f'ban:{acc.pk}')
        acc.refresh_from_db()
        self.assertTrue(acc.is_banned)
        before = len(self.sent_to(CHAT))
        self.say('salom')
        self.assertEqual(len(self.sent_to(CHAT)), before)  # banned chats get no answer

    def test_admin_menu_stats_days_and_broadcast(self):
        self.make_admin()
        self.say('/start')
        self.say_as(900, '🛠 Admin panel')
        self.assertIn('Admin panel', self.sent_to(900)[-1])
        self.say('🛠 Admin panel')  # students don't get it
        self.assertNotIn('Admin panel', self.sent_to(CHAT)[-1])
        self.press_as(900, 'adm:stats')
        self.assertIn("A'zolar: 2", self.last_text())
        Booking.objects.create(day=self.day, full_name='Ali', phone='+998900000001', queue_number=1)
        self.press_as(900, f'day:{self.day.pk}')
        self.assertIn('1. Ali', self.last_text())

        self.press_as(900, 'adm:bc')
        self.say_as(900, 'Ertaga imtihon kuni ochiladi')
        self.assertIn("Ko'rib chiqing", self.sent_to(900)[-1])
        with mock.patch('tgbot.admin_bot.threading.Thread') as thread:
            self.press_as(900, 'adm:bcgo')
        target, args = thread.call_args.kwargs['target'], thread.call_args.kwargs['args']
        with mock.patch('tgbot.admin_bot.time.sleep'):
            target(*args)
        self.assertIn('Ertaga imtihon kuni ochiladi', self.sent_to(CHAT)[-1])
        self.assertIn('Xabar yuborildi: 2', self.sent_to(900)[-1])

    def test_result_pdf_and_band_calculator(self):
        user = User.objects.create_user('vali', password='pw', first_name='Ваня', last_name="G'ulomov")
        TelegramAccount.objects.create(chat_id=CHAT, user=user)
        result = UserResult.objects.create(user=user, exam=Exam.objects.create(title='Mock 3'), score=6.5,
                                           listening_score=7.0, writing_score=6.0,
                                           writing_feedback={'manual': True, 'band': 6.0, 'tasks': [
                                               {'task_num': 1, 'band': 6.0, 'feedback': 'Yaxshi, lekin…'}]})
        other = UserResult.objects.create(user=User.objects.create_user('x'), exam=result.exam, score=5)
        self.press(f'pdf:{other.pk}')  # someone else's result
        self.assertFalse(any(c.kwargs.get('files') for c in self.post.call_args_list))
        self.press(f'pdf:{result.pk}')
        doc = next(c for c in self.post.call_args_list if c.kwargs.get('files'))
        name, content, _ = doc.kwargs['files']['document']
        self.assertEqual(name, f'AbExam-natija-{result.pk}.pdf')
        self.assertTrue(content.startswith(b'%PDF'))

        self.say('32')
        self.assertIn('band <b>7.5</b>', self.last_text())

    def test_superadmin_adds_and_removes_bot_admin(self):
        owner = User.objects.create_user('owner', password='pw', is_staff=True, is_superuser=True)
        TelegramAccount.objects.create(chat_id=900, user=owner)
        self.say('/start')
        acc = TelegramAccount.objects.get(chat_id=CHAT)

        self.press_as(900, 'adm:admins')
        self.press_as(900, 'adm:addadmin')
        self.say_as(900, str(CHAT))
        acc.refresh_from_db()
        self.assertTrue(acc.is_admin)
        self.assertIn('admin qilindingiz', self.sent_to(CHAT)[-1])
        # The new admin gets the admin menu but can't add more admins.
        self.say('🛠 Admin panel')
        self.assertIn('Admin panel', self.last_text())
        self.press('adm:addadmin')
        self.assertNotEqual(TelegramAccount.objects.get(chat_id=CHAT).state, 'add_admin')
        self.press_as(900, f'ban:{acc.pk}')
        acc.refresh_from_db()
        self.assertFalse(acc.is_banned)

        self.press_as(900, f'rmadmin:{acc.pk}')
        acc.refresh_from_db()
        self.assertFalse(acc.is_admin)

        # Picking a contact who hasn't opened the bot yet.
        self.press_as(900, 'adm:addadmin')
        self._webhook({'message': {'message_id': 2, 'chat': {'id': 900, 'type': 'private'}, 'from': {'id': 900},
                                   'users_shared': {'request_id': 1, 'users': [{'user_id': 4242}]}}})
        self.assertTrue(TelegramAccount.objects.get(chat_id=4242).is_admin)

    def test_staff_without_superuser_cannot_add_admins(self):
        self.make_admin()
        self.say('/start')
        self.press_as(900, 'adm:addadmin')
        self.say_as(900, str(CHAT))
        self.assertFalse(TelegramAccount.objects.get(chat_id=CHAT).is_admin)

    def test_site_alerts_reach_bot_added_admins(self):
        from core.models import SiteSettings
        from core.utils import notify_admin_telegram
        SiteSettings.objects.update_or_create(pk=1, defaults={'telegram_work_alerts': True})
        cache.clear()
        bot_admin = TelegramAccount.objects.create(chat_id=777, is_admin=True)

        self.client.post(reverse('register'), {'first_name': 'Ali', 'last_name': 'Valiyev',
                                               'phone_number': '+998 90 412 09 77', 'password': 'Very-Strong-77'})
        alert = self.sent_to(777)[-1]
        self.assertIn("Yangi a'zo", alert)
        self.assertIn('Ali Valiyev', alert)
        self.assertNotIn('IP', alert)
        button = self.post.call_args_list[-1].kwargs['json']['reply_markup']['inline_keyboard'][0][0]
        self.assertTrue(button['url'].startswith('https://abexam.uz/panel/users/'))

        # Security noise (logins, crashes) stays in the owner's admin chat only.
        with override_settings(TELEGRAM_ADMIN_CHAT_ID='111'), \
                mock.patch('core.utils.threading.Thread') as thread:
            notify_admin_telegram('✅ Kirish')
            thread.call_args.kwargs['target']()
        self.assertEqual(self.post.call_args.kwargs['json']['chat_id'], '111')

        # An admin can mute alerts from the bot's admin menu.
        self.press_as(777, 'adm:alerts')
        bot_admin.refresh_from_db()
        self.assertTrue(bot_admin.alerts_off)
        before = len(self.sent_to(777))
        from core.utils import notify_staff_work
        notify_staff_work('✍️ Writing baholash kerak')
        self.assertEqual(len(self.sent_to(777)), before)

    def test_site_offers_bot_until_linked(self):
        user = User.objects.create_user('vali', password='pw')
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('dashboard')), 'Natijangizni Telegramda oling')
        TelegramAccount.objects.create(chat_id=CHAT, user=user)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Natijangizni Telegramda oling')
        with override_settings(TELEGRAM_BOT_TOKEN=''):
            TelegramAccount.objects.all().delete()
            self.assertNotContains(self.client.get(reverse('dashboard')), 'Natijangizni Telegramda oling')

    def test_pending_result_page_always_shows_telegram_status(self):
        user = User.objects.create_user('vali', password='pw')
        result = UserResult.objects.create(user=user, exam=Exam.objects.create(title='Mock 6'),
                                           status=UserResult.STATUS_PENDING)
        url = reverse('exams:result_detail', args=[result.pk])
        self.client.force_login(user)
        self.assertContains(self.client.get(url), 'Natijangizni Telegramda oling')
        TelegramAccount.objects.create(chat_id=CHAT, user=user)
        page = self.client.get(url)
        self.assertNotContains(page, 'Natijangizni Telegramda oling')
        self.assertContains(page, 'Telegram ulangan')
        # Staff see the full pending result; on their own it still shows.
        user.is_staff = True
        user.save()
        self.assertContains(self.client.get(url), 'Telegram ulangan')

    def test_linking_after_exam_sends_result_right_away(self):
        user = User.objects.create_user('vali', password='pw')
        exam = Exam.objects.create(title='Mock 4')
        UserResult.objects.create(user=user, exam=exam, score=7.0, listening_score=7.0)
        UserResult.objects.create(user=user, exam=Exam.objects.create(title='Mock 5'),
                                  status=UserResult.STATUS_PENDING)
        self.client.force_login(user)
        token = self.client.get(reverse('tgbot:link')).url.split('link_')[1]
        self.say(f'/start link_{token}')
        texts = self.sent_to(CHAT)
        self.assertTrue(any('Hisob ulandi' in t for t in texts))
        self.assertTrue(any('Natijangiz tayyor' in t and 'Mock 4' in t for t in texts))
        self.assertIn('Mock 5', texts[-1])
        self.assertIn('tekshirilmoqda', texts[-1])

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
