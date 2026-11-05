"""AB Premium: bought from the balance for a fixed period, or given by staff."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import SiteSettings
from users.models import User

from .models import PremiumPurchase


def _extend(user, days):
    # Time left is kept: renewing early adds to it instead of replacing it.
    start = max(user.premium_until or timezone.now(), timezone.now())
    user.premium_until = start + timedelta(days=days)
    user.save(update_fields=['premium_until'])


def buy(user):
    """Charges the balance and extends Premium. Returns an error, or None."""
    settings_obj = SiteSettings.get()
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if locked.balance < settings_obj.premium_price:
            return "Balans yetarli emas"
        locked.balance -= settings_obj.premium_price
        locked.save(update_fields=['balance'])
        _extend(locked, settings_obj.premium_days)
        PremiumPurchase.objects.create(user=locked, amount=settings_obj.premium_price, days=settings_obj.premium_days)
    user.balance, user.premium_until = locked.balance, locked.premium_until
    return None


def grant(user, days, by):
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        _extend(locked, days)
        PremiumPurchase.objects.create(user=locked, days=days, granted_by=by)
    user.premium_until = locked.premium_until
