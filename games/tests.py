import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from learn.models import DailyXP, LearnerProfile
from users.models import User

from . import services
from .models import GameScore


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class GameTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('ali', password='pw', first_name='Ali')
        self.client.force_login(self.user)

    def _start(self, game='quiz', level='A1'):
        return self.client.post(reverse('games:start', args=[game]), {'level': level}).json()

    def _finish(self, token, correct, mistakes=0):
        return self.client.post(reverse('games:finish'), json.dumps({'token': token, 'correct': correct, 'mistakes': mistakes}),
                                content_type='application/json')

    def _age(self, token, seconds=120):
        key = f'game_round:{token}'
        state = cache.get(key)
        state['started'] = timezone.now() - timedelta(seconds=seconds)
        cache.set(key, state, 900)

    def test_needs_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('games:hub')).status_code, 302)

    def test_hub_and_game_pages_open(self):
        self.assertContains(self.client.get(reverse('games:hub')), 'AB Game')
        for slug in services.GAMES:
            self.assertEqual(self.client.get(reverse('games:play', args=[slug])).status_code, 200)
        self.assertEqual(self.client.get(reverse('games:play', args=['nope'])).status_code, 404)

    def test_every_level_has_words_for_every_game(self):
        for level in services.LEVELS:
            for game, info in services.GAMES.items():
                items = services.build_items(game, level)
                self.assertGreaterEqual(len(items), min(info['size'], 8), (game, level))

    def test_quiz_options_hold_the_answer_once(self):
        for item in services.build_items('quiz', 'A2'):
            self.assertEqual(item['options'].count(item['a']), 1)
            self.assertEqual(len(set(item['options'])), len(item['options']))

    def test_scramble_letters_are_the_word(self):
        for item in services.build_items('scramble', 'B1'):
            self.assertEqual(sorted(item['letters']), sorted(item['en'].lower()))

    def test_score_xp_and_course_link(self):
        token = self._start()['token']
        self._age(token)
        data = self._finish(token, 10, 2).json()
        self.assertEqual(data['score'], 94)
        self.assertEqual(data['xp'], 5)
        self.assertTrue(data['new_best'])
        self.assertEqual(LearnerProfile.objects.get(user=self.user).xp, 5)
        self.assertEqual(DailyXP.objects.get(user=self.user).xp, 5)

    def test_score_never_goes_below_zero(self):
        token = self._start()['token']
        self._age(token)
        self.assertEqual(self._finish(token, 0, 20).json()['score'], 0)

    def test_round_counts_once(self):
        token = self._start()['token']
        self._age(token)
        self.assertEqual(self._finish(token, 5).status_code, 200)
        self.assertEqual(self._finish(token, 5).status_code, 400)
        self.assertEqual(GameScore.objects.count(), 1)

    def test_impossibly_fast_result_is_refused(self):
        self.assertEqual(self._finish(self._start()['token'], 30).status_code, 400)
        self.assertFalse(GameScore.objects.exists())

    def test_cannot_claim_more_words_than_served(self):
        started = self._start('spell')
        self._age(started['token'])
        self.assertEqual(self._finish(started['token'], 999).json()['correct'], len(started['items']))

    def test_another_students_round_is_refused(self):
        token = self._start()['token']
        self._age(token)
        self.client.force_login(User.objects.create_user('vali', password='pw'))
        self.assertEqual(self._finish(token, 5).status_code, 400)

    def test_daily_xp_limit(self):
        with mock.patch.object(services, 'DAILY_XP_LIMIT', 7):
            first, second = self._start()['token'], self._start()['token']
            self._age(first)
            self._age(second)
            self.assertEqual(self._finish(first, 10).json()['xp'], 5)
            result = self._finish(second, 10).json()
        self.assertEqual(result['xp'], 2)
        self.assertTrue(result['xp_limit_reached'])

    def test_finish_needs_post_and_valid_numbers(self):
        self.assertEqual(self.client.get(reverse('games:finish')).status_code, 405)
        response = self.client.post(reverse('games:finish'), json.dumps({'token': 'x', 'correct': 'bad'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_weekly_board_hides_staff_and_phones(self):
        boss = User.objects.create_user('boss', password='pw', is_staff=True)
        phone = User.objects.create_user('998901234567', password='pw', phone_number='+998901234567')
        for user, score in ((boss, 900), (phone, 50), (self.user, 80)):
            GameScore.objects.create(user=user, game='quiz', level='A1', score=score, correct=1)
        board = services.weekly_board(self.user)
        self.assertEqual([r['name'] for r in board['rows']], ['Ali', 'Talaba'])
        self.assertEqual(board['me']['rank'], 1)

    def test_bad_level_falls_back(self):
        started = self._start(level='ZZ')
        self.assertTrue(started['items'])
