"""TESTLAR/<n>/ papkasidagi tayyor HTML testlarni (Listening/Reading/Writing)
saytda ochish. Bu testlar bazadagi Exam'lardan alohida: har biri o'z ichida
javob tekshiruvi bor mustaqil sahifa, shuning uchun ularni shunchaki fayl
sifatida beramiz — faqat tizimga kirgan foydalanuvchilarga."""
import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.views.generic import TemplateView

# Xom materiallar (PDF, zip, asl rasmlar) ham shu papkada turishi mumkin —
# ular tashqariga chiqmasin, faqat test sahifasi va uning audiosi/rasmi.
_ALLOWED_EXT = {'.html', '.mp3', '.jpg', '.jpeg', '.png'}
_KINDS = ('Listening', 'Reading', 'Writing', 'Speaking')
_RANGE_RE = re.compile(r'bytes=(\d*)-(\d*)$')
_CHUNK = 64 * 1024


def _root():
    return Path(getattr(settings, 'TESTLAR_DIR', settings.BASE_DIR / 'TESTLAR'))


def _natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]


def _kind(name):
    return next((k for k in _KINDS if name.lower().startswith(k.lower())), 'Test')


class TestlarListView(LoginRequiredMixin, TemplateView):
    template_name = 'testlar_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        groups = []
        root = _root()
        if root.is_dir():
            folders = [d for d in root.iterdir() if d.is_dir() and d.name.isdigit()]
            for folder in sorted(folders, key=lambda d: int(d.name), reverse=True):
                files = sorted((f.name for f in folder.glob('*.html')), key=_natural_key)
                if files:
                    groups.append({
                        'number': int(folder.name),
                        'files': [{'name': f, 'title': f[:-5], 'kind': _kind(f)} for f in files],
                    })
        context['groups'] = groups
        return context


def _file_iter(fh, length):
    try:
        while length > 0:
            data = fh.read(min(_CHUNK, length))
            if not data:
                break
            length -= len(data)
            yield data
    finally:
        fh.close()


@login_required
def testlar_file(request, folder, filename):
    root = _root().resolve()
    path = (root / str(folder) / filename).resolve()
    if path.parent != root / str(folder) or path.suffix.lower() not in _ALLOWED_EXT or not path.is_file():
        raise Http404

    content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    size = path.stat().st_size

    # Audio'ni oldinga/orqaga surish (va transkriptdan vaqtga o'tish) uchun
    # brauzer Range so'rovi yuboradi; FileResponse buni qo'llamaydi.
    m = _RANGE_RE.match(request.headers.get('Range', ''))
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:
            start, end = max(0, size - int(m.group(2))), size - 1
        if start > end:
            resp = HttpResponse(status=416)
            resp['Content-Range'] = f'bytes */{size}'
            return resp
        fh = open(path, 'rb')
        fh.seek(start)
        resp = StreamingHttpResponse(_file_iter(fh, end - start + 1), status=206, content_type=content_type)
        resp['Content-Range'] = f'bytes {start}-{end}/{size}'
        resp['Content-Length'] = str(end - start + 1)
    else:
        resp = FileResponse(open(path, 'rb'), content_type=content_type)
    resp['Accept-Ranges'] = 'bytes'
    return resp
