"""Superuser-only ops panel at /system/ — health status, backups, logs and
a couple of quick actions (cache clear, maintenance toggle). Separate from
/panel/ (teachers/staff, is_staff) on purpose: nothing here is meant for
day-to-day exam/content management, only for whoever is technically
responsible for the deployment."""
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import django
import psutil
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .utils import notify_admin_telegram, read_audit, read_task_history, record_audit

_BACKUP_NAME_RE = re.compile(r'^[\w.-]+\.(json\.gz|tar\.gz)$')
_LOG_TAIL_LINES = 300

# Never previewed or downloaded through the file browser — still listed
# (nothing is hidden from view), but content stays out of reach: these
# hold the DB password, SECRET_KEY, API keys and every user's password
# hash. A read-only browser is still a browser; this is the one thing it
# must never serve.
_SENSITIVE_FILES = {
    '.env', '.env.local', '.env.production',
    'db.sqlite3', 'db.sqlite3-wal', 'db.sqlite3-shm',
}
# Not sensitive, just noise/irrelevant to browse — skipped from listings.
_SKIP_ENTRIES = {'.git', '__pycache__', 'node_modules'}
_FILE_PREVIEW_MAX_BYTES = 500_000


def _can_access_system(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    # A logged-in, non-superuser account reaching for /system/ is worth
    # knowing about immediately — either a curious staff member or a
    # compromised account probing for admin tools.
    notify_admin_telegram(
        f"🚨 <b>Ruxsatsiz /system/ kirish urinishi</b>\n👤 {user.username}"
    )
    return False


def system_required(view_func):
    return login_required(user_passes_test(_can_access_system, login_url='/login/')(view_func))


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
        start = time.perf_counter()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        db_latency_ms = round((time.perf_counter() - start) * 1000, 1)
        db_ok = True
    except Exception:
        db_ok = False
        db_latency_ms = None

    disk = shutil.disk_usage(settings.BASE_DIR)
    mem = psutil.virtual_memory()
    # A short interval blocks briefly but gives a real reading instead of
    # the meaningless 0.0% psutil returns on a bare first call.
    cpu_pct = psutil.cpu_percent(interval=0.1)
    proc_rss = psutil.Process().memory_info().rss

    from .models import SiteSettings
    context = {
        'django_version': django.get_version(),
        'python_version': sys.version.split()[0],
        'debug': settings.DEBUG,
        'db_vendor': connection.vendor,
        'db_ok': db_ok,
        'db_latency_ms': db_latency_ms,
        'disk_free_gb': round(disk.free / (1024 ** 3), 1),
        'disk_total_gb': round(disk.total / (1024 ** 3), 1),
        'disk_used_pct': round(disk.used / disk.total * 100),
        'ram_used_gb': round(mem.used / (1024 ** 3), 1),
        'ram_total_gb': round(mem.total / (1024 ** 3), 1),
        'ram_used_pct': round(mem.percent),
        'cpu_pct': round(cpu_pct),
        'proc_rss': _human_size(proc_rss),
        'maintenance_mode': SiteSettings.get().maintenance_mode,
        'git_commit': _git_commit(),
        'backup_count': sum(1 for f in _backups_dir().iterdir() if f.is_file()),
        'sentry_enabled': bool(settings.SENTRY_DSN),
    }
    return render(request, 'system/dashboard.html', context)


@system_required
@require_POST
def toggle_maintenance(request):
    from .models import SiteSettings
    s = SiteSettings.get()
    s.maintenance_mode = not s.maintenance_mode
    s.save()
    state = "yoqildi" if s.maintenance_mode else "o'chirildi"
    record_audit(request.user.username, f"Texnik xizmat rejimini {state}")
    messages.success(request, f"Texnik xizmat rejimi {state}.")
    return redirect('system:dashboard')


@system_required
@require_POST
def cache_clear(request):
    cache.clear()
    record_audit(request.user.username, "Keshni tozaladi")
    messages.success(request, "Kesh tozalandi.")
    return redirect('system:dashboard')


@system_required
@require_POST
def app_restart(request):
    """Passenger (production host) watches this file's mtime and respawns
    the app worker on change — no process signal or sudo needed. Under
    runserver/gunicorn nothing is watching it, so it's a harmless no-op."""
    (Path(settings.BASE_DIR) / 'tmp').mkdir(exist_ok=True)
    (Path(settings.BASE_DIR) / 'tmp' / 'restart.txt').touch()
    record_audit(request.user.username, "Ilovani qayta ishga tushirdi")
    messages.success(request, "Qayta ishga tushirish so'raldi. Bir necha soniyada yangi so'rovlar yangi jarayonga tushadi.")
    return redirect('system:dashboard')


@system_required
@require_POST
def clear_temp(request):
    """Deletes only what's safe to lose without touching user content:
    __pycache__ (Python regenerates it) and expired DB sessions. Orphaned
    media/static files are deliberately left alone — telling "no longer
    referenced" from "still in use" needs a real reference scan, and
    guessing wrong here means deleting someone's uploaded file."""
    freed = 0
    removed_dirs = 0
    for pycache in Path(settings.BASE_DIR).rglob('__pycache__'):
        if '.venv-tmp' in pycache.parts or 'node_modules' in pycache.parts:
            continue
        for f in pycache.rglob('*'):
            if f.is_file():
                freed += f.stat().st_size
        shutil.rmtree(pycache, ignore_errors=True)
        removed_dirs += 1

    try:
        call_command('clearsessions')
        sessions_note = ''
    except Exception as e:
        sessions_note = f" (sessiyalarni tozalashda xato: {e})"

    record_audit(
        request.user.username, "Vaqtinchalik fayllarni tozaladi",
        detail=f"{removed_dirs} ta __pycache__, {_human_size(freed)}",
    )
    messages.success(
        request,
        f"{removed_dirs} ta __pycache__ papkasi ({_human_size(freed)}) va eskirgan sessiyalar tozalandi.{sessions_note}",
    )
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
        record_audit(request.user.username, "Zaxira nusxa oldi (qo'lda)")
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
    record_audit(request.user.username, "Zaxira nusxani o'chirdi", detail=filename)
    messages.success(request, f"{filename} o'chirildi.")
    return redirect('system:backups')


def _tail(path, n=_LOG_TAIL_LINES):
    if not path.is_file():
        return ''
    with open(path, 'r', errors='replace') as f:
        return ''.join(f.readlines()[-n:])


@system_required
def logs(request):
    cron_log = _backups_dir() / 'cron.log'
    slow_log = Path(settings.LOGS_DIR) / 'slow_queries.log'
    return render(request, 'system/logs.html', {
        'cron_content': _tail(cron_log),
        'cron_exists': cron_log.is_file(),
        'slow_content': _tail(slow_log),
        'slow_exists': slow_log.is_file(),
        'slow_threshold': settings.SLOW_QUERY_THRESHOLD,
    })


@system_required
def tasks(request):
    return render(request, 'system/tasks.html', {'runs': read_task_history()})


@system_required
def sentry_test(request):
    if not settings.SENTRY_DSN:
        messages.error(request, "SENTRY_DSN .env'da sozlanmagan — avval uni qo'shing.")
        return redirect('system:dashboard')
    1 / 0


@system_required
def audit(request):
    return render(request, 'system/audit.html', {'entries': read_audit()})


def _human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def _resolve_project_path(subpath):
    """Confines any path under settings.BASE_DIR — resolve() collapses
    '..' segments, and the parents check (rather than a naive startswith)
    avoids a sibling directory with a matching name-prefix slipping
    through (e.g. BASE_DIR=examab vs examab2)."""
    base = Path(settings.BASE_DIR).resolve()
    target = (base / subpath).resolve()
    if target != base and base not in target.parents:
        raise Http404
    if not target.exists():
        raise Http404
    return target, base


def _breadcrumbs(target, base):
    rel = target.relative_to(base)
    crumbs = [{'name': 'loyiha', 'path': ''}]
    parts = [] if rel == Path('.') else list(rel.parts)
    for i, part in enumerate(parts):
        crumbs.append({'name': part, 'path': '/'.join(parts[:i + 1])})
    return crumbs


@system_required
def files(request, subpath=''):
    target, base = _resolve_project_path(subpath)

    if target.is_dir():
        entries = []
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name in _SKIP_ENTRIES:
                continue
            rel = p.relative_to(base)
            stat = p.stat()
            entries.append({
                'name': p.name,
                'is_dir': p.is_dir(),
                'path': str(rel),
                'size': '' if p.is_dir() else _human_size(stat.st_size),
                'mtime': datetime.fromtimestamp(stat.st_mtime),
                'sensitive': p.name in _SENSITIVE_FILES,
            })
        return render(request, 'system/files.html', {
            'is_dir': True, 'entries': entries,
            'crumbs': _breadcrumbs(target, base),
        })

    sensitive = target.name in _SENSITIVE_FILES
    stat = target.stat()
    content, is_text, too_large = None, False, stat.st_size > _FILE_PREVIEW_MAX_BYTES
    if not sensitive and not too_large:
        try:
            content = target.read_text(encoding='utf-8')
            is_text = True
        except (UnicodeDecodeError, ValueError):
            is_text = False
    return render(request, 'system/files.html', {
        'is_dir': False, 'file_name': target.name, 'file_path': subpath,
        'sensitive': sensitive, 'is_text': is_text, 'content': content,
        'too_large': too_large, 'size': _human_size(stat.st_size),
        'mtime': datetime.fromtimestamp(stat.st_mtime),
        'crumbs': _breadcrumbs(target, base),
    })


@system_required
def files_download(request, subpath):
    target, base = _resolve_project_path(subpath)
    if target.is_dir() or target.name in _SENSITIVE_FILES:
        raise Http404
    return FileResponse(open(target, 'rb'), as_attachment=True, filename=target.name)
