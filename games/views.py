from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from core.utils import parse_json_body
from learn.content import LEVELS

from . import services


def _level(request, source):
    level = source.get('level', '')
    return level if level in LEVELS else services.default_level(request.user)


def _game(slug):
    if slug not in services.GAMES:
        raise Http404
    return services.GAMES[slug]


@login_required
def hub(request):
    bests = services.my_bests(request.user)
    level = _level(request, request.GET)
    return render(request, 'games/hub.html', {
        'games': [{'slug': slug, 'best': bests.get(slug, 0), **game} for slug, game in services.GAMES.items()],
        'levels': LEVELS, 'level': level, 'board': services.weekly_board(request.user),
        'xp_today': services.xp_today(request.user), 'xp_limit': services.DAILY_XP_LIMIT,
    })


@login_required
def play(request, slug):
    return render(request, 'games/play.html', {
        'slug': slug, 'game': _game(slug), 'level': _level(request, request.GET),
    })


@login_required
@require_POST
def start(request, slug):
    game = _game(slug)
    token, items = services.start_round(request.user, slug, _level(request, request.POST))
    return JsonResponse({'token': token, 'items': items, 'seconds': game['seconds']})


@login_required
@require_POST
def finish(request):
    data, err = parse_json_body(request)
    if err:
        return err
    try:
        correct, mistakes = int(data.get('correct', 0)), int(data.get('mistakes', 0))
    except (TypeError, ValueError):
        return JsonResponse({'error': "Noto'g'ri natija"}, status=400)
    result, error = services.finish_round(request.user, str(data.get('token', '')), correct, mistakes)
    if error:
        return JsonResponse({'error': error}, status=400)
    return JsonResponse(result)
