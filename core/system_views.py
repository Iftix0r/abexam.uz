"""Superuser-only ops panel at /system/ — health status, backups, logs and
a couple of quick actions (cache clear, maintenance toggle). Separate from
/panel/ (teachers/staff, is_staff) on purpose: nothing here is meant for
day-to-day exam/content management, only for whoever is technically
responsible for the deployment."""
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import django
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

_BACKUP_NAME_RE = re.compile(r'^[\w.-]+\.(json\.gz|tar\.gz)$')
_LOG_TAIL_LINES = 300


def is_superuser(user):
    return user.is_authenticated and user.is_superuser


def system_required(view_func):
    return login_required(user_passes_test(is_superuser, login_url='/login/')(view_func))


def _backups_dir():
    d = Path(settings.BASE_DIR) / 'backups'
    d.mkdir(exist_ok=True)
    return d


def _safe_backup_path(filename):
    """Rejects anything that isn't a plain filename we generated ourselves —
    blocks path traversal (../) since these paths are user-supplied via URL."""
    if not _BACKUP_NAME_RE.match(filename):
        raise Http404
    path = _backups_dir() / filename
    if path.parent != _backups_dir():
        raise Http404
    if not path.is_file():
        raise Http404
    return path


def _git_commit():
    try:
        out = subprocess.run(
            ['git', 'log', '-1', '--format=%h %cd %s', '--date=short'],
            cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=3,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


@system_required
def dashboard(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            db_ok = True
    except Exception:
        db_ok = False

    disk = shutil.disk_usage(settings.BASE_DIR)

    from .models import SiteSettings
    context = {
        'django_version': django.get_version(),
        'python_version': sys.version.split()[0],
        'debug': settings.DEBUG,
        'db_vendor': connection.vendor,
        'db_ok': db_ok,
        'disk_free_gb': round(disk.free / (1024 ** 3), 1),
        'disk_total_gb': round(disk.total / (1024 ** 3), 1),
        'disk_used_pct': round(disk.used / disk.total * 100),
        'maintenance_mode': SiteSettings.get().maintenance_mode,
        'git_commit': _git_commit(),
        'backup_count': sum(1 for f in _backups_dir().iterdir() if f.is_file()),
    }
    return render(request, 'system/dashboard.html', context)


@system_required
@require_POST
def toggle_maintenance(request):
    from .models import SiteSettings
    s = SiteSettings.get()
    s.maintenance_mode = not s.maintenance_mode
    s.save()
    messages.success(request, "Texnik xizmat rejimi " + ("yoqildi." if s.maintenance_mode else "o'chirildi."))
    return redirect('system:dashboard')


@system_required
@require_POST
def cache_clear(request):
    cache.clear()
    messages.success(request, "Kesh tozalandi.")
    return redirect('system:dashboard')


@system_required
def backups(request):
    items = []
    for f in sorted(_backups_dir().iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file() and f.name != 'cron.log':
            items.append({
                'name': f.name,
                'size_kb': f.stat().st_size // 1024,
                'mtime': datetime.fromtimestamp(f.stat().st_mtime),
                'kind': 'Baza' if f.name.startswith('db_') else 'Media',
            })
    return render(request, 'system/backups.html', {'backups': items})


@system_required
@require_POST
def backup_run(request):
    try:
        call_command('backup_data')
        messages.success(request, "Zaxira nusxa muvaffaqiyatli olindi.")
    except Exception as e:
        messages.error(request, f"Zaxira olishda xato: {e}")
    return redirect('system:backups')


@system_required
def backup_download(request, filename):
    path = _safe_backup_path(filename)
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=filename)


@system_required
@require_POST
def backup_delete(request, filename):
    path = _safe_backup_path(filename)
    path.unlink()
    messages.success(request, f"{filename} o'chirildi.")
    return redirect('system:backups')


@system_required
def logs(request):
    log_path = _backups_dir() / 'cron.log'
    content = ''
    if log_path.is_file():
        with open(log_path, 'r', errors='replace') as f:
            lines = f.readlines()
        content = ''.join(lines[-_LOG_TAIL_LINES:])
    return render(request, 'system/logs.html', {
        'content': content, 'log_exists': log_path.is_file(),
    })
