import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('staff', '0004_staff_positions_and_departments')]
    operations = [
        migrations.CreateModel(name='Meeting', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.CharField(max_length=200)), ('starts_at', models.DateTimeField(db_index=True)),
            ('location', models.CharField(max_length=200)), ('agenda', models.TextField(blank=True)),
            ('decisions', models.TextField(blank=True)), ('reminder_sent_at', models.DateTimeField(blank=True, null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('organizer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='organized_meetings', to='staff.staffprofile')),
            ('participants', models.ManyToManyField(related_name='meetings', to='staff.staffprofile')),
        ], options={'ordering': ['starts_at']}),
        migrations.CreateModel(name='KPIRecord', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('period', models.DateField(help_text='Hisobot oyining birinchi kuni')), ('metric', models.CharField(max_length=150)),
            ('target', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
            ('actual', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
            ('note', models.CharField(blank=True, max_length=300)), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_kpis', to='staff.staffprofile')),
            ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kpi_records', to='staff.staffprofile')),
        ], options={'ordering': ['-period', 'employee__user__first_name', 'metric']}),
        migrations.CreateModel(name='KnowledgeDocument', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.CharField(max_length=200)), ('description', models.TextField(blank=True)),
            ('file', models.FileField(blank=True, upload_to='staff/knowledge/%Y/%m/')), ('link', models.URLField(blank=True)),
            ('is_required', models.BooleanField(default=False)), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='staff.department')),
            ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='knowledge_documents', to='staff.staffprofile')),
        ], options={'ordering': ['-created_at']}),
        migrations.CreateModel(name='OnboardingItem', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.CharField(max_length=200)), ('description', models.TextField(blank=True)),
            ('due_date', models.DateField(blank=True, null=True)), ('is_done', models.BooleanField(default=False)),
            ('completed_at', models.DateTimeField(blank=True, null=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_onboarding_items', to='staff.staffprofile')),
            ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='onboarding_items', to='staff.staffprofile')),
        ], options={'ordering': ['is_done', 'due_date', 'id']}),
    ]
