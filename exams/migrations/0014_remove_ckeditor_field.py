from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('exams', '0013_exam_attempt_live_fields')]

    operations = [
        migrations.AlterField(
            model_name='section',
            name='content',
            field=models.TextField(blank=True, null=True),
        ),
    ]
