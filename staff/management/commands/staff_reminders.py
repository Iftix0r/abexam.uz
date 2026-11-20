from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from staff.models import DailyReport, Meeting, StaffProfile, Task
from staff.services import notify_profiles, notify_user


class Command(BaseCommand):
    help = 'Staff bot orqali vazifa, yig‘ilish va kunlik hisobot eslatmalarini yuboradi.'

    def add_arguments(self, parser):
        parser.add_argument('kind', choices=['morning', 'evening', 'deadlines', 'meetings'])

    def handle(self, *args, **options):
        kind, sent = options['kind'], 0
        now, today = timezone.now(), timezone.localdate()
        if kind == 'morning':
            for profile in StaffProfile.objects.filter(is_approved=True).select_related('user', 'user__staff_telegram'):
                count = Task.objects.filter(assignee=profile, due_at__date=today).exclude(
                    status__in=[Task.Status.DONE, Task.Status.CANCELLED]).count()
                if count:
                    sent += int(notify_user(profile.user, '☀️ Bugungi ish rejangiz',
                                            f'Bugun {count} ta faol vazifangiz bor.', '/staff/tasks/?period=today'))
        elif kind == 'evening':
            profiles = StaffProfile.objects.filter(is_approved=True).exclude(daily_reports__date=today)
            sent = notify_profiles(profiles, '✅ Kunlik hisobot vaqti',
                                   'Bugungi bajargan ishlaringiz va ertangi rejangizni yuboring.', '/staff/report/')
        elif kind == 'deadlines':
            tasks = Task.objects.filter(due_at__range=(now, now + timedelta(hours=24))).exclude(
                status__in=[Task.Status.DONE, Task.Status.CANCELLED])
            for task in tasks.select_related('assignee__user'):
                sent += int(notify_user(task.assignee.user, '⏰ Vazifa muddati yaqin',
                                        f'{task.title}\nMuddat: {task.due_at:%d.%m %H:%M}', f'/staff/tasks/{task.pk}/'))
        else:
            meetings = Meeting.objects.filter(starts_at__range=(now, now + timedelta(hours=2)), reminder_sent_at__isnull=True)
            for meeting in meetings:
                sent += notify_profiles(meeting.participants.filter(is_approved=True), '📅 Yig‘ilish eslatmasi',
                                        f'{meeting.title}\n{meeting.starts_at:%H:%M} · {meeting.location}', '/staff/meetings/')
                meeting.reminder_sent_at = now; meeting.save(update_fields=['reminder_sent_at'])
        self.stdout.write(self.style.SUCCESS(f'{sent} ta eslatma yuborildi.'))
