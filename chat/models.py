from django.conf import settings
from django.db import models
from django.utils import timezone


class ChatRoom(models.Model):
    """A shared room, open to every signed-in student."""
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=60)
    description = models.CharField(max_length=150, blank=True)
    icon = models.CharField(max_length=30, default='message-circle', help_text='static/icons.css dagi ikonka nomi')
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    pinned = models.ForeignKey('ChatMessage', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['order', 'pk']
        verbose_name = 'Xona'
        verbose_name_plural = 'Xonalar'

    def __str__(self):
        return self.title


class ChatThread(models.Model):
    """A private chat of two students. It starts as a request: the sender gets
    one message until the other side accepts, as in Instagram. A refused sender
    is not told, the thread just stays pending for them."""
    REQUEST, ACCEPTED, DECLINED = 'request', 'accepted', 'declined'
    STATUS_CHOICES = ((REQUEST, "So'rov"), (ACCEPTED, 'Qabul qilingan'), (DECLINED, 'Rad etilgan'))

    # user_a always has the smaller pk, so a pair can only have one thread.
    user_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    user_b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=REQUEST)
    last_message = models.ForeignKey('ChatMessage', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    a_read = models.BigIntegerField(default=0)
    b_read = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user_a', 'user_b'], name='chat_thread_pair')]
        ordering = ['-updated_at']
        verbose_name = 'Lichka'
        verbose_name_plural = 'Lichkalar'

    def has(self, user):
        return user.pk in (self.user_a_id, self.user_b_id)

    def other(self, user):
        return self.user_b if user.pk == self.user_a_id else self.user_a

    def read_id(self, user):
        return self.a_read if user.pk == self.user_a_id else self.b_read

    def is_hidden_from(self, user):
        """A refused request disappears for whoever refused it."""
        return self.status == self.DECLINED and user.pk != self.requested_by_id


class ChatMessage(models.Model):
    # Exactly one of room / thread is set.
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_messages')
    text = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    # Soft delete, so moderators can still see what a report was about.
    # deleted_by empty on a deleted message means reports hid it automatically.
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')

    class Meta:
        verbose_name = 'Xabar'
        verbose_name_plural = 'Xabarlar'

    def __str__(self):
        return f'{self.user}: {self.text[:40]}'


class ChatReport(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['message', 'reporter'], name='chat_report_once')]
        verbose_name = 'Shikoyat'
        verbose_name_plural = 'Shikoyatlar'


class ChatMute(models.Model):
    """A muted student can still read, but not write, until `until`."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_mute')
    until = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chat bloki'
        verbose_name_plural = 'Chat bloklari'

    @property
    def active(self):
        return self.until > timezone.now()


class ChatReaction(models.Model):
    KINDS = ('like', 'heart', 'flame', 'party')

    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    kind = models.CharField(max_length=10)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['message', 'user'], name='chat_reaction_once')]


class ChatPresence(models.Model):
    """Who has opened a room (its members) and when they last had it open."""
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='presence')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    last_seen = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['room', 'user'], name='chat_presence_once')]


class ChatBlock(models.Model):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['blocker', 'blocked'], name='chat_block_once')]
