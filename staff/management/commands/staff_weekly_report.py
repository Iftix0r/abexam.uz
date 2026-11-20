from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from staff.models import Attendance, DailyReport, LeaveRequest, StaffProfile, Task
from staff.services import notify_group, notify_profiles


class Command(BaseCommand):
    help = 'Rahbariyatga haftalik AB Staff hisobotini yuboradi.'

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=7)
        done = Task.objects.filter(completed_at__gte=since).count()
        late = Task.objects.exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).filter(due_at__lt=timezone.now()).count()
        reports = DailyReport.objects.filter(date__gte=since.date()).count()
        attendance = Attendance.objects.filter(date__gte=since.date(), check_in__isnull=False).count()
        leaves = LeaveRequest.objects.filter(created_at__gte=since).count()
        text = (f'✅ Bajarilgan vazifalar: {done}\n🔴 Kechikkan vazifalar: {late}\n'
                f'📝 Kunlik hisobotlar: {reports}\n🕘 Davomat yozuvlari: {attendance}\n🏖 Ruxsat so‘rovlari: {leaves}')
        leaders = StaffProfile.objects.filter(is_approved=True, role__in=[StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.COORDINATOR])
        sent = notify_profiles(leaders, '📊 Haftalik AB Staff hisoboti', text)
        notify_group('📊 Haftalik umumiy natijalar', text)
        self.stdout.write(self.style.SUCCESS(f'Hisobot {sent} rahbarga yuborildi.'))
