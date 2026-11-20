import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('staff', '0002_stafftelegramaccount')]
    operations = [
        migrations.CreateModel(
            name='Attendance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(default=django.utils.timezone.localdate)),
                ('check_in', models.DateTimeField(blank=True, null=True)),
                ('check_out', models.DateTimeField(blank=True, null=True)),
                ('late_reason', models.CharField(blank=True, max_length=300)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='attendance', to='staff.staffprofile')),
            ],
            options={'ordering': ['-date', 'employee__user__first_name']},
        ),
        migrations.AddConstraint(model_name='attendance',
                                 constraint=models.UniqueConstraint(fields=('employee', 'date'),
                                                                    name='unique_staff_attendance')),
    ]
