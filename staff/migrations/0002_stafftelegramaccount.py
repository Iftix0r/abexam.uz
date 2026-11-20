import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('staff', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='StaffTelegramAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chat_id', models.BigIntegerField(unique=True)),
                ('username', models.CharField(blank=True, max_length=64)),
                ('first_name', models.CharField(blank=True, max_length=128)),
                ('is_blocked', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                              related_name='staff_telegram', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
