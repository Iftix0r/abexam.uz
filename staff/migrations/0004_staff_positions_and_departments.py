from django.db import migrations, models


DEPARTMENTS = [
    'Administratsiya',
    'Ingliz tili o‘qituvchilari',
    'Koreys tili o‘qituvchilari',
    'IT va dasturlash',
    'Marketing va SMM',
    'Video va kontent',
    'Moliya va buxgalteriya',
    'Boshqaruv',
]


def seed_departments(apps, schema_editor):
    Department = apps.get_model('staff', 'Department')
    for name in DEPARTMENTS:
        Department.objects.get_or_create(name=name, defaults={'is_active': True})


class Migration(migrations.Migration):
    dependencies = [('staff', '0003_attendance')]
    operations = [
        migrations.AddField(
            model_name='staffprofile', name='position',
            field=models.CharField(choices=[('director', 'Direktor'), ('coordinator', 'Koordinator'),
                ('department_head', 'Bo‘lim boshlig‘i'), ('administrator', 'Administrator'),
                ('english_teacher', 'Ingliz tili o‘qituvchisi'), ('korean_teacher', 'Koreys tili o‘qituvchisi'),
                ('it_teacher', 'IT va dasturlash o‘qituvchisi'), ('targetologist', 'Targetolog'),
                ('marketer', 'Marketolog'), ('smm', 'SMM mutaxassisi'), ('content', 'Kontent yaratuvchi'),
                ('videographer', 'Videograf'), ('accountant', 'Buxgalter'), ('hr', 'HR / Kadrlar'),
                ('technical', 'Texnik xodim'), ('other', 'Boshqa')], db_index=True, default='other', max_length=30),
        ),
        migrations.RunPython(seed_departments, migrations.RunPython.noop),
    ]
