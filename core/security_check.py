"""The panel's security checklist: settings and accounts that make the site
easier to break into, each with what to do about it."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

OK, WARN, BAD = 'ok', 'warn', 'bad'
DORMANT_STAFF_DAYS = 90
GUESSABLE_LOGINS = ('admin', 'administrator', 'root', 'test', 'user', 'superadmin')


def _item(title, status, detail, fix=''):
    return {'title': title, 'status': status, 'detail': detail, 'fix': fix if status != OK else ''}


def run_checks():
    from core.models import CanaryToken, SecurityIncident
    from core.system_views import _backups_dir
    from users.models import User

    now = timezone.now()
    items = []

    items.append(_item('Debug rejimi o\'chiq', BAD if settings.DEBUG else OK,
                       "DEBUG yoqilgan: xato sahifalari kod va sozlamalarni ko'rsatadi." if settings.DEBUG
                       else "Xato sahifalari ichki ma'lumotni ko'rsatmaydi.",
                       ".env faylida DEBUG=False qiling."))

    https = all([getattr(settings, 'SECURE_SSL_REDIRECT', False), getattr(settings, 'SESSION_COOKIE_SECURE', False),
                 getattr(settings, 'CSRF_COOKIE_SECURE', False), getattr(settings, 'SECURE_HSTS_SECONDS', 0) > 0])
    items.append(_item('HTTPS majburiy', OK if https else BAD,
                       "Barcha ulanishlar shifrlangan, cookie'lar faqat HTTPS orqali yuboriladi." if https
                       else "Sayt HTTP orqali ham ochiladi yoki cookie'lar shifrsiz yuborilishi mumkin.",
                       "DEBUG=False qiling: production sozlamalari HTTPS ni majburiy qiladi."))

    key = settings.SECRET_KEY or ''
    strong_key = len(key) >= 50 and len(set(key)) >= 10 and not key.startswith('django-insecure')
    items.append(_item('SECRET_KEY kuchli', OK if strong_key else BAD,
                       "Kalit uzun va tasodifiy." if strong_key else "Kalit qisqa yoki standart: sessiyalarni soxtalashtirish oson.",
                       "Yangi kalit yarating (python -c \"import secrets; print(secrets.token_urlsafe(64))\") "
                       "va .env dagi SECRET_KEY ga qo'ying. Hamma qayta kirishi kerak bo'ladi."))

    hosts_ok = '*' not in settings.ALLOWED_HOSTS
    items.append(_item('Domenlar cheklangan', OK if hosts_ok else WARN,
                       "Sayt faqat o'z domenlariga javob beradi." if hosts_ok else "ALLOWED_HOSTS='*': har qanday domen nomi qabul qilinadi.",
                       ".env dagi ALLOWED_HOSTS ga faqat abexam.uz,www.abexam.uz yozing."))

    validators = len(getattr(settings, 'AUTH_PASSWORD_VALIDATORS', []))
    items.append(_item('Parol talablari', OK if validators >= 3 else WARN,
                       f'{validators} ta parol tekshiruvi yoqilgan.',
                       "AUTH_PASSWORD_VALIDATORS ga uzunlik va oddiy parol tekshiruvlarini qo'shing."))

    supers = list(User.objects.filter(is_superuser=True, is_active=True).values_list('username', flat=True))
    items.append(_item('Superadminlar soni', OK if len(supers) <= 2 else WARN,
                       f"{len(supers)} ta superadmin: {', '.join(supers)}",
                       "Superadmin hamma narsani o'zgartira oladi. Kerak bo'lmaganlarini oddiy admin qiling."))

    guessable = list(User.objects.filter(is_staff=True, is_active=True, username__in=GUESSABLE_LOGINS)
                     .values_list('username', flat=True))
    items.append(_item('Admin loginlari taxmin qilinmaydi', WARN if guessable else OK,
                       f"Oson topiladigan admin login: {', '.join(guessable)}" if guessable
                       else "Hech bir admin «admin», «root» kabi login ishlatmaydi.",
                       "Bunday login hujumchilar birinchi sinaydigan narsa. Admin loginini o'zgartiring."))

    dormant = list(User.objects.filter(is_staff=True, is_active=True)
                   .filter(Q(last_login__lt=now - timedelta(days=DORMANT_STAFF_DAYS)) | Q(last_login__isnull=True))
                   .values_list('username', flat=True))
    items.append(_item("Ishlatilmayotgan admin hisoblari", WARN if dormant else OK,
                       f"{DORMANT_STAFF_DAYS} kundan beri kirmagan: {', '.join(dormant)}" if dormant
                       else f"Barcha adminlar oxirgi {DORMANT_STAFF_DAYS} kunda kirgan.",
                       "Ishlamay qolgan xodimning admin huquqini olib tashlang: unutilgan hisob oson nishon."))

    telegram = bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ADMIN_CHAT_ID)
    items.append(_item('Telegram ogohlantirishlari', OK if telegram else WARN,
                       "Yuqori xavfli hodisalar darhol Telegramga keladi." if telegram
                       else "Hujum haqida Telegramga xabar kelmaydi, faqat panelda ko'rinadi.",
                       ".env ga TELEGRAM_BOT_TOKEN va TELEGRAM_ADMIN_CHAT_ID ni qo'shing."))

    turnstile = bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)
    items.append(_item('Shubhali loginlarda Turnstile', OK if turnstile else WARN,
                       "Botga o'xshash loginlarda server tekshiradigan CAPTCHA ishlaydi." if turnstile
                       else "Turnstile kalitlari yo'q: shubhali loginlarda CAPTCHA chiqmaydi.",
                       ".env ga TURNSTILE_SITE_KEY va TURNSTILE_SECRET_KEY ni qo'shing."))

    hidden_webhook = getattr(settings, 'TELEGRAM_HIDDEN_WEBHOOK_ONLY', False)
    items.append(_item('Eski Telegram webhook yopiq', OK if hidden_webhook else WARN,
                       "Faqat maxfiy webhook manzili ishlaydi." if hidden_webhook
                       else "Eski /tg/webhook/ manzili hali ochiq; o'tish tugagach uni yoping.",
                       ".env ga TELEGRAM_HIDDEN_WEBHOOK_ONLY=True qo'shib ilovani qayta yuklang."))

    staff_binding = getattr(settings, 'STAFF_SESSION_BINDING', False)
    items.append(_item('Admin sessiyasi qurilmaga bog‘langan', OK if staff_binding else WARN,
                       "Admin cookie o'g'irlansa, boshqa tarmoq yoki brauzerda bekor qilinadi." if staff_binding
                       else "Admin sessiyasi boshqa qurilmada qayta ishlatilishi mumkin.",
                       ".env ga STAFF_SESSION_BINDING=True qo'shing."))

    backups = sorted((f for f in _backups_dir().iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime)
    if backups:
        age = (now.timestamp() - backups[-1].stat().st_mtime) / 86400
        status = OK if age <= 7 else WARN if age <= 30 else BAD
        detail = f"Oxirgi zaxira {int(age)} kun oldin olingan."
    else:
        status, detail = BAD, "Hali birorta zaxira nusxa yo'q."
    items.append(_item('Zaxira nusxa', status, detail,
                       "Tizim → Zaxira nusxalar bo'limida zaxira oling. Hujum yoki xatodan keyin faqat shu qutqaradi."))

    used = list(CanaryToken.objects.filter(hits__gt=0).values_list('kind', flat=True))
    items.append(_item('Canary tokenlar tegilmagan', BAD if used else OK,
                       "Tuzoq qiymatlari ishlatilgan: baza yoki zaxira o'g'irlangan bo'lishi mumkin." if used
                       else "Hech kim admin_passwords tuzog'idagi qiymatlarni ishlatmagan.",
                       "Baza va hosting parollarini, SECRET_KEY va API kalitlarni almashtiring."))

    high = SecurityIncident.objects.filter(kind__in=SecurityIncident.kinds_of('high'),
                                           last_seen__gte=now - timedelta(hours=24)).count()
    items.append(_item("So'nggi 24 soatda yuqori xavf", WARN if high else OK,
                       f"{high} ta yuqori xavfli hodisa bo'lgan." if high else "Yuqori xavfli hodisa bo'lmagan.",
                       "Bildirishnomalar → Xavfsizlik bo'limida ko'rib chiqing, kerak bo'lsa IP ni bloklang."))

    passed = sum(1 for i in items if i['status'] == OK)
    return {'items': items, 'score': round(passed / len(items) * 100), 'passed': passed, 'total': len(items)}
