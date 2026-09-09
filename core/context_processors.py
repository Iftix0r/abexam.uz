from .models import SiteSettings


def site(request):
    context = {'site_settings': SiteSettings.get()}
    if request.user.is_authenticated:
        from .models import Notification
        # Broadcast notifications (user=None) share one is_read flag across
        # every viewer, so counting them here would mean one person opening
        # the list marks it "read" for everyone else's badge too — only
        # per-user notifications have an unambiguous read state to badge.
        context['unread_notifications_count'] = Notification.objects.filter(
            user=request.user, is_read=False,
        ).count()
    return context
