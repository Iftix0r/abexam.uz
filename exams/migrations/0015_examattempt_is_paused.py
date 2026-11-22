from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0014_remove_ckeditor_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='examattempt',
            name='is_paused',
            field=models.BooleanField(default=False, help_text="Nazoratchi urinishni vaqtincha to'xtatgan"),
        ),
    ]
