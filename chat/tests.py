from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from users.models import User

from . import services
from .models import (ChatBlock, ChatMessage, ChatMute, ChatPresence, ChatReaction, ChatReport, ChatRoom, ChatThread,
                     StaffMessage, SupportThread)


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

    def test_only_public_name_reaches_other_students(self):
        self._message(self.ali)
        self.client.force_login(self.vali)
        row = self.client.get(reverse('chat:messages', args=['umumiy'])).json()['messages'][0]
        self.assertEqual(row['name'], 'Ali Valiyev')
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


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class SocialTests(TestCase):
    def setUp(self):
        cache.clear()
        self.room = ChatRoom.objects.get(slug='umumiy')
        self.ali = User.objects.create_user('ali', password='pw', first_name='Ali')
        self.vali = User.objects.create_user('vali', password='pw', first_name='Vali')
        self.gani = User.objects.create_user('gani', password='pw', first_name='Gani')
        self.boss = User.objects.create_user('boss', password='pw', is_staff=True, first_name='Boss')
        self.client.force_login(self.ali)

    def _start(self, other=None):
        response = self.client.post(reverse('chat:start_chat', args=[(other or self.vali).pk]))
        self.assertEqual(response.status_code, 200)
        return ChatThread.objects.latest('pk')

    def _say(self, thread, text='Salom'):
        cache.delete(f'chat_gap:{thread.user_a_id}')
        cache.delete(f'chat_gap:{thread.user_b_id}')
        return self.client.post(reverse('chat:thread_send', args=[thread.pk]), {'text': text})

    def test_room_shows_online_and_member_counts(self):
        ChatPresence.objects.create(room=self.room, user=self.vali, last_seen=timezone.now())
        ChatPresence.objects.create(room=self.room, user=self.gani, last_seen=timezone.now() - timedelta(hours=2))
        User.objects.create_user('blocked', password='pw', is_active=False)
        counts = self.client.get(reverse('chat:messages', args=['umumiy'])).json()['counts']
        # Members are all active accounts, whether or not they opened the chat.
        self.assertEqual(counts, {'members': '4', 'online': '2'})

    def test_compact_numbers(self):
        cases = {0: '0', 999: '999', 1000: '1k', 1250: '1,2k', 2500: '2,5k', 3000: '3k', 100_000: '100k',
                 999_999: '999,9k', 1_000_000: '1 mln', 1_500_000: '1,5 mln', 12_000_000: '12 mln'}
        for number, text in cases.items():
            self.assertEqual(services.compact_number(number), text)

    def test_presence_is_not_written_on_every_poll(self):
        url = reverse('chat:messages', args=['umumiy'])
        self.client.get(url)
        first = ChatPresence.objects.get(user=self.ali).last_seen
        self.client.get(url)
        self.assertEqual(ChatPresence.objects.get(user=self.ali).last_seen, first)

    def test_request_allows_one_message_until_accepted(self):
        thread = self._start()
        self.assertEqual(thread.status, ChatThread.REQUEST)
        self.assertEqual(self._say(thread).status_code, 200)
        self.assertEqual(self._say(thread, 'yana').status_code, 403)
        self.client.force_login(self.vali)
        self.assertEqual(self._say(thread, 'javob').status_code, 403)
        self.client.post(reverse('chat:thread_answer', args=[thread.pk]), {'answer': 'accept'})
        self.assertEqual(self._say(thread, 'javob').status_code, 200)
        self.client.force_login(self.ali)
        self.assertEqual(self._say(thread, 'rahmat').status_code, 200)

    def test_sender_cannot_accept_own_request(self):
        thread = self._start()
        self.assertEqual(self.client.post(reverse('chat:thread_answer', args=[thread.pk]),
                                          {'answer': 'accept'}).status_code, 400)

    def test_declined_thread_vanishes_for_the_decliner_only(self):
        thread = self._start()
        self._say(thread)
        self.client.force_login(self.vali)
        self.client.post(reverse('chat:thread_answer', args=[thread.pk]), {'answer': 'decline'})
        self.assertEqual(self.client.get(reverse('chat:thread', args=[thread.pk])).status_code, 404)
        self.client.force_login(self.ali)
        self.assertEqual(self.client.get(reverse('chat:thread', args=[thread.pk])).status_code, 200)
        self.assertEqual(self._say(thread, 'yana').status_code, 403)

    def test_thread_is_closed_to_outsiders(self):
        thread = self._start()
        self._say(thread)
        message = ChatMessage.objects.get(thread=thread)
        self.client.force_login(self.gani)
        self.assertEqual(self.client.get(reverse('chat:thread', args=[thread.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('chat:thread_messages', args=[thread.pk])).status_code, 404)
        self.assertEqual(self._say(thread, 'men').status_code, 404)
        for name in ('chat:report', 'chat:delete', 'chat:react'):
            self.assertEqual(self.client.post(reverse(name, args=[message.pk]), {'kind': 'like'}).status_code, 404)

    def test_staff_cannot_browse_private_chats(self):
        thread = self._start()
        self._say(thread, 'maxfiy matn')
        self.client.force_login(self.boss)
        self.assertEqual(self.client.get(reverse('chat:thread', args=[thread.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('panel:chat_moderation')), 'maxfiy matn')

    def test_reported_private_message_reaches_moderators(self):
        thread = self._start()
        self._say(thread, 'yomon gap')
        self.client.force_login(self.vali)
        self.client.post(reverse('chat:report', args=[ChatMessage.objects.get(thread=thread).pk]))
        self.client.force_login(self.boss)
        page = self.client.get(reverse('panel:chat_moderation'))
        self.assertContains(page, 'yomon gap')
        self.assertContains(page, 'Lichka')

    def test_contact_rules_apply_in_private_too(self):
        thread = self._start()
        self.assertEqual(self._say(thread, 'raqamim 901234567').status_code, 400)

    def test_block_stops_both_directions(self):
        thread = self._start()
        self._say(thread)
        self.client.force_login(self.vali)
        self.client.post(reverse('chat:thread_answer', args=[thread.pk]), {'answer': 'accept'})
        self.assertTrue(self.client.post(reverse('chat:toggle_block', args=[self.ali.pk])).json()['blocked'])
        self.assertEqual(self._say(thread).status_code, 403)
        self.client.force_login(self.ali)
        self.assertEqual(self._say(thread).status_code, 403)
        self.assertEqual(self.client.post(reverse('chat:start_chat', args=[self.vali.pk])).status_code, 400)

    def test_staff_cannot_be_blocked(self):
        self.assertEqual(self.client.post(reverse('chat:toggle_block', args=[self.boss.pk])).status_code, 400)

    def test_daily_request_limit(self):
        others = [User.objects.create_user(f'u{i}', password='pw') for i in range(11)]
        codes = [self.client.post(reverse('chat:start_chat', args=[u.pk])).status_code for u in others]
        self.assertEqual(codes, [200] * 10 + [400])

    def test_cannot_message_yourself(self):
        self.assertEqual(self.client.post(reverse('chat:start_chat', args=[self.ali.pk])).status_code, 400)

    def test_mute_covers_private_chats(self):
        thread = self._start()
        services.mute(self.ali, 1, self.boss)
        self.assertEqual(self._say(thread).status_code, 403)

    def test_unread_and_read_marks(self):
        thread = self._start()
        self._say(thread)
        self.assertEqual(services.unread_count(self.vali), 1)
        self.assertEqual(services.unread_count(self.ali), 0)
        self.client.force_login(self.vali)
        self.client.get(reverse('chat:thread_messages', args=[thread.pk]), {'seen': 1})
        self.assertEqual(services.unread_count(self.vali), 0)
        self.client.force_login(self.ali)
        data = self.client.get(reverse('chat:thread_messages', args=[thread.pk])).json()
        self.assertEqual(data['other_read'], ChatMessage.objects.get(thread=thread).pk)

    def test_dm_switch_closes_private_chats_only(self):
        from core.models import SiteSettings
        thread = self._start()
        settings_obj = SiteSettings.get()
        settings_obj.chat_dm_enabled = False
        settings_obj.save()
        cache.clear()
        self.assertEqual(self.client.get(reverse('chat:thread', args=[thread.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('chat:start_chat', args=[self.gani.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('chat:home')).status_code, 200)

    def test_reply_stays_inside_its_room(self):
        other_room = ChatRoom.objects.get(slug='speaking')
        foreign = ChatMessage.objects.create(room=other_room, user=self.vali, text='boshqa')
        local = ChatMessage.objects.create(room=self.room, user=self.vali, text='shu yerda')
        url = reverse('chat:send', args=['umumiy'])
        row = self.client.post(url, {'text': 'javob', 'reply_to': local.pk}).json()['message']
        self.assertEqual(row['reply']['text'], 'shu yerda')
        cache.clear()
        self.assertIsNone(self.client.post(url, {'text': 'javob', 'reply_to': foreign.pk}).json()['message']['reply'])

    def test_reaction_toggles_and_switches(self):
        message = ChatMessage.objects.create(room=self.room, user=self.vali, text='x')
        url = reverse('chat:react', args=[message.pk])
        self.assertEqual(self.client.post(url, {'kind': 'like'}).json()['reactions'], {'counts': {'like': 1}, 'mine': 'like'})
        self.assertEqual(self.client.post(url, {'kind': 'heart'}).json()['reactions']['mine'], 'heart')
        self.assertIsNone(self.client.post(url, {'kind': 'heart'}).json()['reactions'])
        self.assertEqual(self.client.post(url, {'kind': 'bad'}).status_code, 400)
        self.assertFalse(ChatReaction.objects.exists())

    def test_only_staff_pin(self):
        message = ChatMessage.objects.create(room=self.room, user=self.vali, text='muhim')
        url = reverse('chat:pin', args=[message.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.boss)
        self.client.post(url)
        pinned = self.client.get(reverse('chat:messages', args=['umumiy'])).json()['pinned']
        self.assertEqual(pinned['text'], 'muhim')

    def test_card_shows_no_contact_details(self):
        self.vali.phone_number = '+998901112233'
        self.vali.save()
        card = self.client.get(reverse('chat:user_card', args=[self.vali.pk])).json()
        self.assertEqual(card['name'], 'Vali')
        self.assertNotIn('998901112233', str(card))
        self.assertNotIn('vali@', str(card))



@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class SupportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ali = User.objects.create_user('ali', password='pw', first_name='Ali')
        self.vali = User.objects.create_user('vali', password='pw', first_name='Vali')
        self.boss = User.objects.create_user('boss', password='pw', is_staff=True, first_name='Bosh', last_name='Admin')
        self.client.force_login(self.ali)

    def _ask(self, text='Yordam kerak'):
        cache.delete(f'chat_gap:{self.ali.pk}')
        return self.client.post(reverse('chat:support_send'), {'text': text})

    def _reply(self, text='Javob'):
        thread = SupportThread.objects.get(user=self.ali)
        self.client.force_login(self.boss)
        self.client.post(reverse('panel:chat_send', args=[thread.pk]), {'text': text})
        self.client.force_login(self.ali)

    def test_every_user_has_ab_admin(self):
        self.assertContains(self.client.get(reverse('chat:home')), 'AB Admin')
        self.assertEqual(self.client.get(reverse('chat:support')).status_code, 200)

    def test_student_sees_the_team_not_the_person(self):
        self._ask()
        self._reply('Salom')
        rows = self.client.get(reverse('chat:support_messages')).json()['messages']
        self.assertEqual(rows[-1]['name'], 'AB Admin')
        self.assertIsNone(rows[-1]['user_id'])
        self.assertNotIn('Bosh', str(rows))

    def test_phone_is_allowed_to_ab_admin_only(self):
        self.assertEqual(self._ask('raqamim 901234567').status_code, 200)

    def test_muted_student_can_still_reach_admin(self):
        services.mute(self.ali, 1, self.boss)
        self.assertEqual(self._ask().status_code, 200)

    def test_inbox_is_staff_only(self):
        self._ask()
        thread = SupportThread.objects.get(user=self.ali)
        for url in (reverse('panel:chat_inbox'), reverse('panel:chat_threads'),
                    reverse('panel:chat_messages', args=[thread.pk])):
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.assertEqual(self.client.post(reverse('panel:chat_send', args=[thread.pk]), {'text': 'x'}).status_code, 302)

    def test_student_cannot_read_another_support_chat(self):
        self._ask('maxfiy')
        message = ChatMessage.objects.get(support__user=self.ali)
        self.client.force_login(self.vali)
        self.assertEqual(self.client.get(reverse('chat:support_messages')).json()['messages'], [])
        self.assertEqual(self.client.post(reverse('chat:delete', args=[message.pk])).status_code, 404)

    def test_support_message_cannot_be_reported(self):
        self._ask()
        self._reply()
        message = ChatMessage.objects.filter(support__user=self.ali).latest('pk')
        self.assertEqual(self.client.post(reverse('chat:report', args=[message.pk])).status_code, 400)

    def test_unread_on_both_sides(self):
        self._ask()
        self.assertEqual(services.support_unread_total(), 1)
        thread = SupportThread.objects.get(user=self.ali)
        self.client.force_login(self.boss)
        self.client.get(reverse('panel:chat_messages', args=[thread.pk]))
        self.assertEqual(services.support_unread_total(), 0)
        self.client.post(reverse('panel:chat_send', args=[thread.pk]), {'text': 'Javob'})
        self.assertEqual(services.unread_count(self.ali), 1)
        self.client.force_login(self.ali)
        self.client.get(reverse('chat:support_messages'), {'seen': 1})
        self.assertEqual(services.unread_count(self.ali), 0)

    def test_one_alert_per_waiting_chat(self):
        with mock.patch('chat.services.notify_staff_work') as alert:
            self._ask('bir')
            self._ask('ikki')
        alert.assert_called_once()

    def test_premium_students_are_served_first(self):
        self._ask()
        self.client.force_login(self.vali)
        self.client.post(reverse('chat:support_send'), {'text': 'Men Premium'})
        User.objects.filter(pk=self.ali.pk).update(premium_until=timezone.now() + timedelta(days=5))
        self.client.force_login(self.boss)
        rows = self.client.get(reverse('panel:chat_threads')).json()['threads']
        self.assertEqual(rows[0]['name'], 'Ali')
        self.assertTrue(rows[0]['premium'])

    def test_inbox_search_and_open_for_user(self):
        self._ask()
        self.client.force_login(self.boss)
        self.assertEqual(len(self.client.get(reverse('panel:chat_threads'), {'q': 'Ali'}).json()['threads']), 1)
        self.assertEqual(len(self.client.get(reverse('panel:chat_threads'), {'q': 'yoq'}).json()['threads']), 0)
        response = self.client.get(reverse('panel:chat_open', args=[self.vali.pk]))
        self.assertIn(f'?t={SupportThread.objects.get(user=self.vali).pk}', response.url)

    def test_private_chats_never_appear_in_the_inbox(self):
        thread = ChatThread.objects.create(user_a=self.ali, user_b=self.vali, requested_by=self.ali)
        ChatMessage.objects.create(thread=thread, user=self.ali, text='maxfiy')
        self.client.force_login(self.boss)
        self.assertEqual(self.client.get(reverse('panel:chat_threads')).json()['threads'], [])


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class RoomExtrasTests(TestCase):
    def setUp(self):
        cache.clear()
        self.room = ChatRoom.objects.get(slug='umumiy')
        self.ali = User.objects.create_user('ali', password='pw', first_name='Ali')
        self.client.force_login(self.ali)

    def test_members_come_online_first_without_contacts(self):
        old = User.objects.create_user('998901112233', password='pw', phone_number='+998901112233')
        new = User.objects.create_user('vali', password='pw', first_name='Vali')
        ChatPresence.objects.create(room=self.room, user=old, last_seen=timezone.now() - timedelta(days=2))
        ChatPresence.objects.create(room=self.room, user=new, last_seen=timezone.now())
        data = self.client.get(reverse('chat:members', args=['umumiy'])).json()['members']
        self.assertEqual([m['online'] for m in data], [True, True, False])  # the viewer, Vali, then the old one
        self.assertEqual(data[1]['name'], 'Vali')
        self.assertNotIn('998901112233', str(data))

    def test_everyone_is_a_member_even_without_opening_the_chat(self):
        User.objects.create_user('vali', password='pw', first_name='Vali')
        User.objects.create_user('blok', password='pw', first_name='Blok', is_active=False)
        data = self.client.get(reverse('chat:members', args=['umumiy'])).json()
        self.assertEqual(data['total'], 2)
        self.assertEqual({m['name'] for m in data['members']}, {'Ali', 'Vali'})

    def test_member_pages_and_compact_total(self):
        for i in range(70):
            User.objects.create_user(f'u{i}', password='pw', first_name=f'Talaba{i}')
        url = reverse('chat:members', args=['umumiy'])
        first = self.client.get(url).json()
        self.assertEqual((len(first['members']), first['total'], first['next']), (60, 71, 60))
        self.assertEqual(len(self.client.get(url, {'offset': 60}).json()['members']), 11)

    def test_member_search_is_by_name_not_phone(self):
        User.objects.create_user('998901112233', password='pw', first_name='Dilnoza', phone_number='+998901112233')
        url = reverse('chat:members', args=['umumiy'])
        self.assertEqual(self.client.get(url, {'q': 'dilno'}).json()['total'], 1)
        self.assertEqual(self.client.get(url, {'q': '99890'}).json()['total'], 0)

    def test_presence_race_does_not_break_the_chat(self):
        from django.db import IntegrityError
        with mock.patch('chat.services.ChatPresence.objects.update_or_create', side_effect=IntegrityError):
            self.assertEqual(self.client.get(reverse('chat:messages', args=['umumiy'])).status_code, 200)

    def test_i_am_online_in_the_first_member_list(self):
        data = self.client.get(reverse('chat:members', args=['umumiy'])).json()['members']
        self.assertEqual([(m['name'], m['online']) for m in data], [('Ali', True)])

    def test_search_finds_visible_messages_of_this_room(self):
        other = ChatRoom.objects.get(slug='speaking')
        ChatMessage.objects.create(room=self.room, user=self.ali, text='Cambridge 17 kitobi')
        ChatMessage.objects.create(room=other, user=self.ali, text='Cambridge boshqa xonada')
        ChatMessage.objects.create(room=self.room, user=self.ali, text='Cambridge ochirilgan', deleted_at=timezone.now())
        url = reverse('chat:search', args=['umumiy'])
        rows = self.client.get(url, {'q': 'cambridge'}).json()['results']
        self.assertEqual([r['text'] for r in rows], ['Cambridge 17 kitobi'])
        self.assertEqual(self.client.get(url, {'q': 'c'}).json()['results'], [])

    def test_search_never_reaches_private_chats(self):
        vali = User.objects.create_user('vali', password='pw')
        thread = ChatThread.objects.create(user_a=self.ali, user_b=vali, requested_by=self.ali)
        ChatMessage.objects.create(thread=thread, user=vali, text='maxfiy gap')
        self.assertEqual(self.client.get(reverse('chat:search', args=['umumiy']), {'q': 'maxfiy'}).json()['results'], [])

    def test_day_labels(self):
        today = ChatMessage.objects.create(room=self.room, user=self.ali, text='a')
        old = ChatMessage.objects.create(room=self.room, user=self.ali, text='b')
        yesterday = ChatMessage.objects.create(room=self.room, user=self.ali, text='c')
        ChatMessage.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=5))
        ChatMessage.objects.filter(pk=yesterday.pk).update(created_at=timezone.now() - timedelta(days=1))
        rows = {m['id']: m['day'] for m in self.client.get(reverse('chat:messages', args=['umumiy'])).json()['messages']}
        self.assertEqual(rows[today.pk], 'Bugun')
        self.assertEqual(rows[yesterday.pk], 'Kecha')
        self.assertNotIn(rows[old.pk], ('Bugun', 'Kecha'))


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class TeamChatTests(TestCase):
    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user('a', password='pw', is_staff=True, first_name='Anvar')
        self.b = User.objects.create_user('b', password='pw', is_staff=True, first_name='Bobur')
        self.c = User.objects.create_user('c', password='pw', is_staff=True, first_name='Karim')
        self.student = User.objects.create_user('s', password='pw', first_name='Talaba')
        self.client.force_login(self.a)

    def _send(self, key, text='Salom'):
        return self.client.post(reverse('panel:chat_team_send', args=[key]), {'text': text})

    def _rows(self):
        return {r['key']: r for r in self.client.get(reverse('panel:chat_team_list')).json()['rows']}

    def test_every_admin_is_listed_with_the_group(self):
        rows = self.client.get(reverse('panel:chat_team_list')).json()['rows']
        self.assertEqual(rows[0]['key'], 'group')
        self.assertEqual({r['name'] for r in rows[1:]}, {'Bobur', 'Karim'})

    def test_blocked_or_former_admins_are_not_listed(self):
        User.objects.filter(pk=self.c.pk).update(is_active=False)
        self.assertNotIn(str(self.c.pk), self._rows())
        self.assertEqual(self._send(self.c.pk).status_code, 404)

    def test_group_reaches_all_admins(self):
        self._send('group', 'Hammaga salom')
        self.client.force_login(self.b)
        self.assertEqual(self._rows()['group']['unread'], 1)
        data = self.client.get(reverse('panel:chat_team_messages', args=['group']), {'seen': 1}).json()
        self.assertEqual(data['messages'][0]['name'], 'Anvar')
        self.assertEqual(self._rows()['group']['unread'], 0)

    def test_private_chat_stays_between_two_admins(self):
        self._send(self.b.pk, 'maxfiy')
        self.client.force_login(self.c)
        self.assertEqual(self.client.get(reverse('panel:chat_team_messages', args=[self.a.pk])).json()['messages'], [])
        self.client.force_login(self.b)
        rows = self.client.get(reverse('panel:chat_team_messages', args=[self.a.pk])).json()['messages']
        self.assertEqual(rows[0]['text'], 'maxfiy')

    def test_cannot_write_to_a_student_or_yourself(self):
        self.assertEqual(self._send(self.student.pk).status_code, 404)
        self.assertEqual(self._send(self.a.pk).status_code, 404)
        self.assertEqual(self._send('junk').status_code, 404)

    def test_students_are_kept_out(self):
        self._send('group', 'ichki gap')
        self.client.force_login(self.student)
        for url in (reverse('panel:chat_team'), reverse('panel:chat_team_list'),
                    reverse('panel:chat_team_messages', args=['group'])):
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.assertEqual(self._send('group').status_code, 302)
        self.assertEqual(StaffMessage.objects.count(), 1)

    def test_team_talk_never_reaches_student_views(self):
        self._send('group', 'ichki gap')
        self.client.force_login(self.student)
        data = self.client.get(reverse('chat:search', args=['umumiy']), {'q': 'ichki'}).json()
        self.assertEqual(data['results'], [])
        self.assertNotContains(self.client.get(reverse('chat:home')), 'ichki gap')

    def test_panel_badge_counts_conversations(self):
        self._send('group')
        self._send(self.b.pk)
        cache.delete(f'chat_gap:{self.a.pk}')
        self._send(self.b.pk, 'yana')
        self.assertEqual(services.team_unread(self.b), 2)
        self.assertEqual(services.team_unread(self.a), 0)

    def test_online_marks(self):
        self.client.get(reverse('panel:chat_team_list'))
        self.client.force_login(self.b)
        self.assertTrue(self._rows()[str(self.a.pk)]['online'])
        self.assertFalse(self._rows()[str(self.c.pk)]['online'])

    def test_empty_message_is_refused(self):
        self.assertEqual(self._send('group', '   ').status_code, 400)
        self.assertEqual(self._send('group', 'a' * 2001).status_code, 400)

