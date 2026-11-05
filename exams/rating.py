"""IELTS rating of students: their best graded mock test band.

Only full mock tests count, so a single Reading practice cannot top the list,
and staff accounts stay out. Equal bands are split by the average band, then
by the number of tests taken.
"""
from django.db.models import Avg, Count, Max
from django.utils import timezone

from users.models import User

from .models import UserResult

MONTH, ALL_TIME = 'month', 'all'


def _month_start():
    return timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def exam_rating(user, period=MONTH, limit=50):
    results = UserResult.objects.graded().filter(
        exam__exam_type='mock', score__gt=0, user__is_staff=False, user__is_active=True)
    if period != ALL_TIME:
        results = results.filter(completed_at__gte=_month_start())
    # .order_by() first: the model's default order would split the groups.
    ranked = list(results.order_by().values('user')
                  .annotate(best=Max('score'), avg=Avg('score'), tests=Count('id'))
                  .order_by('-best', '-avg', '-tests', 'user'))
    users = User.objects.in_bulk([r['user'] for r in ranked[:limit]])

    # Short name and initials only: this list is visible to every student.
    rows = [{'rank': rank, 'name': users[r['user']].short_name, 'initials': users[r['user']].initials,
             'avatar_color': users[r['user']].avatar_color, 'best': r['best'], 'tests': r['tests'],
             'pct': round(r['best'] / 9 * 100), 'me': r['user'] == user.pk}
            for rank, r in enumerate(ranked[:limit], 1)]
    me = next(({'rank': rank, 'best': r['best'], 'tests': r['tests'],
                # Bands to reach the student just above; 0 when level on band.
                'gap': ranked[rank - 2]['best'] - r['best'] if rank > 1 else None}
               for rank, r in enumerate(ranked, 1) if r['user'] == user.pk), None)
    return {'rows': rows, 'me': me, 'total': len(ranked), 'period': period,
            'top_band': ranked[0]['best'] if ranked else None,
            'average': sum(r['best'] for r in ranked) / len(ranked) if ranked else None}
