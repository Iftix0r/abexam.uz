"""Booking logic and site → Telegram notifications, shared by the bot
handlers, the panel and the cron command."""
from datetime import timedelta
from html import escape

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from . import api
from .models import Booking, ExamDay, TelegramAccount

MONTHS = ('yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul',
          'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr')
WEEKDAYS = ('Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba')


def fmt_date(d):
    return f"{d.day}-{MONTHS[d.month - 1]}, {WEEKDAYS[d.weekday()]}"


def fmt_day(day):
    return f"{fmt_date(day.date)} · {day.start_time:%H:%M}"


def site_url(path=''):
    return settings.SITE_URL.rstrip('/') + path


def day_details(day):
    lines = [f"📅 <b>{fmt_day(day)}</b>", f"📝 {escape(day.title)}"]
    if day.location:
        lines.append(f"📍 {escape(day.location)}")
    if day.note:
        lines.append(f"ℹ️ {escape(day.note)}")
    return '\n'.join(lines)


class BookingError(Exception):
    pass


def book(day_id, full_name, phone, center='', account=None):
    """Puts someone in the queue for a day. Locks the day row so two people
    taking the last seat at the same moment can't both get it."""
    with transaction.atomic():
        day = ExamDay.objects.select_for_update().filter(pk=day_id).first()
        if not day or not day.accepts_bookings():
            raise BookingError("Bu kunga yozilish yopilgan yoki joy qolmagan.")
        if account and day.active_bookings().filter(account=account).exists():
            raise BookingError("Siz bu kunga allaqachon yozilgansiz.")
        last = day.bookings.aggregate(m=Max('queue_number'))['m'] or 0
        return Booking.objects.create(day=day, account=account, full_name=full_name, phone=phone,
                                      center=center, queue_number=last + 1)


def booking_text(booking):
    return (f"🎫 <b>Navbat #{booking.queue_number}</b>\n{day_details(booking.day)}\n"
            f"👤 {escape(booking.full_name)} · {escape(booking.phone)}"
            + (f"\n🏫 {escape(booking.center)}" if booking.center else ''))


def notify_result_ready(result):
    """Tells a student linked to the bot that their result is out — right
    after submitting, or once staff have graded their Writing."""
    acc = TelegramAccount.objects.filter(user_id=result.user_id, is_blocked=False).first()
    if not acc:
        return
    parts = [f"{name} {score:.1f}" for name, score in (
        ('L', result.listening_score), ('R', result.reading_score),
        ('W', result.writing_score), ('S', result.speaking_score)) if score]
    text = (f"🎉 <b>Natijangiz tayyor!</b>\n«{escape(result.exam.title)}»\n\n"
            f"Umumiy ball: <b>{result.score:.1f}</b>" + (f"\n{' · '.join(parts)}" if parts else ''))
    api.send_async(acc.chat_id, text, api.inline_keyboard([
        [('Batafsil ko\'rish', site_url(f'/exams/result/{result.pk}/'))],
    ]))


def notify_day_cancelled(day, bookings):
    for b in bookings:
        if b.account_id and not b.account.is_blocked:
            api.send_async(b.account.chat_id,
                           f"⚠️ <b>Imtihon bekor qilindi</b>\n{day_details(day)}\n\n"
                           "Boshqa kunga yozilish uchun «📅 Imtihonga yozilish» tugmasini bosing.")


def send_reminders(now=None):
    """Day-before reminder for everyone queued for tomorrow (cron)."""
    now = now or timezone.now()
    tomorrow = timezone.localdate(now) + timedelta(days=1)
    pending = (Booking.objects.select_related('day', 'account')
               .filter(day__date=tomorrow, status=Booking.STATUS_BOOKED, reminded_at__isnull=True,
                       account__isnull=False, account__is_blocked=False))
    sent = 0
    for b in pending:
        ok = api.send(b.account.chat_id,
                      f"⏰ <b>Eslatma: imtihon ertaga!</b>\n\n{booking_text(b)}\n\n"
                      "Pasport/ID va ruchka olib keling. Kechikmang!")
        if ok:
            sent += 1
        else:
            TelegramAccount.objects.filter(pk=b.account_id).update(is_blocked=True)
        b.reminded_at = now
        b.save(update_fields=['reminded_at'])
    return sent
