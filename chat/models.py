from django.conf import settings
from django.db import models
from django.utils import timezone


class ChatRoom(models.Model):
    """A shared room. There are no private chats: every message is on view,
    which is what keeps a space with young students moderatable."""
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=60)
    description = models.CharField(max_length=150, blank=True)
    icon = models.CharField(max_length=30, default='message-circle', help_text='static/icons.css dagi ikonka nomi')
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'pk']
        verbose_name = 'Xona'
        verbose_name_plural = 'Xonalar'

    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
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
