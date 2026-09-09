import os
import sys

# Add the project root to sys.path so Django can import the core package.
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
os.chdir(project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

application = get_wsgi_application()

# Passenger routes every request through this WSGI app with no static file
# server in front of it, so uploaded media (listening audio, images) needs
# an explicit serving path here or it 404s in production.
application = WhiteNoise(application, root=str(settings.MEDIA_ROOT), prefix=settings.MEDIA_URL)
