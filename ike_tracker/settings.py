"""
Django settings for ike_tracker project.
Updated for Production (Render + Neon.tech)
"""

from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

# Wczytaj zmienne z pliku .env
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# --- SECURITY CONFIGURATION ---

# Klucz pobieramy z .env. Jeśli go nie ma, rzucamy błąd (na produkcji) lub dajemy fallback (lokalnie)
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-fallback-key-for-dev-only')

# Debug: True tylko jeśli w .env jest wpisane 'True'
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# Hosty: Rozdzielamy przecinkami z .env, a na Renderze domyślnie akceptujemy wszystko ('*')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # <--- WAŻNE: Obsługa plików statycznych na produkcji
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ike_tracker.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ike_tracker.wsgi.application'


# --- DATABASE CONFIGURATION ---
# Hybryda: Domyślnie SQLite, ale jeśli Render poda DATABASE_URL, przełączamy na PostgreSQL

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Nadpisz, jeśli zdefiniowano DATABASE_URL (np. z Neon.tech na Renderze)
database_url = os.environ.get('DATABASE_URL')
if database_url:
    DATABASES['default'] = dj_database_url.parse(database_url, conn_max_age=600)


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# --- STATIC FILES (CSS, JavaScript, Images) ---
# Konfiguracja dla Whitenoise (niezbędna na Renderze)

STATIC_URL = 'static/'

# Gdzie szukać plików statycznych w projekcie (Twój folder static)
#STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# Gdzie zbierać pliki do publikacji (tworzone przez collectstatic)
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Kompresja i cachowanie plików statycznych
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# --- LOGIN / LOGOUT REDIRECTS ---
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_URL = 'login'

# --- LOGGING CONFIGURATION ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        # Na produkcji pliki logów często nie działają dobrze (system plików jest ulotny),
        # więc polegamy głównie na konsoli (stdout), którą Render przechwytuje.
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'core': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# --- DEFAULT CURRENCY RATES ---
DEFAULT_CURRENCY_RATES = {
    'EUR': 4.30,
    'USD': 4.00,
    'GBP': 5.20,
    'JPY': 2.60,
    'AUD': 2.60
}

# Fix dla Rendera (CSRF) - pozwala na przesyłanie formularzy z domeny onrender.com
CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']