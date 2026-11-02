"""Handles one Telegram update (a message or a button press).

Dialogue state (which question the bot asked last) lives on
TelegramAccount.state, because each webhook call is a fresh request.
"""
from datetime import timedelta
from html import escape

from django.core.cache import cache
from django.db.models import Avg, Count
from django.utils import timezone

from exams.models import UserResult
from users.backends import normalize_phone
from users.models import User

from . import api
from .models import Booking, ExamDay, TelegramAccount
from .services import BookingError, book, booking_text, day_details, fmt_day, site_url

MENU_BOOK = '📅 Imtihonga yozilish'
MENU_MY = '🎫 Navbatlarim'
MENU_RESULTS = '📊 Natijalarim'
MENU_ACCOUNT = '👤 Hisobim'
MENU_HELP = 'ℹ️ Yordam'
CANCEL = '❌ Bekor qilish'
SELF_STUDY = "Mustaqil tayyorlanaman"

MAIN_MENU = {
    'keyboard': [[MENU_BOOK, MENU_MY], [MENU_RESULTS, MENU_ACCOUNT], [MENU_HELP]],
    'resize_keyboard': True,
}


def _keyboard(*rows, contact=None):
    rows = [list(r) for r in rows]
    if contact:
        rows.insert(0, [{'text': contact, 'request_contact': True}])
    return {'keyboard': rows, 'resize_keyboard': True, 'one_time_keyboard': True}


def link_token_key(token):
    return f'tg_link:{token}'


# ── Entry point ───────────────────────────────────────────────────────────────

def handle_update(update):
    if 'message' in update:
        msg = update['message']
        if msg.get('chat', {}).get('type') == 'private':
            _on_message(_account(msg['chat']), msg)
    elif 'callback_query' in update:
        cq = update['callback_query']
        if cq.get('message', {}).get('chat', {}).get('type') == 'private':
            _on_callback(_account(cq['message']['chat']), cq)


def _account(chat):
    acc, _ = TelegramAccount.objects.select_related('user').get_or_create(chat_id=chat['id'])
    acc.username = chat.get('username', '')[:64]
    acc.first_name = chat.get('first_name', '')[:128]
    acc.last_seen_at = timezone.now()
    acc.is_blocked = False
    acc.save(update_fields=['username', 'first_name', 'last_seen_at', 'is_blocked'])
    return acc


def _set_state(acc, state='', **data):
    acc.state = state
    acc.state_data = data
    acc.save(update_fields=['state', 'state_data'])


def _reply(acc, text, markup=None):
    if not api.send(acc.chat_id, text, markup or MAIN_MENU):
        TelegramAccount.objects.filter(pk=acc.pk).update(is_blocked=True)


def _on_message(acc, msg):
    text = (msg.get('text') or '').strip()

    if text.startswith('/start'):
        _set_state(acc)
        payload = text.split(maxsplit=1)[1] if ' ' in text else ''
        if payload.startswith('link_'):
            return _link_by_token(acc, payload[5:])
        if payload.startswith('day_') and payload[4:].isdigit():
            return _start_booking(acc, int(payload[4:]))
        return _welcome(acc)
    if text in (CANCEL, '/cancel'):
        _set_state(acc)
        return _reply(acc, "Bekor qilindi.")

    if acc.state in ('ask_name', 'ask_phone', 'ask_center') and text not in _MENU_ACTIONS:
        return _booking_step(acc, msg, text)

    if msg.get('contact'):
        return _link_by_contact(acc, msg)

    action = _MENU_ACTIONS.get(text) or _COMMANDS.get(text.split('@')[0])
    if action:
        _set_state(acc)
        return action(acc)
    _reply(acc, "Quyidagi menyudan tanlang 👇")


# ── Main menu ─────────────────────────────────────────────────────────────────

def _welcome(acc):
    name = escape(acc.user.display_name if acc.user else acc.first_name or "do'stim")
    _reply(acc,
           f"Assalomu alaykum, <b>{name}</b>! 👋\n\n"
           "<b>AbExam</b> — IELTS Mock imtihon markazi botiga xush kelibsiz.\n\n"
           "📅 Imtihon kuniga navbatga yozilish\n"
           "🎫 Navbatingizni ko'rish va bekor qilish\n"
           "📊 Imtihon natijalaringizni olish\n"
           "🔔 Natija chiqqanda va imtihondan bir kun oldin xabar\n\n"
           f"Imtihon jadvali saytda: {site_url('/jadval/')}")


def _help(acc):
    lines = [
        "<b>Yordam</b>\n",
        f"{MENU_BOOK} — bo'sh kunlardan birini tanlab navbat oling. Saytda hisob shart emas.",
        f"{MENU_MY} — yozilgan kunlaringiz, navbatni bekor qilish.",
        f"{MENU_RESULTS} — saytdagi hisobingizni ulasangiz, natijalar shu yerga keladi.",
        "\nBuyruqlar: /start, /navbat, /natijalar, /cancel",
        f"\n🌐 Sayt: {site_url('/')}\n🗓 Jadval: {site_url('/jadval/')}",
    ]
    if acc.user and acc.user.is_staff:
        lines.append("\n<b>Xodimlar uchun:</b> /bugun — bugungi va ertangi navbatlar ro'yxati")
    _reply(acc, '\n'.join(lines))


def _days_message():
    days = list(ExamDay.objects.upcoming().filter(is_open=True).with_booked()[:12])
    open_days = [d for d in days if d.seats_left() > 0]
    if not open_days:
        return ("Hozircha yozilish ochiq imtihon kunlari yo'q. Tez orada e'lon qilinadi — "
                f"jadvalni kuzatib boring: {site_url('/jadval/')}"), None
    rows = [[(f"{fmt_day(d)} — {d.seats_left()} joy", f'book:{d.pk}')] for d in open_days]
    text = ("<b>Qaysi kunga yozilasiz?</b>\n\n"
            + '\n'.join(f"• {fmt_day(d)} — {escape(d.title)} ({d.booked_count()}/{d.capacity})" for d in days)
            + f"\n\nTo'liq jadval: {site_url('/jadval/')}")
    return text, api.inline_keyboard(rows)


def _show_days(acc):
    text, markup = _days_message()
    _reply(acc, text, markup)


def _my_bookings_message(acc):
    bookings = list(acc.bookings.select_related('day')
                    .filter(day__date__gte=timezone.localdate()).exclude(status=Booking.STATUS_CANCELLED)
                    .order_by('day__date', 'day__start_time'))
    if not bookings:
        return f"Sizda faol navbat yo'q. {MENU_BOOK} tugmasi orqali yoziling.", None
    text = "<b>Navbatlaringiz</b>\n\n" + '\n\n'.join(booking_text(b) for b in bookings)
    rows = [[(f"❌ {b.day.date:%d.%m} navbatini bekor qilish", f'unbook:{b.pk}')]
            for b in bookings if b.status == Booking.STATUS_BOOKED]
    return text, api.inline_keyboard(rows) if rows else None


def _my_bookings(acc):
    text, markup = _my_bookings_message(acc)
    _reply(acc, text, markup)


def _results(acc):
    if not acc.user:
        return _ask_link(acc)
    graded = list(UserResult.objects.graded().filter(user=acc.user).select_related('exam')
                  .order_by('-completed_at')[:5])
    pending = UserResult.objects.pending().filter(user=acc.user).count()
    if not graded and not pending:
        return _reply(acc, "Hali natijalaringiz yo'q. Imtihon topshirganingizdan so'ng shu yerda ko'rinadi.")
    blocks = []
    for r in graded:
        parts = [f"{n} {s:.1f}" for n, s in (('L', r.listening_score), ('R', r.reading_score),
                                             ('W', r.writing_score), ('S', r.speaking_score)) if s]
        blocks.append(f"📝 {escape(r.exam.title)}\n"
                      f"   Umumiy: <b>{r.score:.1f}</b>" + (f"  ({' · '.join(parts)})" if parts else '')
                      + f"\n   {timezone.localtime(r.completed_at):%d.%m.%Y}")
    text = "<b>So'nggi natijalaringiz</b>\n\n" + '\n\n'.join(blocks)
    if pending:
        text += f"\n\n⏳ {pending} ta natija tekshirilmoqda (Writing). Chiqqanda xabar beramiz."
    _reply(acc, text, api.inline_keyboard([[("Barcha natijalar", site_url('/results-list/'))]]))


def _account_info(acc):
    if not acc.user:
        return _ask_link(acc)
    u = acc.user
    stats = UserResult.objects.graded().filter(user=u).aggregate(n=Count('id'), avg=Avg('score'))
    balance = f"{u.balance:,.0f}".replace(',', ' ')
    _reply(acc,
           f"👤 <b>{escape(u.display_name)}</b> (@{escape(u.username)})\n"
           f"📞 {escape(u.phone_number or '—')}\n"
           f"💰 Balans: {balance} so'm\n"
           f"📊 Imtihonlar: {stats['n']}" + (f", o'rtacha ball {stats['avg']:.1f}" if stats['avg'] else ''),
           api.inline_keyboard([[("🌐 Saytga o'tish", site_url('/dashboard/'))],
                                [("🔌 Hisobni botdan uzish", 'unlink')]]))


def _staff_today(acc):
    if not (acc.user and acc.user.is_staff):
        return _reply(acc, "Bu buyruq faqat xodimlar uchun.")
    today = timezone.localdate()
    days = ExamDay.objects.filter(date__range=(today, today + timedelta(days=1))).prefetch_related('bookings')
    if not days:
        return _reply(acc, "Bugun va ertaga imtihon kunlari yo'q.")
    blocks = []
    for d in days:
        rows = [f"{b.queue_number}. {'✅' if b.status == Booking.STATUS_CAME else '▫️'} {escape(b.full_name)} — "
                f"{escape(b.phone)}" + (f" ({escape(b.center)})" if b.center else '')
                for b in d.bookings.all() if b.status != Booking.STATUS_CANCELLED]
        blocks.append(f"<b>{fmt_day(d)}</b> — {escape(d.title)} ({len(rows)}/{d.capacity})\n"
                      + ('\n'.join(rows) or "Hali hech kim yozilmagan"))
    _reply(acc, '\n\n'.join(blocks))


_MENU_ACTIONS = {
    MENU_BOOK: _show_days, MENU_MY: _my_bookings, MENU_RESULTS: _results,
    MENU_ACCOUNT: _account_info, MENU_HELP: _help,
}
_COMMANDS = {
    '/menu': _welcome, '/help': _help, '/navbat': _my_bookings, '/yozilish': _show_days,
    '/natijalar': _results, '/hisob': _account_info, '/bugun': _staff_today,
}


# ── Linking a site account ────────────────────────────────────────────────────

def _ask_link(acc):
    _reply(acc,
           "Natijalarni ko'rish uchun saytdagi hisobingizni ulang:\n\n"
           "1️⃣ Pastdagi «📱 Raqamni yuborish» tugmasini bosing — saytda shu raqam bilan "
           "ro'yxatdan o'tgan bo'lsangiz, hisob darhol ulanadi.\n"
           f"2️⃣ Yoki saytda Profil → «Telegramni ulash» tugmasini bosing: {site_url('/profile/')}",
           _keyboard([CANCEL], contact='📱 Raqamni yuborish'))


def _link(acc, user):
    TelegramAccount.objects.filter(user=user).exclude(pk=acc.pk).update(user=None)
    acc.user = user
    acc.save(update_fields=['user'])
    _reply(acc, f"✅ Hisob ulandi: <b>{escape(user.display_name)}</b>\n\n"
                "Endi natijalaringiz chiqishi bilan shu yerga xabar keladi.")


def _link_by_token(acc, token):
    user_id = cache.get(link_token_key(token))
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if not user:
        return _reply(acc, "Havola eskirgan. Saytda Profil → «Telegramni ulash» tugmasini qayta bosing.")
    cache.delete(link_token_key(token))
    _link(acc, user)


def _link_by_contact(acc, msg):
    contact = msg['contact']
    # Telegram vouches for the number only when it's the sender's own contact.
    if contact.get('user_id') != msg.get('from', {}).get('id'):
        return _reply(acc, "Iltimos, o'zingizning raqamingizni tugma orqali yuboring.")
    phone = normalize_phone(contact.get('phone_number', ''))
    user = User.objects.filter(phone_number=phone, is_active=True).first() if phone else None
    if not user:
        return _reply(acc, f"Bu raqam ({escape(phone or '?')}) bilan saytda hisob topilmadi.\n"
                           f"Ro'yxatdan o'ting: {site_url('/register/')}")
    _link(acc, user)


# ── Booking dialogue ──────────────────────────────────────────────────────────

def _start_booking(acc, day_id):
    day = ExamDay.objects.filter(pk=day_id).first()
    if not day or not day.accepts_bookings():
        return _reply(acc, "Bu kunga yozilish yopilgan yoki joy qolmagan. Boshqa kunni tanlang.")
    existing = day.active_bookings().filter(account=acc).first()
    if existing:
        return _reply(acc, f"Siz bu kunga allaqachon yozilgansiz.\n\n{booking_text(existing)}")
    name = acc.full_name or (acc.user.get_full_name() if acc.user else '')
    phone = acc.phone or (acc.user.phone_number if acc.user else '') or ''
    if name and phone:
        _set_state(acc, 'confirm', day=day.pk, name=name, phone=phone, center=acc.center)
        return _send_confirm(acc)
    _set_state(acc, 'ask_name', day=day.pk)
    _reply(acc, f"{day_details(day)}\n\n✍️ Ism va familiyangizni yozing:", _keyboard([CANCEL]))


def _booking_step(acc, msg, text):
    data = acc.state_data
    if acc.state == 'ask_name':
        if not 3 <= len(text) <= 150 or text.startswith('/'):
            return _reply(acc, "Ism va familiyani to'liq yozing (masalan: Aliyev Vali).", _keyboard([CANCEL]))
        _set_state(acc, 'ask_phone', **data, name=text)
        return _reply(acc, "📞 Telefon raqamingizni yuboring yoki yozing (+998901234567):",
                      _keyboard([CANCEL], contact='📱 Raqamni yuborish'))
    if acc.state == 'ask_phone':
        phone = normalize_phone(msg['contact']['phone_number'] if msg.get('contact') else text)
        if not phone:
            return _reply(acc, "Raqam noto'g'ri. Masalan: +998901234567",
                          _keyboard([CANCEL], contact='📱 Raqamni yuborish'))
        _set_state(acc, 'ask_center', **data, phone=phone)
        return _reply(acc, "🏫 Qaysi o'quv markazda o'qiysiz? Markaz nomini yozing:",
                      _keyboard([SELF_STUDY], [CANCEL]))
    if acc.state == 'ask_center':
        if len(text) > 150 or not text:
            return _reply(acc, "Markaz nomini qisqaroq yozing.", _keyboard([SELF_STUDY], [CANCEL]))
        _set_state(acc, 'confirm', **data, center='' if text == SELF_STUDY else text)
        return _send_confirm(acc)


def _send_confirm(acc):
    data = acc.state_data
    day = ExamDay.objects.filter(pk=data['day']).first()
    if not day:
        _set_state(acc)
        return _reply(acc, "Bu imtihon kuni topilmadi.")
    text = (f"<b>Ma'lumotlarni tekshiring</b>\n\n{day_details(day)}\n\n"
            f"👤 {escape(data['name'])}\n📞 {escape(data['phone'])}\n"
            f"🏫 {escape(data.get('center') or 'Mustaqil')}")
    _reply(acc, text, api.inline_keyboard([
        [('✅ Tasdiqlash', 'bok')],
        [("✏️ O'zgartirish", 'bedit'), ('❌ Bekor', 'bcancel')],
    ]))


def _confirm_booking(acc, cq):
    data = acc.state_data
    if acc.state != 'confirm' or 'day' not in data:
        return api.answer_callback(cq['id'], "Bu so'rov eskirgan.", alert=True)
    try:
        booking = book(data['day'], data['name'], data['phone'], data.get('center', ''), account=acc)
    except BookingError as e:
        _set_state(acc)
        api.answer_callback(cq['id'], str(e), alert=True)
        return api.edit(acc.chat_id, cq['message']['message_id'], f"❌ {escape(str(e))}")
    acc.full_name, acc.phone, acc.center = data['name'], data['phone'], data.get('center', '')
    acc.save(update_fields=['full_name', 'phone', 'center'])
    _set_state(acc)
    api.answer_callback(cq['id'], 'Navbatga yozildingiz!')
    api.edit(acc.chat_id, cq['message']['message_id'],
             f"✅ <b>Siz navbatga yozildingiz!</b>\n\n{booking_text(booking)}\n\n"
             "Imtihondan bir kun oldin eslatma yuboramiz.")
    _reply(acc, "Navbatlaringizni «🎫 Navbatlarim» bo'limida ko'rasiz.")
    from core.utils import notify_staff_work
    notify_staff_work(f"🎫 <b>Yangi navbat</b> (bot)\n{booking_text(booking)}")


# ── Inline buttons ────────────────────────────────────────────────────────────

def _on_callback(acc, cq):
    data = cq.get('data', '')
    message_id = cq['message']['message_id']

    if data.startswith('book:') and data[5:].isdigit():
        api.answer_callback(cq['id'])
        return _start_booking(acc, int(data[5:]))
    if data == 'bok':
        return _confirm_booking(acc, cq)
    if data == 'bedit':
        day_id = acc.state_data.get('day')
        api.answer_callback(cq['id'])
        if not day_id:
            return None
        api.edit(acc.chat_id, message_id, "✏️ Ma'lumotlarni qayta kiritamiz.")
        _set_state(acc, 'ask_name', day=day_id)
        return _reply(acc, "✍️ Ism va familiyangizni yozing:", _keyboard([CANCEL]))
    if data == 'bcancel':
        _set_state(acc)
        api.answer_callback(cq['id'])
        api.edit(acc.chat_id, message_id, "Yozilish bekor qilindi.")
        return _reply(acc, "Asosiy menyu 👇")
    if data.startswith('unbook:') and data[7:].isdigit():
        booking = acc.bookings.select_related('day').filter(pk=int(data[7:]), status=Booking.STATUS_BOOKED,
                                                            day__date__gte=timezone.localdate()).first()
        if not booking:
            return api.answer_callback(cq['id'], "Navbat topilmadi.", alert=True)
        booking.status = Booking.STATUS_CANCELLED
        booking.save(update_fields=['status'])
        api.answer_callback(cq['id'], "Navbat bekor qilindi")
        text, markup = _my_bookings_message(acc)
        api.edit(acc.chat_id, message_id, text, markup)
        from core.utils import notify_staff_work
        return notify_staff_work(f"🚫 <b>Navbat bekor qilindi</b> (bot)\n{booking_text(booking)}")
    if data == 'unlink':
        acc.user = None
        acc.save(update_fields=['user'])
        api.answer_callback(cq['id'], "Hisob uzildi")
        return api.edit(acc.chat_id, message_id, "🔌 Sayt hisobi botdan uzildi.")
    api.answer_callback(cq['id'])
