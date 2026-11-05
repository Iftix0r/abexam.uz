from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_GET, require_POST
from datetime import timedelta

from core.audit import log_action
from panel.views import panel_required
from users.models import User

from . import services
from .models import ChatMessage, ChatMute, ChatRoom

PAGE = 50
REMOVED_WINDOW = timedelta(minutes=10)


def _room(slug):
    return get_object_or_404(ChatRoom, slug=slug, is_active=True)


def _int(value):
    return int(value) if value and value.isdigit() else None


def _payload(message, viewer):
    author = message.user
    # Short name and initials only, as on the rating: no photos, phones or usernames.
    return {
        'id': message.pk, 'name': author.short_name, 'initials': author.initials, 'color': author.avatar_color,
        'text': message.text, 'time': date_format(timezone.localtime(message.created_at), 'd M, H:i'),
        'mine': author.pk == viewer.pk, 'staff': author.is_staff,
        'can_delete': author.pk == viewer.pk or viewer.is_staff,
    }


@login_required
def room_page(request, slug=None):
    rooms = list(ChatRoom.objects.filter(is_active=True))
    if not rooms:
        raise Http404
    room = next((r for r in rooms if r.slug == slug), None) if slug else rooms[0]
    if room is None:
        raise Http404
    return render(request, 'chat/room.html', {
        'rooms': rooms, 'room': room, 'mute': services.active_mute(request.user),
        'max_length': services.MAX_LENGTH,
    })


@login_required
@require_GET
def message_list(request, slug):
    room = _room(slug)
    visible = room.messages.filter(deleted_at__isnull=True).select_related('user')
    after, before = _int(request.GET.get('after')), _int(request.GET.get('before'))
    if after is not None:
        items = list(visible.filter(pk__gt=after).order_by('pk')[:PAGE])
    else:
        if before is not None:
            visible = visible.filter(pk__lt=before)
        items = list(visible.order_by('-pk')[:PAGE])[::-1]
    removed = room.messages.filter(deleted_at__gte=timezone.now() - REMOVED_WINDOW).values_list('pk', flat=True)
    return JsonResponse({'messages': [_payload(m, request.user) for m in items], 'removed': list(removed)})


@login_required
@require_POST
def send(request, slug):
    room = _room(slug)
    mute = services.active_mute(request.user)
    if mute:
        until = date_format(timezone.localtime(mute.until), 'd M, H:i')
        return JsonResponse({'error': f"Siz {until} gacha yoza olmaysiz"}, status=403)
    text = services.clean_text(request.POST.get('text'))
    error = services.rule_error(request.user, text)
    if error:
        return JsonResponse({'error': error}, status=400)
    error = services.rate_error(request.user)
    if error:
        return JsonResponse({'error': error}, status=429)
    message = ChatMessage.objects.create(room=room, user=request.user, text=text)
    return JsonResponse({'message': _payload(message, request.user)})


@login_required
@require_POST
def delete(request, pk):
    message = get_object_or_404(ChatMessage, pk=pk, deleted_at__isnull=True)
    if message.user_id != request.user.pk and not request.user.is_staff:
        return JsonResponse({'error': "Ruxsat yo'q"}, status=403)
    services.hide(message, by=request.user)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def report(request, pk):
    message = get_object_or_404(ChatMessage, pk=pk, deleted_at__isnull=True)
    if message.user_id == request.user.pk:
        return JsonResponse({'error': "O'z xabaringizga shikoyat qilib bo'lmaydi"}, status=400)
    services.report(message, request.user)
    return JsonResponse({'ok': True})


# ── Moderation (panel) ─────────────────────────────────────────────────────────
@panel_required
def moderation(request):
    if request.method == 'POST':
        return _moderate(request)
    now = timezone.now()
    open_filter = Q(reports__resolved_at__isnull=True)
    return render(request, 'panel/chat_moderation.html', {
        'reported': services.open_report_messages().annotate(open_reports=Count('reports', filter=open_filter)),
        'mutes': ChatMute.objects.filter(until__gt=now).select_related('user').order_by('until'),
        'latest': ChatMessage.objects.select_related('user', 'room').order_by('-pk')[:30],
    })


def _moderate(request):
    action = request.POST.get('action', '')
    if action == 'unmute':
        user = get_object_or_404(User, pk=_int(request.POST.get('user')) or 0)
        ChatMute.objects.filter(user=user).delete()
        log_action(request, 'chat', user.display_name, reverse('panel:user_detail', args=[user.pk]), 'Blok olindi')
        flash.success(request, 'Blok olib tashlandi')
        return redirect('panel:chat_moderation')

    message = get_object_or_404(ChatMessage.objects.select_related('user'), pk=_int(request.POST.get('message')) or 0)
    target, url = message.user.display_name, reverse('panel:user_detail', args=[message.user_id])
    if action == 'dismiss':
        if message.deleted_at and message.deleted_by_id is None:
            message.deleted_at = None  # was hidden by reports alone
            message.save(update_fields=['deleted_at'])
        services.resolve_reports(message)
        flash.success(request, 'Shikoyat yopildi')
    elif action in ('delete', 'mute_day', 'mute_week'):
        if message.deleted_by_id is None:
            services.hide(message, by=request.user)
        services.resolve_reports(message)
        if action == 'delete':
            flash.success(request, "Xabar o'chirildi")
        else:
            days = 1 if action == 'mute_day' else 7
            services.mute(message.user, days, request.user)
            flash.success(request, f"Xabar o'chirildi, talaba {days} kunga bloklandi")
        log_action(request, 'chat', target, url, f'{action}: {message.text[:150]}')
    return redirect('panel:chat_moderation')
