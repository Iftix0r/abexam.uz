"""Panel tools for working with many students at once: importing a class
list from a spreadsheet and messaging a chosen set of students."""
import csv
import io
import secrets

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from chat import services as chat_services
from core.audit import log_action
from core.utils import parse_json_body
from users.backends import is_uz_mobile, normalize_phone, phone_variants
from users.forms import _free_username
from users.models import StudyGroup, User

from .views import _filtered_users, panel_required

MAX_IMPORT_ROWS = 500
MAX_MESSAGE_RECIPIENTS = 1000
MAX_UPLOAD_BYTES = 512 * 1024
# No 0/o, 1/l/i: the password is read off a printed list and typed on a phone.
_PASSWORD_LETTERS = 'abcdefghjkmnpqrstuvwxyz'
_PASSWORD_DIGITS = '23456789'
_HEADER_WORDS = {'ism', 'familiya', 'telefon', 'tel', 'raqam', 'name', 'phone', 'f.i.sh', 'fish', 'имя', 'телефон'}


def make_password():
    """Easy to read aloud and type: four letters, four digits (e.g. kmrt4827)."""
    return (''.join(secrets.choice(_PASSWORD_LETTERS) for _ in range(4))
            + ''.join(secrets.choice(_PASSWORD_DIGITS) for _ in range(4)))


def _decode(raw):
    for encoding in ('utf-8-sig', 'cp1251'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _split_line(line):
    # Excel saves CSV with ';' where the decimal mark is a comma (Uzbek and
    # Russian Windows); a list pasted straight from a sheet is tab-separated.
    delimiter = '\t' if '\t' in line else ';' if ';' in line else ','
    return [cell.strip() for cell in next(csv.reader([line], delimiter=delimiter), [])]


def parse_student_list(text):
    """Rows of the pasted or uploaded list, each with a status:
    'new' (an account will be made), 'exists' (the phone already has an
    account, which is only added to the group) or 'error' (skipped, with why).

    Each line is a name and a phone number in any order of cells:
    "Ism; Familiya; Telefon" or "Ism Familiya, Telefon". A header line is
    skipped."""
    rows, seen = [], {}
    lines = [line for line in text.splitlines() if line.strip()]
    for number, line in enumerate(lines, 1):
        cells = [c for c in _split_line(line) if c]
        phone_cells = [c for c in cells if normalize_phone(c)]
        # A "№" column (1, 2, 3…) is not a name.
        names = [c for c in cells if c not in phone_cells and not c.rstrip('.').isdigit()]
        if number == 1 and not phone_cells and _HEADER_WORDS.intersection(line.lower().replace(';', ' ').replace(',', ' ').split()):
            continue
        row = {'line': number, 'source': line.strip()[:200], 'first_name': '', 'last_name': '',
               'phone': '', 'status': 'error', 'error': '', 'user': None}
        rows.append(row)
        if len(rows) > MAX_IMPORT_ROWS:
            row['error'] = f"Bir martada ko'pi bilan {MAX_IMPORT_ROWS} ta qator"
            continue
        if len(names) == 1:
            names = names[0].split(None, 1)
        row['first_name'] = (names[0] if names else '')[:150]
        row['last_name'] = (names[1] if len(names) > 1 else '')[:150]
        if not phone_cells:
            row['error'] = 'Telefon raqam topilmadi'
            continue
        phone = normalize_phone(phone_cells[-1])
        row['phone'] = phone
        if not is_uz_mobile(phone):
            row['error'] = "O'zbekiston mobil raqami emas"
        elif not row['first_name']:
            row['error'] = 'Ism yozilmagan'
        elif phone in seen:
            row['error'] = f"Raqam {seen[phone]}-qatorda ham bor"
        else:
            seen[phone] = number
            row['user'] = User.objects.filter(phone_number__in=phone_variants(phone)).first()
            row['status'] = 'exists' if row['user'] else 'new'
    return rows


def _group_from(value):
    return StudyGroup.objects.filter(pk=value).first() if str(value or '').isdigit() else None


@panel_required
def users_import(request):
    """Paste or upload a class list → check it → make the accounts. The
    passwords are shown once, on the page that follows; they're never stored."""
    groups = StudyGroup.objects.all()
    if request.method != 'POST':
        return render(request, 'panel/users_import.html', {'groups': groups, 'group': _group_from(request.GET.get('group'))})

    text = request.POST.get('text', '')
    upload = request.FILES.get('file')
    if upload:
        if upload.size > MAX_UPLOAD_BYTES:
            messages.error(request, 'Fayl juda katta (512 KB gacha).')
            return redirect('panel:users_import')
        text = _decode(upload.read())
    group = _group_from(request.POST.get('group'))
    rows = parse_student_list(text)
    counts = {status: sum(1 for r in rows if r['status'] == status) for status in ('new', 'exists', 'error')}
    if not rows:
        messages.error(request, "Ro'yxat bo'sh.")
        return redirect('panel:users_import')

    if request.POST.get('step') != 'create':
        return render(request, 'panel/users_import.html', {
            'groups': groups, 'rows': rows, 'counts': counts, 'text': text, 'group': group,
        })

    created = []
    with transaction.atomic():
        for row in rows:
            if row['status'] == 'new':
                user = User(username=_free_username(row['phone'].lstrip('+')), phone_number=row['phone'],
                            first_name=row['first_name'], last_name=row['last_name'])
                row['password'] = make_password()
                user.set_password(row['password'])
                user.save()
                row['user'] = user
                created.append(row)
        if group:
            group.members.add(*[r['user'] for r in rows if r['user']])
    added = counts['new'] + counts['exists'] if group else 0
    log_action(request, 'user_import', f'{len(created)} ta talaba',
               reverse('panel:group_detail', args=[group.pk]) if group else reverse('panel:users'),
               f"Yaratildi: {len(created)}, mavjud: {counts['exists']}, xato: {counts['error']}"
               + (f', guruh: {group.name}' if group else ''))
    return render(request, 'panel/users_import_done.html', {
        'created': created, 'counts': counts, 'group': group, 'added': added,
        'login_url': request.build_absolute_uri(reverse('login')),
    })


@panel_required
@require_POST
def users_message(request):
    """Message the ticked students, or everyone matching the list's filters.
    Each gets it in their AB Admin chat, and in Telegram when the bot is linked."""
    data, err = parse_json_body(request)
    if err:
        return err
    text = str(data.get('text') or '').strip()[:1000]
    if not text:
        return JsonResponse({'ok': False, 'error': 'Xabar matnini yozing'})
    if data.get('all_filtered'):
        students = _filtered_users(request, QueryDict(str(data.get('query') or '').lstrip('?')))
    else:
        students = User.objects.filter(pk__in=[i for i in data.get('ids') or [] if str(i).isdigit()])
    students = students.filter(is_active=True, is_staff=False)
    total = students.count()
    if not total:
        return JsonResponse({'ok': False, 'error': "Xabar oladigan talaba yo'q (adminlar va bloklanganlar kirmaydi)"})
    if total > MAX_MESSAGE_RECIPIENTS:
        return JsonResponse({'ok': False, 'error': f"Bir martada {MAX_MESSAGE_RECIPIENTS} tagacha talabaga yuboriladi. "
                                                   f"Filtrni toraytiring ({total} ta)."})
    for student in students:
        chat_services.message_from_admin(student, request.user, text)
    log_action(request, 'user_message', f'{total} ta talaba', reverse('panel:users'), f'Xabar: {text[:200]}')
    return JsonResponse({'ok': True, 'count': total})
