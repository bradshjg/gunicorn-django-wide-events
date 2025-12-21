import os
from pathlib import Path

ROOT_URLCONF = "app"

DEBUG = os.environ.get("DEBUG", "0") == "1"

BASE_DIR = Path(__file__).resolve().parent

ALLOWED_HOSTS = ["localhost"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(__file__).parent / "db.sqlite3",
        "TEST": {"NAME": Path(__file__).parent / "db.sqlite3"},
    }
}

SECRET_KEY = "not-so-secret"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [Path(__file__).parent / "templates"],
    }
]

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "static"

STATIC_URL = "static/"  # HACK otherwise Django liveserver test cases parse the base url as bytes

USE_TZ = True

INSTALLED_APPS = (
    "django.contrib.staticfiles",
    "db",
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}
