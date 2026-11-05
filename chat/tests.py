from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from users.models import User

from . import services
from .models import ChatMessage, ChatMute, ChatReport, ChatRoom


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ChatTests(TestCase):
    def setUp(self):
        cache.clear()
        self.room = ChatRoom.objects.get(slug='umumiy')
        self.ali = User.objects.create_user('998901112233', password='pw', first_name='Ali', last_name='Valiyev',
                                            phone_number='+998901112233')
        self.vali = User.objects.create_user('vali', password='pw', first_name='Vali')
        self.boss = User.objects.create_user('boss', password='pw', is_staff=True, first_name='Boss')
        self.client.force_login(self.ali)

    def _send(self, text='Salom'):
        cache.clear()
        return self.client.post(reverse('chat:send', args=[self.room.slug]), {'text': text})

    def _message(self, user=None, text='Salom'):
        return ChatMessage.objects.create(room=self.room, user=user or self.vali, text=text)

    def test_needs_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('chat:home')).status_code, 302)
        self.assertEqual(self.client.get(reverse('chat:messages', args=['umumiy'])).status_code, 302)

    def test_default_rooms_exist_and_page_opens(self):
        self.assertEqual(ChatRoom.objects.count(), 5)
        self.assertContains(self.client.get(reverse('chat:home')), 'Umumiy suhbat')

    def test_send_and_read(self):
        self.assertEqual(self._send('Salom, hammaga').status_code, 200)
        data = self.client.get(reverse('chat:messages', args=['umumiy'])).json()
        self.assertEqual(data['messages'][0]['text'], 'Salom, hammaga')
        self.assertTrue(data['messages'][0]['mine'])

    def test_only_short_name_reaches_other_students(self):
        self._message(self.ali)
        self.client.force_login(self.vali)
        row = self.client.get(reverse('chat:messages', args=['umumiy'])).json()['messages'][0]
        self.assertEqual(row['name'], 'Ali V.')
        self.assertNotIn('998901112233', str(row))
        self.assertFalse(row['can_delete'])

    def test_after_returns_only_new_messages(self):
        first = self._message()
        second = self._message(text='Ikkinchi')
        url = reverse('chat:messages', args=['umumiy'])
        data = self.client.get(url, {'after': first.pk}).json()
        self.assertEqual([m['id'] for m in data['messages']], [second.pk])

    def test_contact_details_are_refused(self):
        for text in ('Menga yozing +998 90 123 45 67', 'tel 901234567', 'kiring https://evil.example',
                     'site.uz da bor', 'telegramda @alijon_01', 't.me/kanal'):
            self.assertEqual(self._send(text).status_code, 400, text)
        self.assertFalse(ChatMessage.objects.exists())

    def test_normal_study_talk_passes(self):
        for text in ('Band 7.5 oldim', 'Task 2 uchun 250 ta soz kerak', 'Cambridge 17 Test 3 qiyinmi?'):
            self.assertEqual(self._send(text).status_code, 200, text)

    def test_staff_may_post_links(self):
        self.client.force_login(self.boss)
        self.assertEqual(self._send('Yangilik: https://abexam.uz').status_code, 200)

    def test_empty_and_too_long(self):
        self.assertEqual(self._send('   ').status_code, 400)
        self.assertEqual(self._send('a' * 1001).status_code, 400)

    def test_rate_limit(self):
        url = reverse('chat:send', args=['umumiy'])
        self.assertEqual(self.client.post(url, {'text': 'bir'}).status_code, 200)
        self.assertEqual(self.client.post(url, {'text': 'ikki'}).status_code, 429)

    def test_muted_student_reads_but_cannot_write(self):
        services.mute(self.ali, 1, self.boss)
        self.assertEqual(self._send().status_code, 403)
        self.assertEqual(self.client.get(reverse('chat:messages', args=['umumiy'])).status_code, 200)
        ChatMute.objects.update(until=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self._send().status_code, 200)

    def test_delete_own_only(self):
        mine, theirs = self._message(self.ali), self._message()
        self.assertEqual(self.client.post(reverse('chat:delete', args=[theirs.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('chat:delete', args=[mine.pk])).status_code, 200)
        data = self.client.get(reverse('chat:messages', args=['umumiy'])).json()
        self.assertEqual([m['id'] for m in data['messages']], [theirs.pk])
        self.assertEqual(data['removed'], [mine.pk])

    def test_get_cannot_change_anything(self):
        message = self._message(self.ali)
        self.assertEqual(self.client.get(reverse('chat:delete', args=[message.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('chat:report', args=[message.pk])).status_code, 405)

    def test_report_alerts_staff_once_and_counts_once(self):
        message = self._message()
        with mock.patch('chat.services.notify_staff_work') as alert:
            self.client.post(reverse('chat:report', args=[message.pk]))
            self.client.post(reverse('chat:report', args=[message.pk]))
        self.assertEqual(ChatReport.objects.count(), 1)
        alert.assert_called_once()

    def test_own_message_cannot_be_reported(self):
        self.assertEqual(self.client.post(reverse('chat:report', args=[self._message(self.ali).pk])).status_code, 400)

    def test_three_reports_hide_a_message(self):
        message = self._message()
        for name in 'abc':
            services.report(message, User.objects.create_user(name, password='pw'))
        message.refresh_from_db()
        self.assertIsNotNone(message.deleted_at)
        self.assertIsNone(message.deleted_by)

    def test_only_reported_messages_wait_for_review(self):
        quiet, reported = self._message(text='oddiy'), self._message(text='yomon')
        services.report(reported, self.ali)
        self.assertEqual(list(services.open_report_messages()), [reported])
        services.resolve_reports(reported)
        self.assertFalse(services.open_report_messages().exists())
        self.assertIsNone(quiet.deleted_at)

    def test_report_count_on_the_moderation_page(self):
        message = self._message()
        services.report(message, self.ali)
        services.report(message, self.boss)
        self.client.force_login(self.boss)
        rows = list(self.client.get(reverse('panel:chat_moderation')).context['reported'])
        self.assertEqual([m.open_reports for m in rows], [2])

    def test_moderation_is_staff_only(self):
        self.assertEqual(self.client.get(reverse('panel:chat_moderation')).status_code, 302)

    def test_dismiss_restores_an_auto_hidden_message(self):
        message = self._message()
        for name in 'abc':
            services.report(message, User.objects.create_user(name, password='pw'))
        self.client.force_login(self.boss)
        self.assertContains(self.client.get(reverse('panel:chat_moderation')), 'Yashirilgan')
        self.client.post(reverse('panel:chat_moderation'), {'action': 'dismiss', 'message': message.pk})
        message.refresh_from_db()
        self.assertIsNone(message.deleted_at)
        self.assertFalse(message.reports.filter(resolved_at__isnull=True).exists())

    def test_mute_from_moderation_then_unmute(self):
        message = self._message()
        services.report(message, self.ali)
        self.client.force_login(self.boss)
        self.client.post(reverse('panel:chat_moderation'), {'action': 'mute_week', 'message': message.pk})
        message.refresh_from_db()
        self.assertEqual(message.deleted_by, self.boss)
        self.assertTrue(ChatMute.objects.get(user=self.vali).active)
        self.client.post(reverse('panel:chat_moderation'), {'action': 'unmute', 'user': self.vali.pk})
        self.assertFalse(ChatMute.objects.exists())
