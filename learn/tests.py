import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from users.models import User, Vocabulary
from . import srs
from .content import (
    answer_matches, get_course, get_lesson, get_placement, get_stories, placement_level, validate_course,
    validate_stories,
)
from .models import DailyXP, LearnerProfile, LessonProgress, Mistake
from .services import (
    apply_practice, award_xp, build_practice, complete_lesson, get_profile, leaderboard, record_mistakes,
)


class ContentTests(TestCase):
    def test_shipped_course_is_valid(self):
        self.assertEqual(validate_course(), [])
        course = get_course()
        for code, level in course['levels'].items():
            self.assertGreater(level['lesson_count'], 0, code)

    def test_lessons_are_chained_within_a_level(self):
        first = get_lesson('a1-hello')
        self.assertIsNone(first['prev_slug'])
        self.assertEqual(get_lesson(first['next_slug'])['prev_slug'], 'a1-hello')

    def test_answer_matching_is_forgiving_about_case_and_punctuation(self):
        self.assertTrue(answer_matches("  i'm FROM tashkent. ", ["I'm from Tashkent"]))
        self.assertTrue(answer_matches('I’m fine', "I'm fine"))
        self.assertFalse(answer_matches('', ['am']))
        self.assertFalse(answer_matches('is', ['am', "'m"]))


class StoryContentTests(TestCase):
    def test_stories_are_valid_and_cover_every_level(self):
        self.assertEqual(validate_stories(), [])
        self.assertEqual({s['level'] for s in get_stories().values()}, {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'})


class PracticeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('p', password='pw')
        self.lesson = get_lesson('a1-hello')
        self.gap = next(i for i, s in enumerate(self.lesson['steps']) if s['type'] == 'gap')

    def test_text_questions_and_speaking_are_not_recorded(self):
        steps = self.lesson['steps']
        speak = next(i for i, s in enumerate(steps) if s['type'] == 'speak')
        record_mistakes(self.user, self.lesson, [self.gap, speak, 999, 'x'])
        self.assertEqual(list(Mistake.objects.values_list('step_index', flat=True)), [self.gap])
        family = get_lesson('a1-family')
        comprehension = next(i for i, s in enumerate(family['steps']) if s.get('needs_text'))
        record_mistakes(self.user, family, [comprehension])
        self.assertEqual(Mistake.objects.count(), 1)

    def test_mistake_is_mastered_after_two_right_answers(self):
        record_mistakes(self.user, self.lesson, [self.gap])
        LessonProgress.objects.create(user=self.user, lesson_slug='a1-hello', best_score=50)
        steps, words = build_practice(self.user)
        mine = [s for s in steps if s['_src'] == {'slug': 'a1-hello', 'idx': self.gap, 'mistake': True}]
        self.assertEqual(len(mine), 1)
        self.assertTrue(words)
        self.assertTrue(all(not s.get('needs_text') and s['type'] != 'speak' for s in steps))
        res = {'slug': 'a1-hello', 'step': self.gap, 'ok': True}
        apply_practice(self.user, [res])
        self.assertEqual(Mistake.objects.get().right_streak, 1)
        apply_practice(self.user, [dict(res, ok=False)])
        self.assertEqual(Mistake.objects.get().right_streak, 0)
        apply_practice(self.user, [res])
        out = apply_practice(self.user, [res])
        self.assertEqual(out['mistakes_left'], 0)

    def test_leaderboard_ranks_this_week(self):
        other = User.objects.create_user('o', password='pw', first_name='Ali', last_name='Valiyev')
        award_xp(other, 30)
        award_xp(self.user, 10)
        board = leaderboard(self.user)
        self.assertEqual([r['name'] for r in board['rows']], ['Ali V.', 'p'])
        self.assertEqual(board['me'], {'rank': 2, 'xp': 10})


class PlacementTests(TestCase):
    def test_placement_file_is_well_formed(self):
        test = get_placement()
        self.assertEqual([b['level'] for b in test['blocks']], ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'])
        for block in test['blocks']:
            for q in block['questions']:
                self.assertTrue(0 <= q['answer'] < len(q['options']), q['q'])

    def test_start_level_is_first_block_not_passed(self):
        test = get_placement()
        right = {str(i): [q['answer'] for q in b['questions']] for i, b in enumerate(test['blocks'])}
        self.assertEqual(placement_level(test, {}), 'A1')
        self.assertEqual(placement_level(test, {'0': right['0']}), 'A2')
        self.assertEqual(placement_level(test, {'0': right['0'], '1': right['1'], '2': [-1] * 6}), 'B1')
        self.assertEqual(placement_level(test, {**right, '3': [-1] * 6}), 'B2')
        self.assertEqual(placement_level(test, {**right, '4': [-1] * 6}), 'C1')
        self.assertEqual(placement_level(test, right), 'C2')


class SrsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('s', password='pw')
        self.card = Vocabulary.objects.create(user=self.user, english='peak', translation="cho'qqi")

    def test_intervals_grow_and_again_resets(self):
        now = timezone.now()
        srs.schedule(self.card, srs.GOOD, now)
        self.assertEqual(self.card.interval_days, 1)
        srs.schedule(self.card, srs.GOOD, now)
        self.assertEqual(self.card.interval_days, 3)
        srs.schedule(self.card, srs.GOOD, now)
        self.assertEqual(self.card.interval_days, 7.5)
        srs.schedule(self.card, srs.AGAIN, now)
        self.assertEqual((self.card.reps, self.card.lapses, self.card.interval_days), (0, 1, 0))
        self.assertLess(self.card.due_at, now + timedelta(hours=1))
        self.assertLess(self.card.ease, 2.5)

    def test_session_has_due_then_new_cards(self):
        later = Vocabulary.objects.create(user=self.user, english='a', translation='b',
                                          due_at=timezone.now() + timedelta(days=3))
        due = Vocabulary.objects.create(user=self.user, english='c', translation='d',
                                        due_at=timezone.now() - timedelta(hours=1))
        ids = [c.id for c in srs.session_cards(self.user)]
        self.assertEqual(ids, [due.id, self.card.id])
        self.assertNotIn(later.id, ids)


class ProgressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('learner', password='pw')

    def test_first_completion_pays_more_and_adds_words_once(self):
        lesson = get_lesson('a1-hello')
        first = complete_lesson(self.user, lesson, 80)
        self.assertEqual(first['xp'], 18)
        self.assertEqual(first['words_added'], len(lesson['words']))
        again = complete_lesson(self.user, lesson, 100)
        self.assertEqual((again['xp'], again['words_added'], again['best_score']), (5, 0, 100))
        self.assertEqual(LessonProgress.objects.get(user=self.user).attempts, 2)
        self.assertEqual(LearnerProfile.objects.get(user=self.user).xp, 23)

    def test_existing_vocabulary_word_is_not_duplicated(self):
        Vocabulary.objects.create(user=self.user, english='Hello', translation='salom')
        complete_lesson(self.user, get_lesson('a1-hello'), 100)
        self.assertEqual(self.user.vocabulary.filter(english__iexact='hello').count(), 1)

    def test_streak_counts_consecutive_days_and_resets_after_a_gap(self):
        today = timezone.localdate()
        LearnerProfile.objects.create(user=self.user, streak=4, best_streak=4, last_active=today - timedelta(days=1))
        self.assertEqual(award_xp(self.user, 5).streak, 5)
        self.assertEqual(award_xp(self.user, 5).streak, 5)   # same day doesn't count twice
        self.assertEqual(DailyXP.objects.get(user=self.user, date=today).xp, 10)

        LearnerProfile.objects.filter(user=self.user).update(last_active=today - timedelta(days=3))
        profile = award_xp(self.user, 1)
        self.assertEqual((profile.streak, profile.best_streak), (1, 5))

    def test_shown_streak_is_zero_once_broken(self):
        p = LearnerProfile(user=self.user, streak=9, last_active=timezone.localdate() - timedelta(days=2))
        self.assertEqual(p.current_streak, 0)


class EndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('learner', password='pw')
        self.client.force_login(self.user)

    def _post(self, name, payload, *args):
        return self.client.post(reverse(name, args=args), data=json.dumps(payload), content_type='application/json')

    def test_locked_lesson_cannot_be_completed(self):
        resp = self._post('learn:lesson_complete', {'score': 100}, 'a1-family')
        self.assertEqual(resp.status_code, 403)
        self._post('learn:lesson_complete', {'score': 100}, 'a1-hello')
        resp = self._post('learn:lesson_complete', {'score': 250}, 'a1-family')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(LessonProgress.objects.get(lesson_slug='a1-family').best_score, 100)

    def test_review_grade_only_touches_own_cards(self):
        other = User.objects.create_user('other', password='pw')
        theirs = Vocabulary.objects.create(user=other, english='x', translation='y')
        mine = Vocabulary.objects.create(user=self.user, english='x', translation='y')
        self.assertEqual(self._post('learn:review_grade', {'id': theirs.id, 'grade': 2}).status_code, 404)
        self.assertEqual(self._post('learn:review_grade', {'id': mine.id, 'grade': 2}).status_code, 200)
        mine.refresh_from_db()
        self.assertEqual(mine.reps, 1)
        self.assertIsNotNone(mine.due_at)

    def test_lesson_completion_records_mistakes(self):
        lesson = get_lesson('a1-hello')
        gap = next(i for i, st in enumerate(lesson['steps']) if st['type'] == 'gap')
        self._post('learn:lesson_complete', {'score': 50, 'mistakes': [gap]}, 'a1-hello')
        self.assertTrue(Mistake.objects.filter(user=self.user, step_index=gap).exists())
        res = {'slug': 'a1-hello', 'step': gap, 'ok': True}
        # No practice session was served, so there is nothing to report.
        self.assertEqual(self._post('learn:practice_complete', {'results': [res]}).status_code, 400)
        self._serve_practice([['a1-hello', gap]])
        resp = self._post('learn:practice_complete', {'results': [res]})
        self.assertEqual(resp.json()['right'], 1)

    def _serve_practice(self, steps):
        session = self.client.session
        session['learn_practice'] = steps
        session.save()

    def test_practice_only_counts_served_steps_once(self):
        lesson = get_lesson('a1-hello')
        gaps = [i for i, st in enumerate(lesson['steps']) if st['type'] == 'gap']
        self._serve_practice([['a1-hello', gaps[0]]])
        forged = [{'slug': 'a1-hello', 'step': gaps[0], 'ok': True}] * 5 + \
                 [{'slug': 'a1-hello', 'step': i, 'ok': True} for i in gaps[1:]]
        d = self._post('learn:practice_complete', {'results': forged}).json()
        self.assertEqual((d['right'], d['xp']), (1, 4))
        # The session is used up: replaying the same request is rejected.
        self.assertEqual(self._post('learn:practice_complete', {'results': forged}).status_code, 400)

    def test_practice_xp_has_a_daily_cap(self):
        with mock.patch('learn.views.PRACTICE_PAID_DAILY', 1):
            self._serve_practice([['a1-hello', 0]])
            first = self._post('learn:practice_complete', {'results': []}).json()
            self._serve_practice([['a1-hello', 0]])
            second = self._post('learn:practice_complete', {'results': []}).json()
        self.assertEqual((first['xp'], second['xp']), (3, 0))

    def test_lesson_replay_pays_once_a_day(self):
        xps = [self._post('learn:lesson_complete', {'score': 100}, 'a1-hello').json()['xp'] for _ in range(3)]
        self.assertEqual(xps, [20, 5, 0])
        LessonProgress.objects.filter(lesson_slug='a1-hello').update(completed_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self._post('learn:lesson_complete', {'score': 100}, 'a1-hello').json()['xp'], 5)

    def test_regrading_a_reviewed_card_earns_nothing(self):
        card = Vocabulary.objects.create(user=self.user, english='x', translation='y')
        for _ in range(3):
            self._post('learn:review_grade', {'id': card.id, 'grade': 2})
        self.assertEqual(get_profile(self.user).xp, 1)

    def test_story_completion_pays_once(self):
        first = self._post('learn:story_complete', {'score': 75}, 'a1-malikas-cat').json()
        again = self._post('learn:story_complete', {'score': 100}, 'a1-malikas-cat').json()
        third = self._post('learn:story_complete', {'score': 100}, 'a1-malikas-cat').json()
        self.assertEqual((first['xp'], again['xp'], third['xp']), (8, 2, 0))
        self.assertEqual(LessonProgress.objects.get(lesson_slug='story:a1-malikas-cat').best_score, 100)
        # A read story doesn't count as a finished lesson (no lesson unlocks, placement still offered).
        self.assertEqual(self._post('learn:lesson_complete', {'score': 1}, 'a1-family').status_code, 403)

    def test_placement_sets_level(self):
        test = get_placement()
        answers = {'0': [q['answer'] for q in test['blocks'][0]['questions']]}
        resp = self._post('learn:placement_save', {'answers': answers})
        self.assertEqual(resp.json()['level'], 'A2')
        self.assertEqual(LearnerProfile.objects.get(user=self.user).level, 'A2')
        self.assertEqual(self._post('learn:placement_save', {'answers': []}).status_code, 400)

    @mock.patch('learn.views.ai.tutor_reply', return_value={'reply': 'Great! And you?', 'correction': None, 'tip': None})
    def test_tutor_reply_and_daily_limit(self, reply):
        resp = self._post('learn:tutor_send', {'scenario': 'cafe', 'message': 'I want coffee', 'history': []})
        self.assertEqual(resp.json()['reply'], 'Great! And you?')
        self.assertEqual(LearnerProfile.objects.get(user=self.user).xp, 2)
        with mock.patch('learn.views.TUTOR_DAILY_LIMIT', 1):
            self.assertEqual(self._post('learn:tutor_send', {'message': 'hi'}).status_code, 429)

    @mock.patch('learn.views.ai.check_writing', return_value={'score': 70, 'corrected': 'x', 'mistakes': [], 'praise_uz': '', 'next_uz': ''})
    def test_write_check_needs_a_write_step(self, check):
        lesson = get_lesson('a1-hello')
        write_idx = next(i for i, s in enumerate(lesson['steps']) if s['type'] == 'write')
        bad = self._post('learn:write_check', {'slug': 'a1-hello', 'step': 0, 'text': 'My name is Ali.'})
        self.assertEqual(bad.status_code, 400)
        ok = self._post('learn:write_check', {'slug': 'a1-hello', 'step': write_idx, 'text': 'My name is Ali.'})
        self.assertEqual(ok.json()['score'], 70)


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class PageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('learner', password='pw')
        self.client.force_login(self.user)

    def test_pages_render(self):
        hub = self.client.get(reverse('learn:hub') + '?level=B2')
        self.assertContains(hub, 'Grafiklarni tasvirlash')
        self.assertEqual(LearnerProfile.objects.get(user=self.user).level, 'B2')
        self.assertContains(self.client.get(reverse('learn:lesson', args=['b2-trends'])), 'lesson-data')
        self.assertRedirects(self.client.get(reverse('learn:lesson', args=['b2-linking'])),
                             reverse('learn:hub') + '?level=B2', fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('learn:lesson', args=['nope'])).status_code, 404)
        self.assertEqual(self.client.get(reverse('learn:review')).status_code, 200)
        self.assertContains(self.client.get(reverse('learn:tutor') + '?s=ielts1'), 'IELTS Speaking Part 1')
        self.assertContains(self.client.get(reverse('learn:placement')), 'test-data')
        grammar = self.client.get(reverse('learn:grammar'))
        self.assertContains(grammar, 'Present Perfect vs Past Simple')
        # Only lessons the learner has unlocked get a link from the reference.
        self.assertContains(grammar, reverse('learn:lesson', args=['b2-trends']))
        self.assertNotContains(grammar, reverse('learn:lesson', args=['b2-linking']))

    def test_new_pages_render(self):
        self.assertContains(self.client.get(reverse('learn:stories')), 'Malika')
        self.assertContains(self.client.get(reverse('learn:story', args=['b1-wrong-train'])), 'story-data')
        self.assertEqual(self.client.get(reverse('learn:story', args=['nope'])).status_code, 404)
        self.assertContains(self.client.get(reverse('learn:leaderboard')), 'Haftaning')
        self.assertContains(self.client.get(reverse('learn:practice')), '"mode": "practice"')

    def test_new_learner_is_offered_the_placement_test(self):
        self.assertContains(self.client.get(reverse('learn:hub')), reverse('learn:placement') + '" class="ln-btn')


class ApiTests(TestCase):
    """The mobile app's JSON API (learn/api.py)."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('learner', password='pw-Secret-123')
        resp = self._call('post', 'learn_api:login', {'username': 'learner', 'password': 'pw-Secret-123'}, token=None)
        self.assertEqual(resp.status_code, 200)
        self.token = resp.json()['token']

    def _call(self, method, name, payload=None, *args, token='own', query=''):
        headers = {}
        token = self.token if token == 'own' else token
        if token:
            headers['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        url = reverse(name, args=args) + query
        if method == 'get':
            return self.client.get(url, **headers)
        return self.client.post(url, data=json.dumps(payload or {}), content_type='application/json', **headers)

    def test_health_needs_no_token(self):
        self.assertEqual(self._call('get', 'learn_api:health', token=None).json()['app'], 'abexam-api')

    def test_requests_without_a_valid_token_are_refused(self):
        self.assertEqual(self._call('get', 'learn_api:me', token=None).status_code, 401)
        self.assertEqual(self._call('get', 'learn_api:me', token='nope').status_code, 401)
        self.assertEqual(self._call('get', 'learn_api:me').status_code, 200)
        fallback = self.client.get(reverse('learn_api:me'), HTTP_X_API_TOKEN=self.token)
        self.assertEqual(fallback.status_code, 200)

    def test_wrong_password_and_logout(self):
        bad = self._call('post', 'learn_api:login', {'username': 'learner', 'password': 'x'}, token=None)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self._call('post', 'learn_api:logout').status_code, 200)
        self.assertEqual(self._call('get', 'learn_api:me').status_code, 401)

    def test_delete_account_needs_password_and_erases_user(self):
        bad = self._call('post', 'learn_api:delete_me', {'password': 'wrong'})
        self.assertEqual(bad.status_code, 400)
        self.assertTrue(User.objects.filter(username='learner').exists())
        self.assertEqual(self._call('post', 'learn_api:delete_me', {'password': 'pw-Secret-123'}).status_code, 200)
        self.assertFalse(User.objects.filter(username='learner').exists())
        self.assertEqual(self._call('get', 'learn_api:me').status_code, 401)

    def test_register_returns_a_working_token(self):
        resp = self._call('post', 'learn_api:register', {
            'first_name': 'Ali', 'last_name': 'Valiyev', 'phone_number': '90 412 09 77', 'password': 'Very-Strong-77',
        }, token=None)
        self.assertEqual(resp.status_code, 200, resp.content)
        me = self._call('get', 'learn_api:me', token=resp.json()['token']).json()
        self.assertEqual(me['user']['first_name'], 'Ali')
        login = self._call('post', 'learn_api:login', {'username': '+998904120977', 'password': 'Very-Strong-77'}, token=None)
        self.assertEqual(login.status_code, 200, login.content)
        dup = self._call('post', 'learn_api:register', {
            'first_name': 'Vali', 'last_name': 'X', 'phone_number': '+998 90 412-09-77', 'password': 'Very-Strong-77'}, token=None)
        self.assertEqual(dup.status_code, 400)

    def test_course_lesson_and_completion(self):
        course = self._call('get', 'learn_api:course', query='?level=A1').json()
        self.assertEqual(course['current'], 'a1-hello')
        states = [l['state'] for u in course['units'] for l in u['lessons']]
        self.assertEqual(states[:2], ['current', 'locked'])
        self.assertEqual(self._call('get', 'learn_api:lesson', None, 'a1-family').status_code, 403)
        lesson = self._call('get', 'learn_api:lesson', None, 'a1-hello').json()
        self.assertTrue(lesson['steps'] and lesson['words'])
        done = self._call('post', 'learn_api:lesson_complete', {'score': 90}, 'a1-hello').json()
        self.assertEqual(done['xp'], 19)
        self.assertEqual(self._call('get', 'learn_api:lesson', None, 'a1-family').status_code, 200)
        me = self._call('get', 'learn_api:me').json()
        self.assertEqual((me['xp'], me['streak'], me['review']['new']), (19, 1, len(lesson['words'])))

    def test_practice_id_is_single_use(self):
        self._call('post', 'learn_api:lesson_complete', {'score': 50}, 'a1-hello')
        session = self._call('get', 'learn_api:practice').json()
        self.assertTrue(session['steps'])
        results = [{'slug': s['_src']['slug'], 'step': s['_src']['idx'], 'ok': True} for s in session['steps']]
        first = self._call('post', 'learn_api:practice_complete', {'id': session['id'], 'results': results})
        self.assertEqual(first.json()['right'], len(results))
        again = self._call('post', 'learn_api:practice_complete', {'id': session['id'], 'results': results})
        self.assertEqual(again.status_code, 400)

    def test_review_stories_and_placement(self):
        self._call('post', 'learn_api:lesson_complete', {'score': 100}, 'a1-hello')
        cards = self._call('get', 'learn_api:review').json()['cards']
        graded = self._call('post', 'learn_api:review_grade', {'id': cards[0]['id'], 'grade': 2})
        self.assertEqual(graded.status_code, 200)
        listing = self._call('get', 'learn_api:stories').json()['stories']
        slug = listing[0]['slug']
        self.assertTrue(self._call('get', 'learn_api:story', None, slug).json()['paragraphs'])
        self.assertEqual(self._call('post', 'learn_api:story_complete', {'score': 80}, slug).json()['xp'], 8)
        test = self._call('get', 'learn_api:placement').json()
        answers = {'0': [q['answer'] for q in test['blocks'][0]['questions']]}
        self.assertEqual(self._call('post', 'learn_api:placement', {'answers': answers}).json()['level'], 'A2')
        board = self._call('get', 'learn_api:leaderboard').json()
        self.assertEqual(board['me']['rank'], 1)
        self.assertTrue(self._call('get', 'learn_api:grammar').json()['levels'])


class DraftAndAppTests(TestCase):
    """Resume a lesson across site and app; app release download."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('learner', password='pw-Secret-123')
        self.client.force_login(self.user)
        self.lesson = get_lesson('a1-hello')
        self.sig = f"{len(self.lesson['steps'])}:{len(self.lesson['words'])}"
        self.state = {'sig': self.sig, 'queue': list(range(len(self.lesson['steps']))), 'pos': 3,
                      'firstTry': {'1': True}, 'retried': [], 'mistakes': [], 'at': 1}

    def _post(self, url, payload, **extra):
        return self.client.post(url, data=json.dumps(payload), content_type='application/json', **extra)

    def test_draft_saved_on_site_is_offered_in_app_and_cleared_on_completion(self):
        site_url = reverse('learn:lesson_draft', args=['a1-hello'])
        self.assertTrue(self._post(site_url, {'data': self.state}).json()['ok'])
        self.assertFalse(self._post(site_url, {'data': {**self.state, 'sig': '1:1'}}).json()['ok'])
        token = self._post(reverse('learn_api:login'), {'username': 'learner', 'password': 'pw-Secret-123'}).json()['token']
        auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        lesson = self.client.get(reverse('learn_api:lesson', args=['a1-hello']), **auth).json()
        self.assertEqual(lesson['draft']['pos'], 3)
        moved = {**self.state, 'pos': 5, 'at': 2}
        self.assertTrue(self._post(reverse('learn_api:lesson_draft', args=['a1-hello']), {'data': moved}, **auth).json()['ok'])
        complete_lesson(self.user, self.lesson, 80)
        self.assertIsNone(self.client.get(reverse('learn_api:lesson', args=['a1-hello']), **auth).json()['draft'])

    def test_app_version_and_download(self):
        from .models import AppRelease
        self.assertEqual(self.client.get(reverse('learn_api:app_version')).json()['build'], 0)
        AppRelease.objects.create(version='1.0.0', build=1, url='https://example.com/old.apk')
        AppRelease.objects.create(version='1.4.0', build=6, url='https://example.com/app.apk', notes='Yangi\n\nTez')
        info = self.client.get(reverse('learn_api:app_version')).json()
        self.assertEqual((info['version'], info['build'], info['notes']), ('1.4.0', 6, ['Yangi', 'Tez']))
        self.client.logout()
        resp = self.client.get(reverse('learn:app_download'))
        self.assertRedirects(resp, 'https://example.com/app.apk', fetch_redirect_response=False)
        self.assertEqual(AppRelease.objects.get(build=6).downloads, 1)
        self.assertContains(self.client.get(reverse('learn:app')), '1.4.0')


class GamificationTests(TestCase):
    """Duolingo-style quests, chest, badges and streak freezes."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('learner', password='pw')
        self.client.force_login(self.user)

    def test_freeze_is_earned_every_seven_days_and_saves_a_missed_day(self):
        today = timezone.localdate()
        LearnerProfile.objects.create(user=self.user, streak=6, best_streak=6, last_active=today - timedelta(days=1))
        self.assertEqual(award_xp(self.user, 5).streak_freezes, 1)        # day 7 → one freeze
        LearnerProfile.objects.filter(user=self.user).update(last_active=today - timedelta(days=2))
        p = LearnerProfile.objects.get(user=self.user)
        self.assertEqual(p.current_streak, 7)                             # missed yesterday, freeze covers it
        p = award_xp(self.user, 5)
        self.assertEqual((p.streak, p.streak_freezes), (8, 0))
        LearnerProfile.objects.filter(user=self.user).update(last_active=today - timedelta(days=3))
        self.assertEqual(award_xp(self.user, 5).streak, 1)               # no freeze left → reset

    def test_quests_fill_up_and_the_chest_opens_once(self):
        from .gamification import daily_quests, open_chest
        info = daily_quests(self.user)
        self.assertEqual(len(info['quests']), 3)
        self.assertIsNone(open_chest(self.user))
        DailyXP.objects.create(user=self.user, date=timezone.localdate(), xp=100, lessons=5, perfect=5, reviews=50,
                               stories=5, practice=5, tutor=10)
        self.assertTrue(daily_quests(self.user)['all_done'])
        resp = self.client.post(reverse('learn:chest'))
        self.assertEqual(resp.json()['xp'], 15)
        self.assertEqual(self.client.post(reverse('learn:chest')).status_code, 400)

    def test_lesson_completion_counts_for_quests_and_unlocks_a_badge_once(self):
        first = complete_lesson(self.user, get_lesson('a1-hello'), 100)
        self.assertIn('lessons', [b['key'] for b in first['new_badges']])
        day = DailyXP.objects.get(user=self.user)
        self.assertEqual((day.lessons, day.perfect), (1, 1))
        again = complete_lesson(self.user, get_lesson('a1-hello'), 100)
        self.assertNotIn('lessons', [b['key'] for b in again['new_badges']])

    def test_api_exposes_quests_and_achievements(self):
        token = self.client.post(reverse('learn_api:login'), data=json.dumps({'username': 'learner', 'password': 'pw'}),
                                 content_type='application/json').json()['token']
        auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        me = self.client.get(reverse('learn_api:me'), **auth).json()
        self.assertEqual(len(me['daily']['quests']), 3)
        badges = self.client.get(reverse('learn_api:achievements'), **auth).json()['badges']
        self.assertEqual({b['key'] for b in badges}, {'lessons', 'streak', 'perfect', 'words', 'stories', 'xp'})
        self.assertEqual(self.client.post(reverse('learn_api:chest'), **auth).status_code, 400)


class CheckpointTests(TestCase):
    """Unit tests / level exams with test-out, and AI 'explain my answer'."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('learner', password='pw')
        self.client.force_login(self.user)

    def _all_right(self, served):
        return [{'slug': s, 'step': i, 'ok': True} for s, i in served]

    def test_unit_test_mixes_lessons_and_passing_tests_out(self):
        from . import checkpoints
        unit = get_course()['levels']['A1']['units'][0]
        test = checkpoints.build('unit', unit['slug'])
        self.assertEqual(len(test['steps']), checkpoints.UNIT_SIZE)
        self.assertEqual({s['_src']['slug'] for s in test['steps']}, {l['slug'] for l in unit['lessons']})
        self.assertTrue(all(s['type'] in checkpoints.TEST_TYPES and not s.get('needs_text') for s in test['steps']))
        served = [[s['_src']['slug'], s['_src']['idx']] for s in test['steps']]
        half = [dict(r, ok=n < 5) for n, r in enumerate(self._all_right(served))]
        fail = checkpoints.finish(self.user, 'unit', unit['slug'], served, half)
        self.assertFalse(fail['passed'])
        self.assertTrue(Mistake.objects.filter(user=self.user).exists())   # wrong answers → practice
        ok = checkpoints.finish(self.user, 'unit', unit['slug'], served, self._all_right(served))
        self.assertEqual((ok['passed'], ok['first_pass'], ok['tested_out'], ok['xp']), (True, True, 3, checkpoints.UNIT_XP))
        next_unit_first = get_course()['levels']['A1']['units'][1]['lessons'][0]
        self.assertEqual(self.client.get(reverse('learn:lesson', args=[next_unit_first['slug']])).status_code, 200)
        again = checkpoints.finish(self.user, 'unit', unit['slug'], served, self._all_right(served))
        self.assertEqual((again['first_pass'], again['xp']), (False, 0))

    def test_later_unit_test_is_locked_until_the_previous_unit_is_done(self):
        units = get_course()['levels']['A1']['units']
        locked = reverse('learn:checkpoint', args=['unit', units[1]['slug']])
        self.assertRedirects(self.client.get(locked), reverse('learn:hub'), fetch_redirect_response=False)

    def test_site_test_flow_uses_the_served_questions_only(self):
        units = get_course()['levels']['A1']['units']
        url = reverse('learn:checkpoint', args=['unit', units[0]['slug']])
        self.assertEqual(self.client.get(url).status_code, 200)
        served = self.client.session[f"learn_test_unit_{units[0]['slug']}"]
        forged = self._all_right(served) + [{'slug': 'a1-hello', 'step': 999, 'ok': True}]
        done = self.client.post(reverse('learn:checkpoint_complete', args=['unit', units[0]['slug']]),
                                data=json.dumps({'results': forged}), content_type='application/json').json()
        self.assertEqual((done['score'], done['passed']), (100, True))
        self.assertEqual(self.client.post(reverse('learn:checkpoint_complete', args=['unit', units[0]['slug']]),
                                          data='{}', content_type='application/json').status_code, 400)

    def test_api_level_exam_and_course_states(self):
        token = self.client.post(reverse('learn_api:login'), data=json.dumps({'username': 'learner', 'password': 'pw'}),
                                 content_type='application/json').json()['token']
        auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        course = self.client.get(reverse('learn_api:course'), {'level': 'A1'}, **auth).json()
        self.assertEqual([u['test']['state'] for u in course['units']][:2], ['open', 'locked'])
        exam = self.client.get(reverse('learn_api:checkpoint'), {'kind': 'level', 'key': 'A2'}, **auth).json()
        results = [{'slug': s['_src']['slug'], 'step': s['_src']['idx'], 'ok': True} for s in exam['steps']]
        done = self.client.post(reverse('learn_api:checkpoint_complete'), data=json.dumps({'id': exam['id'], 'results': results}),
                                content_type='application/json', **auth).json()
        self.assertTrue(done['passed'])
        self.assertGreater(done['tested_out'], 9)
        course = self.client.get(reverse('learn_api:course'), {'level': 'A2'}, **auth).json()
        self.assertEqual(course['exam']['state'], 'passed')
        self.assertIsNone(course['current'])

    @mock.patch('learn.ai.explain_answer', return_value={'verdict': 'correct', 'explain_uz': "To'g'ri", 'rule_uz': '', 'example': ''})
    def test_explain_my_answer_is_cached(self, explain):
        lesson = get_lesson('a1-hello')
        gap = next(i for i, s in enumerate(lesson['steps']) if s['type'] == 'gap')
        body = json.dumps({'slug': 'a1-hello', 'step': gap, 'answer': 'something'})
        first = self.client.post(reverse('learn:explain'), data=body, content_type='application/json').json()
        self.assertEqual(first['verdict'], 'correct')
        self.client.post(reverse('learn:explain'), data=body, content_type='application/json')
        self.assertEqual(explain.call_count, 1)
        words = next(i for i, s in enumerate(lesson['steps']) if s['type'] == 'words')
        bad = self.client.post(reverse('learn:explain'), data=json.dumps({'slug': 'a1-hello', 'step': words, 'answer': 'x'}),
                               content_type='application/json')
        self.assertEqual(bad.status_code, 503)
