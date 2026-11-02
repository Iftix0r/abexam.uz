from . import api
from .models import TelegramAccount


def telegram(request):
    """Bot links and the signed-in user's link status for the sidebar,
    dashboard and result pages. Values are callables, so nothing is looked
    up unless a template uses them — and the account only once a request."""
    if not api.enabled():
        return {}
    context = {'tg_bot_username': api.bot_username, 'tg_bot_url': api.deep_link}
    if request.user.is_authenticated:
        found = []

        def account():
            if not found:
                found.append(TelegramAccount.objects.filter(user=request.user).first())
            return found[0]

        context.update(tg_account=account, tg_needs_link=lambda: account() is None)
    return context
