"""The staff notifications page and the topbar bell."""
from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import StaffAlert

from .views import panel_required

PAGE_SIZE = 30
BELL_SIZE = 8
TODAY_KINDS = ('signup', 'login', 'payment', 'support')


def _with_read_flag(alerts, staff):
    read = StaffAlert.read_by.through.objects.filter(staffalert=OuterRef('pk'), user=staff)
    return alerts.annotate(seen=Exists(read))


def _day_label(moment, today):
    day = timezone.localtime(moment).date()
    if day == today:
        return 'Bugun'
    if day == today - timedelta(days=1):
        return 'Kecha'
    return None


@panel_required
def alerts_list(request):
    tab = request.GET.get('tab', '')
    if tab not in StaffAlert.LABELS:
        tab = ''
    q = request.GET.get('q', '').strip()
    only_unread = request.GET.get('unread') == '1'

    alerts = _with_read_flag(StaffAlert.objects.select_related('user'), request.user)
    if tab:
        alerts = alerts.filter(kind=tab)
    if q:
        alerts = alerts.filter(Q(title__icontains=q) | Q(body__icontains=q))
    if only_unread:
        alerts = alerts.filter(pk__in=StaffAlert.unread_for(request.user).values('pk'))
    page = Paginator(alerts, PAGE_SIZE).get_page(request.GET.get('page'))
    today = timezone.localdate()
    for alert in page:
        alert.day = _day_label(alert.created_at, today)
        alert.unread = not alert.seen and alert.kind not in StaffAlert.QUIET

    unread = dict(StaffAlert.unread_for(request.user).values_list('kind').annotate(n=Count('id')).order_by())
    happened = dict(StaffAlert.objects.filter(created_at__date=today).values_list('kind').annotate(n=Count('id')).order_by())
    return render(request, 'panel/alerts.html', {
        'alerts': page, 'page': page, 'tab': tab, 'q': q, 'only_unread': only_unread,
        'tabs': [{'key': key, 'label': label, 'unread': unread.get(key, 0)} for key, label in StaffAlert.LABELS.items()],
        'unread_total': sum(unread.values()),
        'today': [{'label': StaffAlert.LABELS[k], 'n': happened.get(k, 0), 'icon': StaffAlert.ICONS[k],
                   'color': StaffAlert.COLORS[k]} for k in TODAY_KINDS],
    })


@panel_required
def alert_open(request, pk):
    alert = get_object_or_404(StaffAlert, pk=pk)
    alert.read_by.add(request.user)
    return redirect(alert.url or 'panel:alerts')


@panel_required
@require_POST
def alert_read(request, pk):
    get_object_or_404(StaffAlert, pk=pk).read_by.add(request.user)
    return JsonResponse({'ok': True, 'unread': StaffAlert.unread_for(request.user).count()})


@panel_required
@require_POST
def alerts_read_all(request):
    unread = StaffAlert.unread_for(request.user)
    kind = request.POST.get('tab', '')
    if kind in StaffAlert.LABELS:
        unread = unread.filter(kind=kind)
    through = StaffAlert.read_by.through
    through.objects.bulk_create([through(staffalert_id=pk, user_id=request.user.pk) for pk in unread.values_list('pk', flat=True)],
                                ignore_conflicts=True)
    return redirect(request.POST.get('back') if str(request.POST.get('back', '')).startswith('/panel/alerts/') else 'panel:alerts')


@panel_required
def alerts_poll(request):
    """What the topbar bell shows; asked every 30 seconds while a panel tab is open."""
    unread = StaffAlert.unread_for(request.user)
    latest = _with_read_flag(StaffAlert.objects.exclude(kind__in=StaffAlert.QUIET).select_related('user'),
                             request.user)[:BELL_SIZE]
    return JsonResponse({
        'unread': unread.count(),
        'alerts': [{
            'id': a.pk, 'title': a.title, 'body': a.body, 'unread': not a.seen, 'icon': a.icon, 'color': a.color,
            'when': timezone.localtime(a.created_at).strftime('%d.%m %H:%M'),
        } for a in latest],
    })
