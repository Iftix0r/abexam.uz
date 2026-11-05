from .services import unread_count


def chat(request):
    """Unread private chats for the menu badge. Lazy: only pages that show the
    menu run the query, once thanks to {% with %} there."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    return {'chat_unread': lambda: unread_count(user)}
