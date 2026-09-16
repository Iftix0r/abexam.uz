"""Superuser-only ops panel at /system/ — backups, cache, and basic health
info. Separate from /panel/ (teachers/staff, is_staff) on purpose: nothing
here is meant for day-to-day exam/content management, only for whoever is
technically responsible for the deployment."""
import re
import shutil
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

_BACKUP_NAME_RE = re.compile(r'^[\w.-]+\.(json\.gz|tar\.gz|log)$')


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


@system_required
def dashboard(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            db_ok = True
    except Exception:
        db_ok = False

    disk = shutil.disk_usage(settings.BASE_DIR)

    backups = []
    for f in sorted(_backups_dir().iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file() and f.name != 'cron.log':
            backups.append({
                'name': f.name,
                'size_kb': f.stat().st_size // 1024,
                'mtime': datetime.fromtimestamp(f.stat().st_mtime),
            })

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
        'backups': backups,
        'maintenance_mode': SiteSettings.get().maintenance_mode,
    }
    return render(request, 'system/dashboard.html', context)


@system_required
@require_POST
def backup_run(request):
    try:
        call_command('backup_data')
        messages.success(request, "Zaxira nusxa muvaffaqiyatli olindi.")
    except Exception as e:
        messages.error(request, f"Zaxira olishda xato: {e}")
    return redirect('system:dashboard')


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
    return redirect('system:dashboard')


@system_required
@require_POST
def cache_clear(request):
    cache.clear()
    messages.success(request, "Kesh tozalandi.")
    return redirect('system:dashboard')
