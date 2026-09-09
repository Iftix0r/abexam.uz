"""
WSGI config for core project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_wsgi_application()

# WhiteNoise only auto-serves STATIC_ROOT (via the middleware); on hosts
# without a front-end web server that serves /media/ directly (e.g. plain
# Passenger/WSGI deployment), uploaded files such as listening audio would
# 404 with no serving path at all. Wrap the app so media is always reachable.
from django.conf import settings
from whitenoise import WhiteNoise

application = WhiteNoise(application, root=str(settings.MEDIA_ROOT), prefix=settings.MEDIA_URL)
