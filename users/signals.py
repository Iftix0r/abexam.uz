from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

from core.utils import get_client_ip, notify_admin_telegram


@receiver(user_logged_out)
def notify_logout(sender, request, user, **kwargs):
    if not user:
        return
    ip = get_client_ip(request)
    ua = request.META.get('HTTP_USER_AGENT', '—')[:300]
    notify_admin_telegram(
        f"🚪 <b>Chiqish</b>\n"
        f"👤 {user.get_full_name() or user.username} (@{user.username})\n"
        f"🌐 IP: {ip}\n"
        f"💻 {ua}"
    )
