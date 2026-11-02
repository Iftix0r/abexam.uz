from . import api
from .models import TelegramAccount


def telegram(request):
    """For the «get your results in Telegram» card: shown only while the bot
    is set up and the signed-in user hasn't linked it yet. Both values are
    callables, so the lookup only runs on pages that show the card."""
    if not (api.enabled() and request.user.is_authenticated):
        return {}
    return {
        'tg_bot_username': api.bot_username,
        'tg_needs_link': lambda: not TelegramAccount.objects.filter(user=request.user).exists(),
    }
