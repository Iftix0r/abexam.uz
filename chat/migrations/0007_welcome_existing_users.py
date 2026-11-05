from django.conf import settings
from django.db import migrations


def greet(apps, schema_editor):
    """Every student already on the site gets the AB Admin greeting too."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    SupportThread = apps.get_model('chat', 'SupportThread')
    ChatMessage = apps.get_model('chat', 'ChatMessage')
    sender = User.objects.filter(is_superuser=True).order_by('pk').first()
    if sender is None:
        return
    for user in User.objects.filter(is_staff=False, is_active=True).iterator():
        thread, _ = SupportThread.objects.get_or_create(user=user)
        if ChatMessage.objects.filter(support=thread).exists():
            continue
        name = user.first_name.strip()
        greeting = f'Salom, {name}!' if name else 'Salom!'
        message = ChatMessage.objects.create(
            support=thread, user=sender, is_auto=True,
            text=f"{greeting} AbExam'ga xush kelibsiz. Men AB Admin. Qanday yordam bera olaman?")
        SupportThread.objects.filter(pk=thread.pk).update(last_message=message, staff_read=message.pk)


class Migration(migrations.Migration):
    dependencies = [
        ('chat', '0006_chatmessage_is_auto'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.RunPython(greet, migrations.RunPython.noop)]
