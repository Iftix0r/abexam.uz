"""IP blocks set by staff in the panel. Kept in memory for half a minute, so
a blocked attacker costs no database query per request."""
import ipaddress
import time

from django.db.models import F, Q
from django.http import HttpResponseForbidden
from django.utils import timezone

from .models import BlockedIP

REFRESH_SECONDS = 30
NARROWEST_V4, NARROWEST_V6 = 16, 48  # wider blocks would shut out whole providers
_known = {'at': 0.0, 'networks': ()}

BLOCKED_PAGE = (
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>Kirish cheklangan</title>'
    '<div style="font-family:Arial,sans-serif;max-width:420px;margin:15vh auto;padding:0 16px;text-align:center">'
    '<h1 style="font-size:22px">Kirish vaqtincha cheklangan</h1>'
    '<p style="color:#555;line-height:1.6">Bu tarmoqdan saytga kirish cheklangan. Xato deb o\'ylasangiz, '
    'support@abexam.uz manziliga yozing.</p></div>')


def forget():
    """Drop this worker's copy, e.g. right after a block is added or removed."""
    _known['at'] = 0.0


def _active():
    if time.monotonic() - _known['at'] > REFRESH_SECONDS:
        rows = (BlockedIP.objects.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
                .values_list('pk', 'network'))
        _known.update(at=time.monotonic(),
                      networks=tuple((pk, ipaddress.ip_network(net, strict=False)) for pk, net in rows))
    return _known['networks']


def block_for(ip):
    """The block covering this IP, or None."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    return next((pk for pk, network in _active() if address in network), None)


def parse_network(value, own_ip):
    """(network text, error). Refuses blocks that would lock out the site's staff or its users wholesale."""
    try:
        network = ipaddress.ip_network(str(value).strip(), strict=False)
    except ValueError:
        return None, "IP manzil noto'g'ri. Masalan: 203.0.113.7 yoki 203.0.113.0/24"
    if network.is_loopback or network.is_unspecified:
        return None, "Bu server o'zining manzili, uni bloklab bo'lmaydi."
    if network.prefixlen < (NARROWEST_V4 if network.version == 4 else NARROWEST_V6):
        return None, "Diapazon juda keng: butun provayder foydalanuvchilari bloklanib qoladi."
    try:
        if ipaddress.ip_address(own_ip) in network:
            return None, "Bu sizning hozirgi IP manzilingiz. O'zingizni bloklab qo'yasiz."
    except ValueError:
        pass
    return str(network), None


def refuse_blocked(request, ip):
    """A 403 for a blocked visitor, or None. Signed-in staff always pass, so
    a block can never lock the panel's own users out."""
    pk = block_for(ip)
    if pk is None:
        return None
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated and user.is_staff:
        return None
    from .security import _batch
    hits, _ = _batch(('blocked', pk), '')
    if hits:
        BlockedIP.objects.filter(pk=pk).update(hits=F('hits') + hits, last_hit_at=timezone.now())
    return HttpResponseForbidden(BLOCKED_PAGE)
