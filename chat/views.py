from datetime import timedelta

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_GET, require_POST

from core.audit import log_action
from core.models import SiteSettings
from exams.models import UserResult
from panel.views import _user_search, panel_required
from users.models import User

from . import services
from .models import ChatBlock, ChatMessage, ChatMute, ChatReaction, ChatRoom, ChatThread, SupportThread

PAGE = 50
RECENT_REACTIONS = 40
REMOVED_WINDOW = timedelta(minutes=10)
ADMIN_NAME = 'AB Admin'


def _room(slug):
    return get_object_or_404(ChatRoom, slug=slug, is_active=True)


def _int(value):
    return int(value) if value and value.isdigit() else None


def _dm_enabled():
    return SiteSettings.get().chat_dm_enabled


def _thread(request, pk):
    if not _dm_enabled():
        raise Http404
    thread = get_object_or_404(ChatThread.objects.select_related('user_a', 'user_b'), pk=pk)
    if not thread.has(request.user) or thread.is_hidden_from(request.user):
        raise Http404
    return thread


def _accessible_message(request, pk):
    message = get_object_or_404(ChatMessage.objects.select_related('thread', 'room', 'support'), pk=pk,
                                deleted_at__isnull=True)
    if not services.can_access(message, request.user):
        raise Http404
    return message


def _from_admin(message):
    return message.support_id is not None and message.user_id != message.support.user_id


def _reply(message):
    target = message.reply_to
    if target is None or target.deleted_at:
        return None
    return {'id': target.pk, 'name': ADMIN_NAME if _from_admin(target) else target.user.short_name,
            'text': target.text[:90]}


def _payload(message, viewer, reactions):
    author = message.user
    # Short name and initials only, as on the rating: no photos, phones or usernames.
    payload = {
        'id': message.pk, 'user_id': author.pk, 'name': author.short_name, 'initials': author.initials,
        'color': author.avatar_color, 'text': message.text, 'premium': author.is_premium,
        'time': date_format(timezone.localtime(message.created_at), 'd M, H:i'),
        'mine': author.pk == viewer.pk, 'staff': author.is_staff,
        'can_delete': author.pk == viewer.pk or viewer.is_staff,
        'reply': _reply(message), 'reactions': reactions.get(message.pk),
    }
    if _from_admin(message):  # the student sees the team, not the person
        payload.update({'user_id': None, 'name': ADMIN_NAME, 'initials': 'AB', 'color': '#d32f2f', 'premium': False})
    return payload


def _serialized(items, viewer):
    reactions = services.reaction_map([m.pk for m in items], viewer)
    return [_payload(m, viewer, reactions) for m in items]


def _page_of(queryset, request):
    visible = queryset.filter(deleted_at__isnull=True).select_related('user', 'support', 'reply_to__user',
                                                                      'reply_to__support')
    after, before = _int(request.GET.get('after')), _int(request.GET.get('before'))
    if after is not None:
        return list(visible.filter(pk__gt=after).order_by('pk')[:PAGE])
    if before is not None:
        visible = visible.filter(pk__lt=before)
    return list(visible.order_by('-pk')[:PAGE])[::-1]


def _recent_reactions(queryset, viewer):
    """Live counts for the latest messages, already on the reader's screen."""
    ids = list(queryset.filter(deleted_at__isnull=True).order_by('-pk').values_list('pk', flat=True)[:RECENT_REACTIONS])
    found = services.reaction_map(ids, viewer)
    return {str(pk): found.get(pk) for pk in ids}


def _removed(queryset):
    return list(queryset.filter(deleted_at__gte=timezone.now() - REMOVED_WINDOW).values_list('pk', flat=True))


def _thread_rows(user):
    rows = []
    for thread in services.threads_of(user)[:40]:
        other = thread.other(user)
        last = thread.last_message
        rows.append({
            'id': thread.pk, 'name': other.short_name, 'initials': other.initials, 'avatar_color': other.avatar_color,
            'preview': last.text[:40] if not last.deleted_at else "Xabar o'chirilgan",
            'unread': last.user_id != user.pk and last.pk > thread.read_id(user),
            'incoming': thread.status == ChatThread.REQUEST and thread.requested_by_id != user.pk,
        })
    return rows


def _support_row(user):
    thread = SupportThread.objects.filter(user=user).select_related('last_message').first()
    last = thread.last_message if thread else None
    return {
        'preview': last.text[:40] if last else "Savol va yordam",
        'unread': bool(last and last.user_id != user.pk and last.pk > thread.user_read),
    }


def _page_context(request, **extra):
    dm = _dm_enabled()
    return {
        'support_row': _support_row(request.user),
        'rooms': list(ChatRoom.objects.filter(is_active=True)), 'dm_enabled': dm,
        'threads': _thread_rows(request.user) if dm else [],
        'mute': services.active_mute(request.user), 'max_length': services.MAX_LENGTH, **extra,
    }


@login_required
def room_page(request, slug=None):
    context = _page_context(request)
    rooms = context['rooms']
    if not rooms:
        raise Http404
    room = next((r for r in rooms if r.slug == slug), None) if slug else rooms[0]
    if room is None:
        raise Http404
    return render(request, 'chat/room.html', {**context, 'room': room})


@login_required
@require_GET
def message_list(request, slug):
    room = _room(slug)
    services.touch_presence(room, request.user)
    pinned = room.pinned if room.pinned_id and room.pinned.deleted_at is None else None
    return JsonResponse({
        'messages': _serialized(_page_of(room.messages.all(), request), request.user),
        'removed': _removed(room.messages.all()),
        'reactions': _recent_reactions(room.messages.all(), request.user),
        'counts': services.room_counts(room),
        'pinned': {'id': pinned.pk, 'name': pinned.user.short_name, 'text': pinned.text[:140]} if pinned else None,
    })


@login_required
@require_GET
def members(request, slug):
    room = _room(slug)
    since = services.online_since()
    rows = room.presence.select_related('user').order_by('-last_seen')[:60]
    return JsonResponse({'members': [{
        'id': p.user_id, 'name': p.user.short_name, 'initials': p.user.initials, 'color': p.user.avatar_color,
        'online': p.last_seen >= since, 'staff': p.user.is_staff, 'premium': p.user.is_premium,
    } for p in rows]})


def _checked_text(request, support=False):
    """Returns (text, error response). AB Admin stays reachable when muted:
    that is where a student asks about the mute."""
    mute = None if support else services.active_mute(request.user)
    if mute:
        until = date_format(timezone.localtime(mute.until), 'd M, H:i')
        return None, JsonResponse({'error': f"Siz {until} gacha yoza olmaysiz"}, status=403)
    text = services.clean_text(request.POST.get('text'))
    error = services.rule_error(request.user, text, contacts_ok=support)
    if error:
        return None, JsonResponse({'error': error}, status=400)
    error = services.rate_error(request.user)
    if error:
        return None, JsonResponse({'error': error}, status=429)
    return text, None


def _reply_target(request, **where):
    pk = _int(request.POST.get('reply_to'))
    return ChatMessage.objects.filter(pk=pk, deleted_at__isnull=True, **where).first() if pk else None


@login_required
@require_POST
def send(request, slug):
    room = _room(slug)
    text, failed = _checked_text(request)
    if failed:
        return failed
    message = ChatMessage.objects.create(room=room, user=request.user, text=text,
                                         reply_to=_reply_target(request, room=room))
    return JsonResponse({'message': _serialized([message], request.user)[0]})


@login_required
@require_POST
def delete(request, pk):
    message = _accessible_message(request, pk)
    if message.user_id != request.user.pk and not request.user.is_staff:
        return JsonResponse({'error': "Ruxsat yo'q"}, status=403)
    services.hide(message, by=request.user)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def report(request, pk):
    message = _accessible_message(request, pk)
    if message.user_id == request.user.pk or message.support_id:
        return JsonResponse({'error': "Bu xabarga shikoyat qilib bo'lmaydi"}, status=400)
    services.report(message, request.user)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def react(request, pk):
    message = _accessible_message(request, pk)
    kind = request.POST.get('kind', '')
    if kind not in ChatReaction.KINDS:
        return JsonResponse({'error': "Noto'g'ri reaksiya"}, status=400)
    services.toggle_reaction(message, request.user, kind)
    return JsonResponse({'reactions': services.reaction_map([message.pk], request.user).get(message.pk)})


@login_required
@require_POST
def pin(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': "Ruxsat yo'q"}, status=403)
    message = _accessible_message(request, pk)
    if message.room is None:
        return JsonResponse({'error': "Faqat xonada qadash mumkin"}, status=400)
    room = message.room
    room.pinned = None if room.pinned_id == message.pk else message
    room.save(update_fields=['pinned'])
    return JsonResponse({'ok': True})


# ── Profile card, private chats, blocking ──────────────────────────────────────
@login_required
@require_GET
def user_card(request, pk):
    other = get_object_or_404(User, pk=pk, is_active=True)
    stats = (UserResult.objects.graded().filter(user=other, exam__exam_type='mock', score__gt=0)
             .aggregate(best=Max('score'), avg=Avg('score'), tests=Count('id')))
    return JsonResponse({
        'id': other.pk, 'name': other.short_name, 'initials': other.initials, 'color': other.avatar_color,
        'staff': other.is_staff, 'premium': other.is_premium, 'online': services.is_online(other), 'best': stats['best'], 'tests': stats['tests'],
        'me': other.pk == request.user.pk, 'dm': _dm_enabled(),
        'blocked': ChatBlock.objects.filter(blocker=request.user, blocked=other).exists(),
    })


@login_required
@require_POST
def start_chat(request, pk):
    if not _dm_enabled():
        raise Http404
    other = get_object_or_404(User, pk=pk, is_active=True)
    thread, error = services.start_thread(request.user, other)
    if error:
        return JsonResponse({'error': error}, status=400)
    return JsonResponse({'url': reverse('chat:thread', args=[thread.pk])})


@login_required
@require_POST
def toggle_block(request, pk):
    other = get_object_or_404(User, pk=pk)
    if other.pk == request.user.pk or other.is_staff:
        return JsonResponse({'error': "Bu foydalanuvchini bloklab bo'lmaydi"}, status=400)
    block, created = ChatBlock.objects.get_or_create(blocker=request.user, blocked=other)
    if not created:
        block.delete()
    return JsonResponse({'blocked': created})


@login_required
def thread_page(request, pk):
    thread = _thread(request, pk)
    other = thread.other(request.user)
    incoming = thread.status == ChatThread.REQUEST and thread.requested_by_id != request.user.pk
    return render(request, 'chat/room.html', _page_context(request, thread=thread, other=other, incoming=incoming))


@login_required
@require_GET
def thread_messages(request, pk):
    thread = _thread(request, pk)
    items = _page_of(thread.messages.all(), request)
    if items and request.GET.get('seen') == '1':
        services.mark_read(thread, request.user, items[-1].pk)
    other = thread.other(request.user)
    return JsonResponse({
        'messages': _serialized(items, request.user),
        'removed': _removed(thread.messages.all()),
        'reactions': _recent_reactions(thread.messages.all(), request.user),
        'other_read': thread.read_id(other), 'other_online': services.is_online(other),
        'send_error': services.thread_send_error(thread, request.user),
    })


@login_required
@require_POST
def thread_send(request, pk):
    thread = _thread(request, pk)
    error = services.thread_send_error(thread, request.user)
    if error:
        return JsonResponse({'error': error}, status=403)
    text, failed = _checked_text(request)
    if failed:
        return failed
    message = ChatMessage.objects.create(thread=thread, user=request.user, text=text,
                                         reply_to=_reply_target(request, thread=thread))
    services.after_thread_message(thread, message)
    return JsonResponse({'message': _serialized([message], request.user)[0]})


@login_required
@require_POST
def thread_answer(request, pk):
    thread = _thread(request, pk)
    if thread.status != ChatThread.REQUEST or thread.requested_by_id == request.user.pk:
        return JsonResponse({'error': "So'rov topilmadi"}, status=400)
    accept = request.POST.get('answer') == 'accept'
    thread.status = ChatThread.ACCEPTED if accept else ChatThread.DECLINED
    thread.save(update_fields=['status', 'updated_at'])
    return JsonResponse({'url': reverse('chat:thread', args=[thread.pk]) if accept else reverse('chat:home')})


# ── AB Admin, student side ─────────────────────────────────────────────────────
@login_required
def support_page(request):
    return render(request, 'chat/room.html', _page_context(request, support=True))


@login_required
@require_GET
def support_messages(request):
    thread = services.support_of(request.user)
    items = _page_of(thread.messages.all(), request)
    if items and request.GET.get('seen') == '1':
        services.mark_support_read(thread, items[-1].pk, staff=False)
    return JsonResponse({
        'messages': _serialized(items, request.user), 'removed': _removed(thread.messages.all()),
        'reactions': _recent_reactions(thread.messages.all(), request.user),
        'other_read': thread.staff_read, 'other_online': False, 'send_error': None,
    })


@login_required
@require_POST
def support_send(request):
    thread = services.support_of(request.user)
    text, failed = _checked_text(request, support=True)
    if failed:
        return failed
    message = ChatMessage.objects.create(support=thread, user=request.user, text=text,
                                         reply_to=_reply_target(request, support=thread))
    services.after_support_message(thread, message)
    return JsonResponse({'message': _serialized([message], request.user)[0]})


# ── AB Admin inbox (panel) ─────────────────────────────────────────────────────
def _inbox_rows(query):
    threads = SupportThread.objects.filter(last_message__isnull=False).select_related('user', 'last_message')
    if query:
        threads = threads.filter(user__in=User.objects.filter(_user_search(query)))
    rows = []
    for thread in threads[:80]:
        user, last = thread.user, thread.last_message
        rows.append({
            'id': thread.pk, 'name': user.display_name, 'initials': user.initials, 'color': user.avatar_color,
            'premium': user.is_premium, 'preview': last.text[:60],
            'mine': last.user_id != user.pk,
            'time': date_format(timezone.localtime(last.created_at), 'd M, H:i'),
            'unread': last.user_id == user.pk and last.pk > thread.staff_read,
        })
    # Waiting chats first, Premium students ahead of the rest.
    rows.sort(key=lambda r: (not r['unread'], not (r['unread'] and r['premium'])))
    return rows


@panel_required
def inbox(request):
    return render(request, 'panel/chat_inbox.html', {'open_thread': _int(request.GET.get('t'))})


@panel_required
@require_GET
def inbox_threads(request):
    return JsonResponse({'threads': _inbox_rows(request.GET.get('q', '').strip())})


@panel_required
def inbox_open(request, pk):
    thread = services.support_of(get_object_or_404(User, pk=pk))
    return redirect(f"{reverse('panel:chat_inbox')}?t={thread.pk}")


def _inbox_payload(message, thread):
    from_student = message.user_id == thread.user_id
    return {
        'id': message.pk, 'text': message.text, 'mine': not from_student,
        'author': '' if from_student else message.user.display_name,
        'time': date_format(timezone.localtime(message.created_at), 'd M, H:i'),
    }


@panel_required
@require_GET
def inbox_messages(request, pk):
    thread = get_object_or_404(SupportThread.objects.select_related('user'), pk=pk)
    items = _page_of(thread.messages.all(), request)
    if items:
        services.mark_support_read(thread, items[-1].pk, staff=True)
    user = thread.user
    return JsonResponse({
        'messages': [_inbox_payload(m, thread) for m in items],
        'user': {
            'id': user.pk, 'name': user.display_name, 'phone': user.phone_number or '', 'initials': user.initials,
            'color': user.avatar_color, 'premium': user.is_premium, 'premium_days': user.premium_days_left,
            'balance': float(user.balance), 'url': reverse('panel:user_detail', args=[user.pk]),
        },
        'user_read': thread.user_read,
    })


@panel_required
@require_POST
def inbox_send(request, pk):
    thread = get_object_or_404(SupportThread.objects.select_related('user'), pk=pk)
    text = services.clean_text(request.POST.get('text'))
    error = services.rule_error(request.user, text)
    if error:
        return JsonResponse({'error': error}, status=400)
    message = ChatMessage.objects.create(support=thread, user=request.user, text=text)
    services.after_support_message(thread, message)
    return JsonResponse({'message': _inbox_payload(message, thread)})


# ── Moderation (panel) ─────────────────────────────────────────────────────────
@panel_required
def moderation(request):
    if request.method == 'POST':
        return _moderate(request)
    now = timezone.now()
    open_filter = Q(reports__resolved_at__isnull=True)
    rooms_only = ChatMessage.objects.filter(room__isnull=False)  # private and support chats stay out
    return render(request, 'panel/chat_moderation.html', {
        'reported': services.open_report_messages().annotate(open_reports=Count('reports', filter=open_filter)),
        'mutes': ChatMute.objects.filter(until__gt=now).select_related('user').order_by('until'),
        'latest': rooms_only.select_related('user', 'room').order_by('-pk')[:30],
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
