import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('staff', '0005_meetings_kpi_knowledge_onboarding')]
    operations = [
        migrations.CreateModel(name='Goal', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.CharField(max_length=200)), ('description', models.TextField(blank=True)),
            ('target_date', models.DateField()), ('progress', models.PositiveSmallIntegerField(default=0)),
            ('status', models.CharField(choices=[('planned', 'Rejada'), ('active', 'Jarayonda'),
                ('achieved', 'Erishildi'), ('paused', 'To‘xtatilgan')], default='planned', max_length=15)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_goals', to='staff.staffprofile')),
            ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='goals', to='staff.department')),
            ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='goals', to='staff.staffprofile')),
            ('tasks', models.ManyToManyField(blank=True, related_name='goals', to='staff.task')),
        ], options={'ordering': ['status', 'target_date']}),
    ]
