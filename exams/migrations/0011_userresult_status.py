from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('exams', '0010_exam_is_reviewed'),
    ]

    operations = [
        migrations.AddField(
            model_name='userresult',
            name='status',
            field=models.CharField(choices=[('pending', 'Tekshirilmoqda'), ('graded', 'Baholangan')], db_index=True, default='graded', max_length=10),
        ),
        migrations.AddField(
            model_name='userresult',
            name='graded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='graded_results', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='userresult',
            name='graded_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
