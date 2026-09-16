"""
Ma'lumotlar bazasi (barcha jadvallar) va media fayllardan (audio, rasm)
zaxira nusxa oladi. JSON-fixture formatidan foydalanadi, shuning uchun
joriy DB SQLite bo'lsa ham, PostgreSQL bo'lsa ham bir xil ishlaydi.

Kunlik cron orqali ishga tushirish uchun mo'ljallangan:
    python manage.py backup_data

Tiklash uchun:
    gunzip -c backups/db_20260101_030000.json.gz | python manage.py loaddata --format=json -
"""
import gzip
import io
import tarfile
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.utils import record_task_run

EXCLUDED_MODELS = ['contenttypes', 'auth.permission', 'sessions.session', 'admin.logentry']


class Command(BaseCommand):
    help = "Bazadan va media papkasidan zaxira nusxa oladi (backups/ ichiga), eskilarini tozalaydi."

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-days', type=int, default=14,
            help="Necha kunlik zaxiralarni saqlash — eskisi avtomatik o'chiriladi (standart: 14)",
        )

    def handle(self, *args, **options):
        start = time.monotonic()
        try:
            note = self._run(options)
        except Exception as e:
            record_task_run('backup_data', False, time.monotonic() - start, note=str(e))
            raise
        record_task_run('backup_data', True, time.monotonic() - start, note=note)

    def _run(self, options):
        backups_dir = Path(settings.BASE_DIR) / 'backups'
        backups_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        db_path = backups_dir / f'db_{stamp}.json.gz'
        buf = io.StringIO()
        call_command(
            'dumpdata',
            use_natural_foreign_keys=True,
            use_natural_primary_keys=True,
            exclude=EXCLUDED_MODELS,
            indent=2,
            stdout=buf,
        )
        with gzip.open(db_path, 'wt', encoding='utf-8') as f:
            f.write(buf.getvalue())
        self.stdout.write(self.style.SUCCESS(
            f'Baza zaxirasi: {db_path.name} ({db_path.stat().st_size // 1024} KB)'
        ))
        note = f'{db_path.name} ({db_path.stat().st_size // 1024} KB)'

        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists() and any(media_root.iterdir()):
            media_path = backups_dir / f'media_{stamp}.tar.gz'
            with tarfile.open(media_path, 'w:gz') as tar:
                tar.add(media_root, arcname='media')
            self.stdout.write(self.style.SUCCESS(
                f'Media zaxirasi: {media_path.name} ({media_path.stat().st_size // 1024} KB)'
            ))
            note += f', {media_path.name} ({media_path.stat().st_size // 1024} KB)'

        keep_days = options['keep_days']
        cutoff = datetime.now().timestamp() - keep_days * 86400
        removed = 0
        for f in backups_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        if removed:
            self.stdout.write(f"{removed} ta {keep_days} kundan eski zaxira o'chirildi.")
            note += f', {removed} ta eski o\'chirildi'
        return note
