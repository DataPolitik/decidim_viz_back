"""
Django settings for decidim_viz_analysis.

Everything deployment-specific is read from environment variables so that no
secret has to be committed. Defaults are meant for local development only.

    DJANGO_SECRET_KEY      required when DJANGO_DEBUG is off
    DJANGO_DEBUG           "1" (default) or "0"
    DJANGO_ALLOWED_HOSTS   comma-separated, e.g. "viz.example.org,localhost"
    DJANGO_CORS_ORIGINS    comma-separated origins of the front end,
                           e.g. "https://viz.example.org". Empty + DEBUG = allow all.
    DJANGO_DB_PATH         path of the SQLite file (default: db.sqlite3 here)
    DECIDIM_VIZ_CACHE_DIR  where the network caches (pickles) are stored
    DECIDIM_VIZ_FRONTEND_DIR  optional: directory of the built front end
                           (decidim_viz_front's dist/decidim_viz_front). When set,
                           Django also serves the dashboard itself at /, so one
                           site on one address hosts both halves.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('Set DJANGO_SECRET_KEY when DJANGO_DEBUG=0')
    SECRET_KEY = 'insecure-development-key-do-not-use-in-production'

ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'stats',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'decidim_viz_analysis.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'decidim_viz_analysis.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DJANGO_DB_PATH', str(BASE_DIR / 'db.sqlite3')),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# The Angular front end is served from another origin.
CORS_ALLOWED_ORIGINS = _env_list('DJANGO_CORS_ORIGINS')
CORS_ALLOW_ALL_ORIGINS = DEBUG and not CORS_ALLOWED_ORIGINS

# Network caches written by `generate_*_cache` and read by the /comments and
# /endorsements endpoints.
DECIDIM_VIZ_CACHE_DIR = Path(os.environ.get('DECIDIM_VIZ_CACHE_DIR', BASE_DIR / 'stats' / 'cache'))

# Optionally serve the built front end from the same site (see the docstring).
# WhiteNoise answers only for files that exist in that directory ("/" gives
# index.html), so every other path, such as /stats/..., still reaches Django.
DECIDIM_VIZ_FRONTEND_DIR = os.environ.get('DECIDIM_VIZ_FRONTEND_DIR')
if DECIDIM_VIZ_FRONTEND_DIR:
    MIDDLEWARE.insert(MIDDLEWARE.index('django.middleware.security.SecurityMiddleware') + 1,
                      'whitenoise.middleware.WhiteNoiseMiddleware')
    WHITENOISE_ROOT = DECIDIM_VIZ_FRONTEND_DIR
    WHITENOISE_INDEX_FILE = True
    # The front end reads assets/config.json at start-up: never serve a stale copy.
    WHITENOISE_ADD_HEADERS_FUNCTION = lambda headers, path, url: (
        headers.__setitem__('Cache-Control', 'no-cache') if url.endswith('/config.json') else None)
