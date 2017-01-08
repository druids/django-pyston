from dj.settings.base import *

DEBUG = TEMPLATES[0]['OPTIONS']['debug'] = THUMBNAIL_DEBUG = True

ALLOWED_HOSTS = ['localhost']

# URL with protocol (and port)
PROJECT_URL = 'localhost:8000'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(PROJECT_DIR, 'var', 'db', 'sqlite.db'),
        'USER': '',
        'PASSWORD': '',
    },
}
