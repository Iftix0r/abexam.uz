"""Menu buttons and small helpers shared by the student and admin handlers."""
from . import api
from .models import TelegramAccount
from .services import is_admin

MENU_BOOK = '📅 Imtihonga yozilish'
MENU_MY = '🎫 Navbatlarim'
MENU_RESULTS = '📊 Natijalarim'
MENU_ACCOUNT = '👤 Hisobim'
MENU_SUPPORT = '✉️ Adminga yozish'
MENU_HELP = 'ℹ️ Yordam'
MENU_ADMIN = '🛠 Admin panel'
CANCEL = '❌ Bekor qilish'


def main_menu(acc):
    rows = [[MENU_BOOK, MENU_MY], [MENU_RESULTS, MENU_ACCOUNT], [MENU_SUPPORT, MENU_HELP]]
    if is_admin(acc):
        rows.append([MENU_ADMIN])
    return {'keyboard': rows, 'resize_keyboard': True}


def keyboard(*rows, contact=None):
    rows = [list(r) for r in rows]
    if contact:
        rows.insert(0, [{'text': contact, 'request_contact': True}])
    return {'keyboard': rows, 'resize_keyboard': True, 'one_time_keyboard': True}


def set_state(acc, state='', **data):
    acc.state = state
    acc.state_data = data
    acc.save(update_fields=['state', 'state_data'])


def reply(acc, text, markup=None):
    if not api.send(acc.chat_id, text, markup or main_menu(acc)):
        TelegramAccount.objects.filter(pk=acc.pk).update(is_blocked=True)


def who(acc):
    """«Vali (@vali) · sayt: @vali_99» — how admins see a chat."""
    name = acc.full_name or acc.first_name or str(acc.chat_id)
    parts = [name + (f' (@{acc.username})' if acc.username else '')]
    if acc.user_id:
        parts.append(f'sayt: @{acc.user.username}')
    return ' · '.join(parts)
