from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from staff.models import Department, Goal, StaffProfile


GOALS = [
    {
        'title': 'Yangi o‘quvchilar qabulini 20% oshirish',
        'description': 'Sinov darsiga yozilgan murojaatlarni tezkor qayta ishlash va kursga qabul konversiyasini yaxshilash.',
        'department': 'Administratsiya', 'positions': ['administrator', 'coordinator'], 'days': 60, 'progress': 15,
    },
    {
        'title': 'O‘quvchilar davomati 90% dan yuqori bo‘lishi',
        'description': 'Sababsiz dars qoldirishlarni kamaytirish, ota-onalar bilan aloqa va haftalik davomat tahlili.',
        'department': 'Ingliz tili o‘qituvchilari', 'positions': ['department_head', 'english_teacher'], 'days': 45, 'progress': 30,
    },
    {
        'title': 'IELTS natijalarini o‘rtacha 0.5 bandga oshirish',
        'description': 'Mock test tahlili, individual xatolar rejasi va qo‘shimcha speaking/reading mashg‘ulotlari.',
        'department': 'Ingliz tili o‘qituvchilari', 'positions': ['english_teacher', 'department_head'], 'days': 90, 'progress': 10,
    },
    {
        'title': 'Koreys tili guruhlarida o‘zlashtirishni yaxshilash',
        'description': 'Oylik nazorat, uy vazifasi intizomi va past natijali o‘quvchilar bilan individual ishlash.',
        'department': 'Koreys tili o‘qituvchilari', 'positions': ['korean_teacher', 'department_head'], 'days': 75, 'progress': 20,
    },
    {
        'title': 'Oy davomida 120 ta sifatli lid olish',
        'description': 'Maqsadli auditoriya segmentlari, reklama kreativlari va kampaniyalar bo‘yicha haftalik optimizatsiya.',
        'department': 'Marketing va SMM', 'positions': ['targetologist', 'marketer'], 'days': 30, 'progress': 25,
    },
    {
        'title': 'Haftasiga 5 ta foydali kontent chiqarish',
        'description': 'Reels, o‘quvchi natijasi, foydali maslahat va markaz hayotidan kontentlarni reja asosida tayyorlash.',
        'department': 'Video va kontent', 'positions': ['smm', 'content', 'videographer'], 'days': 30, 'progress': 40,
    },
    {
        'title': 'IT kurslari uchun amaliy loyiha tizimini joriy qilish',
        'description': 'Har bir modul yakunida portfolio loyihasi va mentor tekshiruv mezonlarini ishlab chiqish.',
        'department': 'IT va dasturlash', 'positions': ['it_teacher', 'department_head'], 'days': 60, 'progress': 5,
    },
    {
        'title': 'Barcha bo‘limlarda haftalik hisobot intizomini 100% qilish',
        'description': 'Vazifalar, davomat, KPI va muammolar bo‘yicha haftalik rahbariyat ko‘rib chiqishini yo‘lga qo‘yish.',
        'department': 'Boshqaruv', 'positions': ['director', 'coordinator'], 'days': 30, 'progress': 35,
    },
]


class Command(BaseCommand):
    help = 'AB Education uchun realistik demo maqsadlarni xavfsiz yaratadi.'

    def handle(self, *args, **options):
        creator = StaffProfile.objects.filter(user__is_superuser=True).first()
        if not creator:
            creator = StaffProfile.objects.filter(role=StaffProfile.Role.SUPER_ADMIN).first()
        if not creator:
            raise CommandError('Avval Super Admin Staff profilini yarating yoki /staff/ sahifasiga kiring.')

        created = skipped = 0
        today = timezone.localdate()
        for data in GOALS:
            department, _ = Department.objects.get_or_create(name=data['department'])
            owner = (StaffProfile.objects.filter(is_approved=True, department=department,
                                                 position__in=data['positions']).first()
                     or StaffProfile.objects.filter(is_approved=True, department=department).first()
                     or creator)
            _, was_created = Goal.objects.get_or_create(
                title=data['title'],
                defaults={
                    'description': data['description'], 'owner': owner, 'department': department,
                    'target_date': today + timedelta(days=data['days']), 'progress': data['progress'],
                    'status': Goal.Status.ACTIVE, 'created_by': creator,
                },
            )
            created += int(was_created)
            skipped += int(not was_created)
        self.stdout.write(self.style.SUCCESS(f'{created} ta demo maqsad yaratildi, {skipped} ta avval mavjud.'))
