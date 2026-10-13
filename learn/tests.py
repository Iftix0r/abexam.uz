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
