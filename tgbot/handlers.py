"""Handles one Telegram update (a message or a button press).

Dialogue state (which question the bot asked last) lives on
TelegramAccount.state, because each webhook call is a fresh request.
Staff-only features are in admin_bot.py.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Avg, Count
from django.utils import timezone

from exams.models import UserResult
from exams.views import calc_band
from users.backends import normalize_phone
from users.models import User

from . import admin_bot, api
from .models import Booking, ExamDay, TelegramAccount
from .services import (BookingError, book, booking_admin_markup, booking_text, day_details, escape, fmt_day,
                       is_admin, is_admin_chat, notify_admins, result_message, site_url)
from .ui import (CANCEL, MENU_ACCOUNT, MENU_ADMIN, MENU_BOOK, MENU_HELP, MENU_MY, MENU_RESULTS, MENU_SUPPORT,
                 keyboard, reply, set_state, who)

SELF_STUDY = "Mustaqil tayyorlanaman"
BOOKING_STATES = ('ask_name', 'ask_phone', 'ask_center')
ADMIN_STATES = ('bc_text', 'reply', 'add_admin')


def link_token_key(token):
    return f'tg_link:{token}'


# ── Entry point ───────────────────────────────────────────────────────────────

def handle_update(update):
    if 'message' in update:
        msg = update['message']
        if msg.get('chat', {}).get('type') != 'private':
            return
        acc, created = _account(msg['chat'])
        if created:
            text = msg.get('text') or ''
            admin_bot.notify_new_member(acc, text.split(maxsplit=1)[1] if text.startswith('/start ') else '')
        if acc.is_banned and not is_admin(acc):
            return
        _on_message(acc, msg)
    elif 'callback_query' in update:
        cq = update['callback_query']
        chat = cq.get('message', {}).get('chat', {})
        # Buttons work in private chats and on alerts in the staff group.
        if chat.get('type') != 'private' and not is_admin_chat(chat.get('id')):
            return
        actor, _ = _account(cq['from'])
        kind = cq.get('data', '').partition(':')[0]
        if kind in admin_bot.CALLBACKS:
            if is_admin(actor) or is_admin_chat(chat.get('id')):
                return admin_bot.on_callback(actor, cq)
            return api.answer_callback(cq['id'], "Faqat adminlar uchun", alert=True)
        if actor.is_banned:
            return api.answer_callback(cq['id'])
        _on_callback(actor, cq)


def _account(chat):
    acc, created = TelegramAccount.objects.select_related('user').get_or_create(chat_id=chat['id'])
    acc.username = (chat.get('username') or '')[:64]
    acc.first_name = (chat.get('first_name') or '')[:128]
    acc.last_seen_at = timezone.now()
    acc.is_blocked = False
    acc.save(update_fields=['username', 'first_name', 'last_seen_at', 'is_blocked'])
    return acc, created


def _on_message(acc, msg):
    text = (msg.get('text') or '').strip()

    if text.startswith('/start'):
        set_state(acc)
        payload = text.split(maxsplit=1)[1] if ' ' in text else ''
        if payload.startswith('link_'):
            return _link_by_token(acc, payload[5:])
        if payload.startswith('day_') and payload[4:].isdigit():
            return _start_booking(acc, int(payload[4:]))
        return _welcome(acc)
    if text in (CANCEL, '/cancel'):
        set_state(acc)
        return reply(acc, "Bekor qilindi.")

    if text not in _MENU_ACTIONS:
        if acc.state in BOOKING_STATES:
            return _booking_step(acc, msg, text)
        if acc.state == 'support':
            return _support_message(acc, msg)
        if acc.state in ADMIN_STATES and is_admin(acc):
            return admin_bot.on_state_message(acc, msg, text)

    if msg.get('contact'):
        return _link_by_contact(acc, msg)

    action = _MENU_ACTIONS.get(text) or _COMMANDS.get(text.split()[0].split('@')[0] if text else '')
    if action:
        set_state(acc)
        return action(acc, text) if action in _TAKES_TEXT else action(acc)
    if text.isdigit():
        return _band(acc, f'/ball {text}')
    reply(acc, "Quyidagi menyudan tanlang 👇")


# ── Main menu ─────────────────────────────────────────────────────────────────

def _welcome(acc):
    name = escape(acc.user.display_name if acc.user else acc.first_name or "do'stim")
    reply(acc,
          f"Assalomu alaykum, <b>{name}</b>! 👋\n\n"
          "<b>AbExam</b> — IELTS Mock imtihon markazi botiga xush kelibsiz.\n\n"
          "📅 Imtihon kuniga navbatga yozilish\n"
          "🎫 Navbatingizni ko'rish va bekor qilish\n"
          "📊 Natijalaringiz va ularni 📄 PDF qilib olish\n"
          "🔔 Natija chiqqanda va imtihondan bir kun oldin xabar\n"
          "✉️ Adminga savol yuborish\n\n"
          + ("✅ Sayt hisobingiz ulangan — natijalaringiz chiqishi bilan shu yerga avtomatik keladi.\n\n"
             if acc.user else
             "🔗 <b>abexam.uz da imtihon topshirasizmi?</b> Natija avtomatik kelishi uchun hisobingizni ulang: "
             "«📊 Natijalarim» → «📱 Raqamni yuborish», yoki saytda imtihondan keyin chiqadigan "
             "«Botni ochish» tugmasini bosing.\n\n")
          + f"Imtihon jadvali saytda: {site_url('/jadval/')}")


def _help(acc):
    lines = [
        "<b>Yordam</b>\n",
        f"{MENU_BOOK} — bo'sh kunlardan birini tanlab navbat oling. Saytda hisob shart emas.",
        f"{MENU_MY} — yozilgan kunlaringiz, navbatni bekor qilish.",
        f"{MENU_RESULTS} — saytdagi hisobingizni ulang: natijalar va PDF varaqa shu yerga keladi.",
        f"{MENU_SUPPORT} — savol, taklif yoki muammo; admin javobi shu chatga keladi.",
        "🧮 Ball kalkulyatori — to'g'ri javoblar sonini yuboring (masalan <code>32</code>), "
        "Listening/Reading bandini aytamiz.",
        "\nBuyruqlar: /start, /yozilish, /navbat, /natijalar, /hisob, /ball 32, /cancel",
        f"\n🌐 Sayt: {site_url('/')}\n🗓 Jadval: {site_url('/jadval/')}",
    ]
    if is_admin(acc):
        lines.append(f"\n<b>Xodimlar uchun:</b> {MENU_ADMIN} — statistika, navbat ro'yxati, kelganlarni "
                     "belgilash, hammaga xabar yuborish, adminlarni boshqarish.")
    reply(acc, '\n'.join(lines))


def _band(acc, text=''):
    arg = text.split(maxsplit=1)[1] if ' ' in text else ''
    if not arg.isdigit() or not 0 <= int(arg) <= 40:
        return reply(acc, "To'g'ri javoblar sonini 0–40 oralig'ida yozing, masalan: <code>/ball 32</code>")
    band = calc_band(int(arg), 40)
    reply(acc, f"🧮 40 tadan <b>{arg}</b> ta to'g'ri → band <b>{band:.1f}</b>\n"
               "(Listening va Academic Reading uchun taxminiy jadval)")


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
    reply(acc, text, markup)


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
    reply(acc, text, markup)


def _results(acc):
    if not acc.user:
        return _ask_link(acc)
    graded = list(UserResult.objects.graded().filter(user=acc.user).select_related('exam')
                  .order_by('-completed_at')[:5])
    pending = UserResult.objects.pending().filter(user=acc.user).count()
    if not graded and not pending:
        return reply(acc, "Hali natijalaringiz yo'q. Imtihon topshirganingizdan so'ng shu yerda ko'rinadi.")
    blocks = []
    for i, r in enumerate(graded, 1):
        parts = [f"{n} {s:.1f}" for n, s in (('L', r.listening_score), ('R', r.reading_score),
                                             ('W', r.writing_score), ('S', r.speaking_score)) if s]
        blocks.append(f"{i}. 📝 {escape(r.exam.title)}\n"
                      f"   Umumiy: <b>{r.score:.1f}</b>" + (f"  ({' · '.join(parts)})" if parts else '')
                      + f"\n   {timezone.localtime(r.completed_at):%d.%m.%Y}")
    text = "<b>So'nggi natijalaringiz</b>\n\n" + '\n\n'.join(blocks)
    if pending:
        text += f"\n\n⏳ {pending} ta natija tekshirilmoqda (Writing). Chiqqanda xabar beramiz."
    if graded:
        text += "\n\n📄 PDF varaqani olish uchun natija raqamini bosing."
    pdf_buttons = [(f"📄 {i}. PDF ({r.score:.1f})", f'pdf:{r.pk}') for i, r in enumerate(graded, 1)]
    rows = [pdf_buttons[i:i + 3] for i in range(0, len(pdf_buttons), 3)]
    rows.append([("Barcha natijalar", site_url('/results-list/'))])
    reply(acc, text, api.inline_keyboard(rows))


def _send_pdf(acc, cq, result_id):
    from exams.pdf import result_pdf
    result = UserResult.objects.select_related('user', 'exam').filter(pk=result_id).first()
    if not result or result.is_pending or not (result.user_id == acc.user_id or is_admin(acc)):
        return api.answer_callback(cq['id'], "Natija topilmadi", alert=True)
    api.answer_callback(cq['id'], "PDF tayyorlanmoqda…")
    api.call('sendChatAction', chat_id=acc.chat_id, action='upload_document')
    api.send_document(acc.chat_id, f'AbExam-natija-{result.pk}.pdf', result_pdf(result),
                      caption=f"📄 «{escape(result.exam.title)}» — umumiy ball <b>{result.score:.1f}</b>")


def _account_info(acc):
    if not acc.user:
        return _ask_link(acc)
    u = acc.user
    stats = UserResult.objects.graded().filter(user=u).aggregate(n=Count('id'), avg=Avg('score'))
    balance = f"{u.balance:,.0f}".replace(',', ' ')
    reply(acc,
          f"👤 <b>{escape(u.display_name)}</b> (@{escape(u.username)})\n"
          f"📞 {escape(u.phone_number or '—')}\n"
          f"💰 Balans: {balance} so'm\n"
          f"📊 Imtihonlar: {stats['n']}" + (f", o'rtacha ball {stats['avg']:.1f}" if stats['avg'] else ''),
          api.inline_keyboard([[("🌐 Saytga o'tish", site_url('/dashboard/'))],
                               [("🔌 Hisobni botdan uzish", 'unlink')]]))


def _support(acc):
    set_state(acc, 'support')
    reply(acc, "✉️ Savol, taklif yoki muammoingizni yozing (rasm ham yuborishingiz mumkin).\n"
               "Admin javobi shu chatga keladi.", keyboard([CANCEL]))


def _support_message(acc, msg):
    # One message per 20 s, so nobody floods the staff chat.
    if not cache.add(f'tg_support:{acc.pk}', 1, 20):
        return reply(acc, "Biroz kuting va qayta yuboring.", keyboard([CANCEL]))
    set_state(acc)
    admin_bot.forward_question(acc, msg)
    reply(acc, "✅ Xabaringiz adminga yuborildi. Javob shu yerga keladi.")


def _admin_menu(acc):
    if not is_admin(acc):
        return reply(acc, "Quyidagi menyudan tanlang 👇")
    admin_bot.menu(acc)


_MENU_ACTIONS = {
    MENU_BOOK: _show_days, MENU_MY: _my_bookings, MENU_RESULTS: _results,
    MENU_ACCOUNT: _account_info, MENU_SUPPORT: _support, MENU_HELP: _help, MENU_ADMIN: _admin_menu,
}
_COMMANDS = {
    '/menu': _welcome, '/help': _help, '/navbat': _my_bookings, '/yozilish': _show_days,
    '/natijalar': _results, '/hisob': _account_info, '/savol': _support, '/ball': _band,
    '/admin': _admin_menu,
}
_TAKES_TEXT = {_band}


# ── Linking a site account ────────────────────────────────────────────────────

def _ask_link(acc):
    reply(acc,
          "Natijalarni ko'rish uchun saytdagi hisobingizni ulang:\n\n"
          "1️⃣ Pastdagi «📱 Raqamni yuborish» tugmasini bosing — saytda shu raqam bilan "
          "ro'yxatdan o'tgan bo'lsangiz, hisob darhol ulanadi.\n"
          f"2️⃣ Yoki saytda Profil → «Telegramni ulash» tugmasini bosing: {site_url('/profile/')}",
          keyboard([CANCEL], contact='📱 Raqamni yuborish'))


def _link(acc, user):
    TelegramAccount.objects.filter(user=user).exclude(pk=acc.pk).update(user=None)
    acc.user = user
    acc.save(update_fields=['user'])
    reply(acc, f"✅ Hisob ulandi: <b>{escape(user.display_name)}</b>\n\n"
               "🔔 Endi imtihon natijalaringiz chiqishi bilan shu yerga avtomatik keladi — "
               "botni o'chirib qo'ymang.")
    notify_admins(f"🔗 <b>Hisob ulandi</b>\n{escape(who(acc))}", admin_bot.member_markup(acc))
    _recent_results(acc)


def _recent_results(acc):
    """Right after linking — usually straight from the «exam finished»
    screen: the newest result if it's fresh, and what's still being graded."""
    latest = (UserResult.objects.graded().filter(user=acc.user, completed_at__gte=timezone.now() - timedelta(days=3))
              .select_related('exam').order_by('-completed_at').first())
    if latest:
        reply(acc, *result_message(latest))
    for r in UserResult.objects.pending().filter(user=acc.user).select_related('exam'):
        reply(acc, f"⏳ «{escape(r.exam.title)}» — Writing qismingiz tekshirilmoqda.\n"
                   "Natija chiqishi bilan shu yerga yuboramiz.")


def _link_by_token(acc, token):
    user_id = cache.get(link_token_key(token))
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if not user:
        return reply(acc, "Havola eskirgan. Saytda Profil → «Telegramni ulash» tugmasini qayta bosing.")
    cache.delete(link_token_key(token))
    _link(acc, user)


def _link_by_contact(acc, msg):
    contact = msg['contact']
    # Telegram vouches for the number only when it's the sender's own contact.
    if contact.get('user_id') != msg.get('from', {}).get('id'):
        return reply(acc, "Iltimos, o'zingizning raqamingizni tugma orqali yuboring.")
    phone = normalize_phone(contact.get('phone_number', ''))
    user = User.objects.filter(phone_number=phone, is_active=True).first() if phone else None
    if not user:
        return reply(acc, f"Bu raqam ({escape(phone or '?')}) bilan saytda hisob topilmadi.\n"
                          f"Ro'yxatdan o'ting: {site_url('/register/')}")
    _link(acc, user)


# ── Booking dialogue ──────────────────────────────────────────────────────────

def _start_booking(acc, day_id):
    day = ExamDay.objects.filter(pk=day_id).first()
    if not day or not day.accepts_bookings():
        return reply(acc, "Bu kunga yozilish yopilgan yoki joy qolmagan. Boshqa kunni tanlang.")
    existing = day.active_bookings().filter(account=acc).first()
    if existing:
        return reply(acc, f"Siz bu kunga allaqachon yozilgansiz.\n\n{booking_text(existing)}")
    name = acc.full_name or (acc.user.get_full_name() if acc.user else '')
    phone = acc.phone or (acc.user.phone_number if acc.user else '') or ''
    if name and phone:
        set_state(acc, 'confirm', day=day.pk, name=name, phone=phone, center=acc.center)
        return _send_confirm(acc)
    set_state(acc, 'ask_name', day=day.pk)
    reply(acc, f"{day_details(day)}\n\n✍️ Ism va familiyangizni yozing:", keyboard([CANCEL]))


def _booking_step(acc, msg, text):
    data = acc.state_data
    if acc.state == 'ask_name':
        if not 3 <= len(text) <= 150 or text.startswith('/'):
            return reply(acc, "Ism va familiyani to'liq yozing (masalan: Aliyev Vali).", keyboard([CANCEL]))
        set_state(acc, 'ask_phone', **data, name=text)
        return reply(acc, "📞 Telefon raqamingizni yuboring yoki yozing (+998901234567):",
                     keyboard([CANCEL], contact='📱 Raqamni yuborish'))
    if acc.state == 'ask_phone':
        phone = normalize_phone(msg['contact']['phone_number'] if msg.get('contact') else text)
        if not phone:
            return reply(acc, "Raqam noto'g'ri. Masalan: +998901234567",
                         keyboard([CANCEL], contact='📱 Raqamni yuborish'))
        set_state(acc, 'ask_center', **data, phone=phone)
        return reply(acc, "🏫 Qaysi o'quv markazda o'qiysiz? Markaz nomini yozing:",
                     keyboard([SELF_STUDY], [CANCEL]))
    if acc.state == 'ask_center':
        if len(text) > 150 or not text:
            return reply(acc, "Markaz nomini qisqaroq yozing.", keyboard([SELF_STUDY], [CANCEL]))
        set_state(acc, 'confirm', **data, center='' if text == SELF_STUDY else text)
        return _send_confirm(acc)


def _send_confirm(acc):
    data = acc.state_data
    day = ExamDay.objects.filter(pk=data['day']).first()
    if not day:
        set_state(acc)
        return reply(acc, "Bu imtihon kuni topilmadi.")
    text = (f"<b>Ma'lumotlarni tekshiring</b>\n\n{day_details(day)}\n\n"
            f"👤 {escape(data['name'])}\n📞 {escape(data['phone'])}\n"
            f"🏫 {escape(data.get('center') or 'Mustaqil')}")
    reply(acc, text, api.inline_keyboard([
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
        set_state(acc)
        api.answer_callback(cq['id'], str(e), alert=True)
        return api.edit(acc.chat_id, cq['message']['message_id'], f"❌ {escape(str(e))}")
    acc.full_name, acc.phone, acc.center = data['name'], data['phone'], data.get('center', '')
    acc.save(update_fields=['full_name', 'phone', 'center'])
    set_state(acc)
    api.answer_callback(cq['id'], 'Navbatga yozildingiz!')
    api.edit(acc.chat_id, cq['message']['message_id'],
             f"✅ <b>Siz navbatga yozildingiz!</b>\n\n{booking_text(booking)}\n\n"
             "Imtihondan bir kun oldin eslatma yuboramiz.")
    reply(acc, "Navbatlaringizni «🎫 Navbatlarim» bo'limida ko'rasiz.")
    left = booking.day.seats_left()
    notify_admins(f"🎫 <b>Yangi navbat</b> (bot)\n{booking_text(booking)}\n"
                  f"💬 {escape(who(acc))}\n🪑 Qolgan joy: {left}", booking_admin_markup(booking))


# ── Inline buttons ────────────────────────────────────────────────────────────

def _on_callback(acc, cq):
    data = cq.get('data', '')
    message_id = cq['message']['message_id']

    if data.startswith('book:') and data[5:].isdigit():
        api.answer_callback(cq['id'])
        return _start_booking(acc, int(data[5:]))
    if data.startswith('pdf:') and data[4:].isdigit():
        return _send_pdf(acc, cq, int(data[4:]))
    if data == 'bok':
        return _confirm_booking(acc, cq)
    if data == 'bedit':
        day_id = acc.state_data.get('day')
        api.answer_callback(cq['id'])
        if not day_id:
            return None
        api.edit(acc.chat_id, message_id, "✏️ Ma'lumotlarni qayta kiritamiz.")
        set_state(acc, 'ask_name', day=day_id)
        return reply(acc, "✍️ Ism va familiyangizni yozing:", keyboard([CANCEL]))
    if data == 'bcancel':
        set_state(acc)
        api.answer_callback(cq['id'])
        api.edit(acc.chat_id, message_id, "Yozilish bekor qilindi.")
        return reply(acc, "Asosiy menyu 👇")
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
        return notify_admins(f"🚫 <b>Navbat bekor qilindi</b> (o'quvchi o'zi)\n{booking_text(booking)}")
    if data == 'support':
        api.answer_callback(cq['id'])
        return _support(acc)
    if data == 'unlink':
        acc.user = None
        acc.save(update_fields=['user'])
        api.answer_callback(cq['id'], "Hisob uzildi")
        return api.edit(acc.chat_id, message_id, "🔌 Sayt hisobi botdan uzildi.")
    api.answer_callback(cq['id'])
