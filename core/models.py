from datetime import timedelta

from django.core.cache import cache
from django.db import models
from django.conf import settings
from django.utils import timezone


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=100, default='AbExam.uz')
    site_description = models.TextField(blank=True, default='IELTS Mock platformasi')
    announcement = models.TextField(blank=True, help_text='Sayt yuqorisida ko\'rinadigan e\'lon')
    announcement_active = models.BooleanField(default=False)
    maintenance_mode = models.BooleanField(default=False)
    maintenance_message = models.TextField(blank=True, default='Sayt texnik ishlar uchun vaqtincha to\'xtatilgan.')
    logo = models.ImageField(upload_to='site/', null=True, blank=True)
    # Exam page beeps and flashes red when the student leaves the test window
    # or pastes into Writing, so invigilators in the room notice.
    proctor_alarm = models.BooleanField(default=True)
    # Starting an exam needs its hourly password (exams/passwords.py), which
    # the invigilator reads in the panel and tells the students in the room.
    exam_password_required = models.BooleanField(default=True)
    # The exam page needs the webcam on and sends frames staff watch live
    # (exams/camera.py); the site asks for camera permission on entry.
    camera_proctoring = models.BooleanField(default=True)
    # Admin Telegram chat gets pinged when work is waiting: a payment to
    # approve, a Writing to grade, a question whose answer key looks wrong.
    telegram_work_alerts = models.BooleanField(default=True)
    premium_price = models.DecimalField(max_digits=10, decimal_places=2, default=99000)
    premium_days = models.PositiveIntegerField(default=30)
    chat_dm_enabled = models.BooleanField(default=True, help_text="AbChat'da talabalar lichkaga yoza oladi")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sayt sozlamalari'

    def __str__(self):
        return self.site_name

    _CACHE_KEY = 'site_settings_singleton'

    @classmethod
    def get(cls):
        # Read on every request (maintenance-mode middleware + the
        # announcement/notification context processor), so cache it rather
        # than hitting the DB twice per request site-wide.
        obj = cache.get(cls._CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls._CACHE_KEY, obj, 300)
        return obj

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.set(self._CACHE_KEY, self, 300)


class Notification(models.Model):
    TYPE_CHOICES = (
        ('info', 'Ma\'lumot'),
        ('success', 'Muvaffaqiyat'),
        ('warning', 'Ogohlantirish'),
        ('danger', 'Xato'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='notifications', null=True, blank=True,
                             help_text='Bo\'sh qoldirilsa — barcha foydalanuvchilarga')
    title = models.CharField(max_length=200)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Xabar'
        verbose_name_plural = 'Xabarlar'

    def __str__(self):
        return self.title


class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percent = models.IntegerField(default=0, help_text='0-100 oralig\'ida')
    max_uses = models.IntegerField(default=1)
    used_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Promo kod'
        verbose_name_plural = 'Promo kodlar'

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.used_count >= self.max_uses:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class StaffAlert(models.Model):
    """Something on the site staff may want to know about, for the panel's
    notifications page. `user` is who it is about: deleting that account
    deletes these too, since the text carries their name and phone."""
    LABELS = {
        'signup': 'Yangi talabalar', 'login': 'Kirishlar', 'payment': "To'lovlar", 'exam': 'Imtihonlar',
        'support': 'Xabarlar', 'report': 'Shikoyatlar', 'security': 'Xavfsizlik',
    }
    ICONS = {
        'signup': 'lc-user', 'login': 'lc-key-round', 'payment': 'lc-credit-card', 'exam': 'lc-pen-line',
        'support': 'lc-message-circle', 'report': 'lc-flag', 'security': 'lc-shield-check',
    }
    COLORS = {
        'signup': '#16a34a', 'login': '#6366f1', 'payment': '#ca8a04', 'exam': '#3b82f6',
        'support': '#0ea5e9', 'report': '#f97316', 'security': '#dc2626',
    }
    QUIET = ('login',)  # listed, but too frequent to count as unread
    UNREAD_DAYS = 30

    kind = models.CharField(max_length=20, choices=list(LABELS.items()), db_index=True)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=300, blank=True)
    url = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Xodimlar bildirishnomasi'
        verbose_name_plural = 'Xodimlar bildirishnomalari'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.title

    @property
    def icon(self):
        return self.ICONS[self.kind]

    @property
    def color(self):
        return self.COLORS[self.kind]

    @classmethod
    def unread_for(cls, staff):
        since = timezone.now() - timedelta(days=cls.UNREAD_DAYS)
        return cls.objects.exclude(kind__in=cls.QUIET).exclude(read_by=staff).filter(created_at__gte=since)


class SecurityIncident(models.Model):
    """One kind of attack from one IP, with repeats inside an hour counted in `hits`."""
    KINDS = {
        'scan': ('Zaiflik qidiruvi', 'medium',
                 "Avtomatik skaner saytda ochiq fayllar va ma'lum zaif sahifalarni qidirmoqda (.env, wp-admin, .php).",
                 "Odatda xavfsiz: bunday sahifalar saytda yo'q. Urinishlar ko'paysa, IP ni hosting firewall'ida bloklang."),
        'sql_injection': ('SQL injection urinishi', 'high',
                          "Manzilga ma'lumotlar bazasini aldash uchun SQL buyrug'i qo'shilgan.",
                          "Sayt Django ORM ishlatadi, bu turdagi hujumdan himoyalangan. IP ni kuzating, ko'p takrorlansa bloklang."),
        'xss': ('XSS urinishi', 'high',
                "Manzilga brauzerda bajariladigan skript qo'shilgan. Maqsad boshqa foydalanuvchining sessiyasini o'g'irlash.",
                "Shablonlar matnni avtomatik xavfsiz qiladi. Agar bu havolani kimdir talabalarga yuborgan bo'lsa, ogohlantiring."),
        'traversal': ('Tizim fayllarini o\'qish urinishi', 'high',
                      "Server fayllarini (/etc/passwd kabi) ochishga urinish bo'ldi.",
                      "IP ni hosting firewall'ida bloklang va server loglarini ko'rib chiqing."),
        'code_exec': ('Serverda kod bajarish urinishi', 'high',
                      "Manzil orqali serverda buyruq yoki shablon kodi bajarishga urinish bo'ldi.",
                      "IP ni darhol bloklang, server loglarini va yaqinda o'zgargan fayllarni tekshiring."),
        'flood': ("So'rovlar oqimi (DoS)", 'high',
                  "Bitta IP daqiqasiga juda ko'p so'rov yubormoqda. Sayt sekinlashishi mumkin.",
                  "Sayt sekinlashgan bo'lsa, IP ni hosting firewall'ida bloklang. Internet-qidiruv boti bo'lishi ham mumkin."),
        'brute_force': ('Parol terish', 'high',
                        "Bitta hisobga ketma-ket noto'g'ri parol kiritildi va u vaqtincha bloklandi.",
                        "Bu IP sizning talabangizniki bo'lishi mumkin. Agar notanish bo'lsa, hisob egasiga parolni almashtirishni ayting."),
        'spray': ('Ko\'p hisoblarga parol sinash', 'high',
                  "Bitta IP dan ko'plab turli hisoblarga kirishga urinildi. Bu sizib chiqqan parollar ro'yxatini sinash belgisi.",
                  "IP ni bloklang. Shu IP dan kirib ketgan hisoblar bo'lsa, ularning parolini almashtiring."),
        'distributed': ('Bitta hisobga ko\'p IP dan hujum', 'high',
                        "Bir hisobga turli IP manzillardan parol sinalmoqda. Bu tashkillashtirilgan hujum belgisi.",
                        "Hisob egasini ogohlantiring va parolini almashtiring."),
        'staff_target': ('Admin hisobiga hujum', 'high',
                         "Admin hisobiga ketma-ket noto'g'ri parol kiritildi.",
                         "Bu o'zingiz bo'lmasangiz, shu admin parolini darhol almashtiring."),
        'breach': ('Hisob buzilgan bo\'lishi mumkin', 'high',
                   "Ko'p noto'g'ri urinishdan keyin hisobga muvaffaqiyatli kirildi. Parol topilgan bo'lishi mumkin.",
                   "Hisob egasi bilan bog'laning. U kirmagan bo'lsa, parolni darhol almashtiring."),
        'webhook': ('Soxta Telegram so\'rovi', 'medium',
                    "Kimdir Telegram botining manzilga maxfiy kalitsiz so'rov yubordi.",
                    "So'rov rad etildi. Ko'p takrorlansa, webhook kalitini yangilang."),
        'suspicious': ('Shubhali so\'rov', 'medium',
                       "Django so'rovni xavfli deb to'xtatdi.",
                       "So'rov rad etildi. Takrorlansa, IP ni kuzating."),
        'csrf': ('Qalbaki forma (CSRF)', 'low',
                 "Himoya kalitisiz forma yuborildi. Ko'pincha sahifa uzoq ochiq qolganda ham shunday bo'ladi.",
                 "So'rov rad etildi. Bir IP dan ko'p takrorlanmasa, e'tibor bermasa ham bo'ladi."),
        'bad_host': ('Noto\'g\'ri domen bilan so\'rov', 'low',
                     "Saytga boshqa domen nomi yoki to'g'ridan-to'g'ri IP orqali murojaat bo'ldi. Bu avtomatik botlarda ko'p uchraydi.",
                     "So'rov rad etildi. Hech narsa qilish shart emas."),
        'honeypot_visit': ('Tuzoq sahifa ochildi', 'medium',
                           "Hech qayerda ko'rsatilmagan soxta sahifa ochildi (/administrator/ yoki /backup/). "
                           "Oddiy foydalanuvchi u yerga bormaydi, bu bot yoki saytni o'rganayotgan odam.",
                           "Hozircha xavfsiz. Shu IP dan boshqa hodisalar ham bo'lsa, hosting firewall'ida bloklang."),
        'honeypot_login': ('Soxta admin sahifasiga login kiritildi', 'high',
                           "Kimdir soxta admin sahifasiga login va parol kiritdi. Bu ataylab kirishga urinish.",
                           "IP ni bloklang. Kiritilgan login sizning xodimingizniki bo'lsa, uning parolini almashtiring."),
        'canary': ('Canary token ishlatildi', 'high',
                   "Faqat admin_passwords tuzoq jadvalida turgan soxta login yoki API kalit ishlatildi. "
                   "Demak kimdir ma'lumotlar bazasini yoki uning zaxira nusxasini o'qigan.",
                   "Jiddiy holat. Bazaga va hostingga kirish parollarini, SECRET_KEY va API kalitlarni almashtiring, "
                   "zaxira nusxalar qayerda saqlanishini tekshiring."),
        'panel_probe': ('Talaba panelga kirishga urindi', 'low',
                        "Xodim bo'lmagan foydalanuvchi admin panel sahifasini ochdi va rad etildi.",
                        "Tasodif bo'lishi mumkin. Tez-tez takrorlansa, hisobni tekshiring."),
    }
    SEVERITY_LABELS = {'high': 'Yuqori', 'medium': "O'rta", 'low': 'Past'}
    BADGES = {'high': 'badge-red', 'medium': 'badge-yellow', 'low': 'badge-gray'}

    kind = models.CharField(max_length=20, choices=[(k, v[0]) for k, v in KINDS.items()], db_index=True)
    ip = models.GenericIPAddressField(db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    user_agent = models.CharField(max_length=300, blank=True)
    hits = models.PositiveIntegerField(default=1)
    samples = models.JSONField(default=list, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = 'Xavfsizlik hodisasi'
        verbose_name_plural = 'Xavfsizlik hodisalari'
        ordering = ['-last_seen', '-id']

    def __str__(self):
        return f'{self.label} — {self.ip}'

    @property
    def label(self):
        return self.KINDS[self.kind][0]

    @property
    def severity(self):
        return self.KINDS[self.kind][1]

    @property
    def what(self):
        return self.KINDS[self.kind][2]

    @property
    def advice(self):
        return self.KINDS[self.kind][3]

    @property
    def severity_label(self):
        return self.SEVERITY_LABELS[self.severity]

    @property
    def badge(self):
        return self.BADGES[self.severity]

    @classmethod
    def kinds_of(cls, severity):
        return [kind for kind, details in cls.KINDS.items() if details[1] == severity]


class BlockedIP(models.Model):
    """An IP or range staff shut out from the site. Signed-in staff still pass."""
    DURATIONS = (('1h', '1 soat', timedelta(hours=1)), ('24h', '24 soat', timedelta(hours=24)),
                 ('7d', '7 kun', timedelta(days=7)), ('30d', '30 kun', timedelta(days=30)),
                 ('forever', 'Muddatsiz', None))

    network = models.CharField(max_length=50, unique=True, help_text='203.0.113.7 yoki 203.0.113.0/24')
    reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    hits = models.PositiveIntegerField(default=0)
    last_hit_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Bloklangan IP'
        verbose_name_plural = 'Bloklangan IP lar'
        ordering = ['-created_at']

    def __str__(self):
        return self.network

    @property
    def is_active(self):
        return self.expires_at is None or self.expires_at > timezone.now()

    @classmethod
    def expiry(cls, code):
        length = next((d[2] for d in cls.DURATIONS if d[0] == code), timedelta(hours=24))
        return timezone.now() + length if length else None


class CanaryToken(models.Model):
    """A value no one should ever send. It is created once per install and
    also sits in the decoy `admin_passwords` table."""
    KINDS = (('login', 'Soxta admin login'), ('api_key', 'Soxta API kalit'))

    kind = models.CharField(max_length=10, choices=KINDS)
    value = models.CharField(max_length=100, unique=True)
    hits = models.PositiveIntegerField(default=0)
    last_hit_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Canary token'
        verbose_name_plural = 'Canary tokenlar'

    def __str__(self):
        return self.get_kind_display()


class DecoyAdminPassword(models.Model):
    """Bait for whoever reads the database: none of these credentials work,
    and using them raises a «canary» incident."""
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    api_key = models.CharField(max_length=100)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'admin_passwords'
        verbose_name = 'Tuzoq (admin_passwords)'
        verbose_name_plural = 'Tuzoq (admin_passwords)'

    def __str__(self):
        return self.username


class AuditLog(models.Model):
    """What a staff member did in the panel — balance changes, answer-key
    edits, grading, deletions — with who and when, for accountability."""
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    # Kept as text too, so the entry still reads right after the account is gone.
    staff_name = models.CharField(max_length=150)
    action = models.CharField(max_length=40, db_index=True)
    target = models.CharField(max_length=255, blank=True)
    target_url = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Xodim harakati'
        verbose_name_plural = 'Xodimlar harakatlari'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.staff_name}: {self.action} {self.target}"
