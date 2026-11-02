from django.conf import settings
from django.db import models
from django.utils import timezone


class TelegramAccount(models.Model):
    """A chat with the bot. Linked to a site user once they share their
    phone number or open the link from their profile; students from other
    learning centres book exams without ever having a site account."""
    chat_id = models.BigIntegerField(unique=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='telegram')
    username = models.CharField(max_length=64, blank=True)
    first_name = models.CharField(max_length=128, blank=True)
    # Filled in on the first booking and offered again on the next one.
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    center = models.CharField(max_length=150, blank=True)
    # Where the user is in a multi-step dialogue (the webhook is stateless).
    state = models.CharField(max_length=30, blank=True)
    state_data = models.JSONField(default=dict, blank=True)
    is_blocked = models.BooleanField(default=False, help_text='Botni bloklagan — xabar yuborilmaydi')
    # Set by an admin: the bot ignores this chat (spam in «Adminga yozish»).
    is_banned = models.BooleanField(default=False, help_text='Admin bloklagan — bot javob bermaydi')
    # Bot-only admin (stats, queue, broadcasts, replies) — gives no access to
    # the site panel. Site staff who link their account are admins anyway.
    is_admin = models.BooleanField(default=False, help_text="Bot admini — saytdagi panelga kirish huquqi bermaydi")
    alerts_off = models.BooleanField(default=False, help_text="Admin xabarnomalarini o'chirib qo'ygan")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Telegram foydalanuvchi'
        verbose_name_plural = 'Telegram foydalanuvchilar'

    def __str__(self):
        return f'@{self.username}' if self.username else (self.first_name or str(self.chat_id))


class ExamDayQuerySet(models.QuerySet):
    def upcoming(self):
        return self.filter(date__gte=timezone.localdate())

    def with_booked(self):
        return self.annotate(booked=models.Count('bookings', filter=~models.Q(bookings__status=Booking.STATUS_CANCELLED)))


class ExamDay(models.Model):
    """A day the centre holds an exam; students queue up for it in the bot
    and the public /jadval/ page shows how full each day is."""
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    title = models.CharField(max_length=150, default='IELTS Mock imtihon')
    capacity = models.PositiveIntegerField(default=30)
    location = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True, help_text="Narx, nima olib kelish kerak va h.k.")
    is_open = models.BooleanField(default=True, help_text="Yopilsa yangi yozilish qabul qilinmaydi")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ExamDayQuerySet.as_manager()

    class Meta:
        ordering = ['date', 'start_time']
        verbose_name = 'Imtihon kuni'
        verbose_name_plural = 'Imtihon kunlari'

    def __str__(self):
        return f"{self.date:%d.%m.%Y} {self.start_time:%H:%M} — {self.title}"

    def active_bookings(self):
        return self.bookings.exclude(status=Booking.STATUS_CANCELLED)

    def booked_count(self):
        booked = getattr(self, 'booked', None)
        return booked if booked is not None else self.active_bookings().count()

    def seats_left(self):
        return max(0, self.capacity - self.booked_count())

    def fill_pct(self):
        return min(100, round(self.booked_count() / self.capacity * 100)) if self.capacity else 100

    def accepts_bookings(self):
        return self.is_open and self.date >= timezone.localdate() and self.seats_left() > 0


class Booking(models.Model):
    STATUS_BOOKED = 'booked'
    STATUS_CAME = 'came'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = (
        (STATUS_BOOKED, 'Navbatda'),
        (STATUS_CAME, 'Keldi'),
        (STATUS_CANCELLED, 'Bekor qilingan'),
    )
    day = models.ForeignKey(ExamDay, on_delete=models.CASCADE, related_name='bookings')
    # Empty for a booking staff added in the panel (phone call, walk-in).
    account = models.ForeignKey(TelegramAccount, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='bookings')
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    center = models.CharField(max_length=150, blank=True, help_text="O'quv markaz nomi")
    # Order of signing up for the day; never reused after a cancellation.
    queue_number = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_BOOKED, db_index=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['day', 'queue_number']
        verbose_name = 'Navbat'
        verbose_name_plural = 'Navbatlar'

    def __str__(self):
        return f"#{self.queue_number} {self.full_name} — {self.day}"
