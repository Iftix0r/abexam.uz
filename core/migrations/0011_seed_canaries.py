import secrets

from django.db import migrations


def seed(apps, schema_editor):
    """Random on every install, so the bait can't be known in advance."""
    CanaryToken = apps.get_model('core', 'CanaryToken')
    DecoyAdminPassword = apps.get_model('core', 'DecoyAdminPassword')
    if CanaryToken.objects.exists():
        return
    login = f'superadmin_backup_{secrets.token_hex(2)}'
    api_key = f'ak_live_{secrets.token_urlsafe(24)}'
    CanaryToken.objects.create(kind='login', value=login)
    CanaryToken.objects.create(kind='api_key', value=api_key)
    DecoyAdminPassword.objects.create(username=login, password=secrets.token_urlsafe(12), api_key=api_key,
                                      note='Zaxira superadmin hisobi')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_canarytoken_decoy'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
