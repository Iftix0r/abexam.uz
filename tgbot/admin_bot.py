"""Bot features for staff: alerts about new members and questions with
buttons to act on them, stats, exam-day check-in and broadcasts."""
import threading
import time
from datetime import timedelta

from django.core.cache import cache
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from core.models import AuditLog
from exams.models import UserResult
from payments.models import Transaction
from users.models import User

from . import api
from .models import Booking, ExamDay, TelegramAccount
from .services import booking_text, escape, fmt_day, notify_admins, site_url
from .ui import CANCEL, keyboard, reply, set_state, who

# Callback prefixes only staff may press.
CALLBACKS = {'adm', 'day', 'came', 'bcame', 'acancel', 'ban', 'unban', 'reply'}

SOURCES = {'day': "jadvaldagi «Yozilish» tugmasi", 'link': "saytdagi «Telegramni ulash»"}


def _audit(acc, action, target, details=''):
    if acc.user_id:
        AuditLog.objects.create(staff=acc.user, staff_name=acc.user.display_name, action=action,
                                target=str(target)[:255], details=f'Telegram bot: {details}')


# ── Alerts ────────────────────────────────────────────────────────────────────

def member_markup(acc):
    return api.inline_keyboard([
        [('💬 Yozish', f'reply:{acc.pk}'), ('🚫 Bloklash', f'ban:{acc.pk}')],
        [('👤 Telegram profil', f'https://t.me/{acc.username}')] if acc.username else [],
    ])


def notify_new_member(acc, payload=''):
    today = timezone.localdate()
    total = TelegramAccount.objects.count()
    new_today = TelegramAccount.objects.filter(created_at__date=today).count()
    source = SOURCES.get(payload.split('_')[0]) if payload else None
    notify_admins(
        f"🆕 <b>Botga yangi a'zo</b>\n"
        f"👤 {escape(who(acc))}\n🆔 <code>{acc.chat_id}</code>\n"
        + (f"🔗 Qayerdan: {source}\n" if source else '')
        + f"👥 Jami: {total} (bugun +{new_today})",
        member_markup(acc),
    )


def forward_question(acc, msg):
    """«✉️ Adminga yozish»: the student's message goes to staff with a reply button."""
    header = f"✉️ <b>Savol</b> — {escape(who(acc))}\n🆔 <code>{acc.chat_id}</code>"
    markup = api.inline_keyboard([[('↩️ Javob berish', f'reply:{acc.pk}'), ('🚫 Bloklash', f'ban:{acc.pk}')]])
    if msg.get('text'):
        return notify_admins(f"{header}\n\n{escape(msg['text'][:3500])}", markup)
    # Photos, files, voice: forward the original after the header.
    from .services import admin_chat_ids
    for chat_id in admin_chat_ids():
        api.send(chat_id, header, markup)
        api.call('forwardMessage', chat_id=chat_id, from_chat_id=acc.chat_id, message_id=msg['message_id'])


# ── Admin menu ────────────────────────────────────────────────────────────────

def menu(acc):
    reply(acc, "🛠 <b>Admin panel</b>", api.inline_keyboard([
        [('📊 Statistika', 'adm:stats'), ('📋 Navbatlar', 'adm:days')],
        [('📣 Xabar yuborish', 'adm:bc'), ("👥 Yangi a'zolar", 'adm:new')],
        [('🌐 Saytdagi panel', site_url('/panel/'))],
    ]))


def _stats_text():
    now = timezone.now()
    today = timezone.localdate()
    week = now - timedelta(days=7)
    bots = TelegramAccount.objects
    bookings = Booking.objects.filter(day__date__gte=today, status=Booking.STATUS_BOOKED)
    return (
        f"📊 <b>Statistika</b> — {timezone.localtime(now):%d.%m.%Y %H:%M}\n\n"
        f"<b>Bot</b>\n"
        f"👥 A'zolar: {bots.count()} (bugun +{bots.filter(created_at__date=today).count()}, "
        f"7 kun +{bots.filter(created_at__gte=week).count()})\n"
        f"🔗 Saytga ulangan: {bots.filter(user__isnull=False).count()}\n"
        f"🚫 Botni bloklagan: {bots.filter(Q(is_blocked=True) | Q(is_banned=True)).count()}\n\n"
        f"<b>Sayt</b>\n"
        f"👤 Foydalanuvchilar: {User.objects.count()} (bugun +{User.objects.filter(date_joined__date=today).count()})\n"
        f"📝 Bugun topshirilgan imtihonlar: {UserResult.objects.filter(completed_at__date=today).count()}\n"
        f"✍️ Writing tekshirish kutmoqda: {UserResult.objects.pending().count()}\n"
        f"💳 Tasdiqlanmagan to'lovlar: {Transaction.objects.filter(status='pending').count()}\n\n"
        f"<b>Navbat</b>\n"
        f"📅 Rejadagi kunlar: {ExamDay.objects.upcoming().count()}\n"
        f"🎫 Navbatdagilar: {bookings.count()} (bugun: {bookings.filter(day__date=today).count()})"
    )


def _days_view():
    days = list(ExamDay.objects.upcoming().with_booked()[:20])
    if not days:
        return "Rejadagi imtihon kunlari yo'q. Panelda qo'shing.", api.inline_keyboard(
            [[("➕ Kun qo'shish", site_url('/panel/exam-days/'))]])
    rows = [[(f"{fmt_day(d)} — {d.booked}/{d.capacity}" + ('' if d.is_open else ' 🔒'), f'day:{d.pk}')] for d in days]
    return "📋 <b>Imtihon kunlari</b>\nKunni tanlang — navbatdagilar ro'yxati va kelganlarni belgilash:", \
        api.inline_keyboard(rows)


def _day_view(day):
    bookings = list(day.active_bookings().order_by('queue_number')[:90])
    came = sum(b.status == Booking.STATUS_CAME for b in bookings)
    text = (f"📋 <b>{fmt_day(day)}</b> — {escape(day.title)}\n"
            f"Navbatda: {len(bookings)}/{day.capacity} · keldi: {came}\n\n"
            + ('\n'.join(f"{b.queue_number}. {escape(b.full_name)} — {escape(b.phone)}"
                         + (f" ({escape(b.center)})" if b.center else '') for b in bookings)
               or "Hali hech kim yozilmagan.")
            + ("\n\nKelganini belgilash uchun ismini bosing." if bookings else ''))
    rows = [[(f"{'✅' if b.status == Booking.STATUS_CAME else '▫️'} {b.queue_number}. {b.full_name[:40]}",
              f'came:{b.pk}')] for b in bookings]
    rows.append([('🔄 Yangilash', f'day:{day.pk}'), ('⬅️ Kunlar', 'adm:days')])
    rows.append([('📥 CSV (saytda)', site_url(f'/panel/exam-days/{day.pk}/export/'))])
    return text[:4000], api.inline_keyboard(rows)


def _new_members_text():
    accs = TelegramAccount.objects.select_related('user').order_by('-created_at')[:15]
    return "👥 <b>So'nggi a'zolar</b>\n\n" + '\n'.join(
        f"• {escape(who(a))} — {timezone.localtime(a.created_at):%d.%m %H:%M}"
        + (' 🚫' if a.is_banned or a.is_blocked else '') for a in accs)


# ── Broadcast ─────────────────────────────────────────────────────────────────

def _audience():
    return TelegramAccount.objects.filter(is_blocked=False, is_banned=False)


def _broadcast(admin_chat_id, text):
    """Runs in a thread: Telegram allows ~30 messages a second."""
    close_old_connections()
    sent = failed = 0
    try:
        for acc in _audience().only('pk', 'chat_id').iterator():
            if api.send(acc.chat_id, text):
                sent += 1
            else:
                failed += 1
                TelegramAccount.objects.filter(pk=acc.pk).update(is_blocked=True)
            time.sleep(0.05)
        api.send(admin_chat_id, f"✅ Xabar yuborildi: {sent} kishiga" + (f", {failed} kishi botni bloklagan" if failed else ''))
    finally:
        cache.delete('tg_broadcast_running')
        close_old_connections()


# ── Dialogue steps (admin typing a broadcast or a reply) ──────────────────────

def on_state_message(acc, msg, text):
    if acc.state == 'bc_text':
        if not text:
            return reply(acc, "Faqat matnli xabar yuboriladi. Matnni yozing:", keyboard([CANCEL]))
        set_state(acc, 'bc_confirm', text=text[:3500])
        n = _audience().count()
        return reply(acc, f"📣 <b>Ko'rib chiqing:</b>\n\n{escape(text[:3500])}\n\n— {n} kishiga yuboriladi.",
                     api.inline_keyboard([[('✅ Yuborish', 'adm:bcgo'), ('❌ Bekor', 'adm:bcno')]]))
    if acc.state == 'reply':
        target = TelegramAccount.objects.filter(pk=acc.state_data.get('to')).first()
        set_state(acc)
        if not target or not text:
            return reply(acc, "Javob yuborilmadi (faqat matn yuboriladi).")
        ok = api.send(target.chat_id, f"💬 <b>AbExam admin javobi:</b>\n\n{escape(text)}",
                      api.inline_keyboard([[('✉️ Yana yozish', 'support')]]))
        _audit(acc, 'tgbot', who(target), f'Javob: {text[:200]}')
        return reply(acc, f"✅ Javob yuborildi: {escape(who(target))}" if ok else "❌ Foydalanuvchi botni bloklagan.")


# ── Buttons ───────────────────────────────────────────────────────────────────

def _append(cq, line, markup=None):
    """Adds a status line under an alert (keeps it readable for other admins)."""
    msg = cq['message']
    api.edit(msg['chat']['id'], msg['message_id'], escape(msg.get('text', ''))[:3800] + f"\n\n{line}", markup)


def on_callback(actor, cq):
    data = cq.get('data', '')
    kind, _, arg = data.partition(':')
    chat_id = cq['message']['chat']['id']
    message_id = cq['message']['message_id']
    by = escape(actor.user.display_name if actor.user_id else actor.first_name or 'admin')

    if kind == 'adm':
        api.answer_callback(cq['id'])
        if arg == 'stats':
            return api.edit(chat_id, message_id, _stats_text(), api.inline_keyboard([[('🔄 Yangilash', 'adm:stats')]]))
        if arg == 'days':
            return api.edit(chat_id, message_id, *_days_view())
        if arg == 'new':
            return api.edit(chat_id, message_id, _new_members_text())
        if arg == 'bc':
            set_state(actor, 'bc_text')
            return reply(actor, "📣 Barcha bot a'zolariga yuboriladigan xabar matnini yozing:", keyboard([CANCEL]))
        if arg == 'bcgo' and actor.state == 'bc_confirm':
            text = actor.state_data.get('text', '')
            set_state(actor)
            # One broadcast at a time, so a double tap doesn't send twice.
            if not cache.add('tg_broadcast_running', 1, 3600):
                return api.edit(chat_id, message_id, "⏳ Boshqa xabar hozir yuborilmoqda, keyinroq urinib ko'ring.")
            _audit(actor, 'tgbot', "Barcha bot a'zolari", f'Xabar yuborildi: {text[:200]}')
            api.edit(chat_id, message_id, f"⏳ Yuborilmoqda...\n\n{escape(text)}")
            threading.Thread(target=_broadcast, args=(actor.chat_id, escape(text)), daemon=True).start()
            return None
        if arg == 'bcno':
            set_state(actor)
            return api.edit(chat_id, message_id, "Bekor qilindi.")
        return None

    if kind == 'day':
        day = ExamDay.objects.filter(pk=arg).first()
        api.answer_callback(cq['id'])
        if day:
            return api.edit(chat_id, message_id, *_day_view(day))
        return None

    if kind in ('came', 'bcame', 'acancel'):
        b = Booking.objects.select_related('day', 'account').filter(pk=arg).first()
        if not b:
            return api.answer_callback(cq['id'], "Navbat topilmadi", alert=True)
        if kind == 'acancel':
            if b.status == Booking.STATUS_CANCELLED:
                return api.answer_callback(cq['id'], "Allaqachon bekor qilingan")
            b.status = Booking.STATUS_CANCELLED
            b.save(update_fields=['status'])
            _audit(actor, 'booking', f'{b.full_name} — {b.day}', 'Bekor qilindi')
            if b.account and not b.account.is_blocked:
                api.send_async(b.account.chat_id, f"⚠️ <b>Navbatingiz bekor qilindi</b>\n\n{booking_text(b)}\n\n"
                                                  "Savol bo'lsa «✉️ Adminga yozish» tugmasini bosing.")
            api.answer_callback(cq['id'], "Bekor qilindi")
            return _append(cq, f"❌ Bekor qilindi — {by}")
        b.status = Booking.STATUS_BOOKED if b.status == Booking.STATUS_CAME else Booking.STATUS_CAME
        b.save(update_fields=['status'])
        _audit(actor, 'booking', f'{b.full_name} — {b.day}', b.get_status_display())
        api.answer_callback(cq['id'], f"#{b.queue_number} {b.full_name}: {b.get_status_display()}")
        if kind == 'came':
            return api.edit(chat_id, message_id, *_day_view(b.day))
        return _append(cq, f"✅ Keldi — {by}" if b.status == Booking.STATUS_CAME else f"↩️ Navbatga qaytarildi — {by}")

    target = TelegramAccount.objects.select_related('user').filter(pk=arg).first()
    if not target:
        return api.answer_callback(cq['id'], "Foydalanuvchi topilmadi", alert=True)
    if kind in ('ban', 'unban'):
        target.is_banned = kind == 'ban'
        target.save(update_fields=['is_banned'])
        _audit(actor, 'tgbot', who(target), 'Botda bloklandi' if target.is_banned else 'Blokdan chiqarildi')
        api.answer_callback(cq['id'], 'Bloklandi' if target.is_banned else 'Blokdan chiqarildi')
        toggle = ('✅ Blokdan chiqarish', f'unban:{target.pk}') if target.is_banned else ('🚫 Bloklash', f'ban:{target.pk}')
        return _append(cq, f"{'🚫 Bloklandi' if target.is_banned else '✅ Blokdan chiqarildi'} — {by}",
                       api.inline_keyboard([[('💬 Yozish', f'reply:{target.pk}'), toggle]]))
    if kind == 'reply':
        set_state(actor, 'reply', to=target.pk)
        if not api.send(actor.chat_id, f"✍️ <b>{escape(who(target))}</b> ga javobingizni yozing:", keyboard([CANCEL])):
            set_state(actor)
            return api.answer_callback(cq['id'], "Avval botga shaxsiy /start yozing", alert=True)
        return api.answer_callback(cq['id'], "Javobni bot bilan shaxsiy chatda yozing")
    return api.answer_callback(cq['id'])
