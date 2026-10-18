"""Настройки проекта «Florida RU».

Все секреты и всё, что отличается между локальной машиной и продом,
читается из переменных окружения (см. .env.example).
"""

import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# В тестах (pytest) по умолчанию включаем DEBUG: dev-ключ и обычное хранилище статики.
TESTING = "pytest" in sys.modules
DEBUG = env_bool("DJANGO_DEBUG", TESTING)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or (
    "dev-insecure-key-change-me" if DEBUG else None
)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
if render_host := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(render_host)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Публичный адрес сайта — нужен для ссылок в Telegram, sitemap и canonical.
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")
SITE_NAME = "Florida RU"
# Мета-тег подтверждения сайта в Google Search Console (только значение content="…").
GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    "core",
    "news",
    "sources",
    "pipeline",
    "social",
    "guides",
    "ads",
    "stats",
    "directory",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "api",
]

# Заявки бизнесов в справочник: True — проверять ИИ прямо в запросе (тесты), иначе в фоновом потоке.
DIRECTORY_MODERATION_SYNC = env_bool("DIRECTORY_MODERATION_SYNC")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "stats.tracking.StatsMiddleware",  # посещаемость: дневные счётчики без cookie и IP
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

# --- Сбор новостей -----------------------------------------------------------

FETCH_USER_AGENT = os.environ.get(
    "FETCH_USER_AGENT",
    f"FloridaRUBot/1.0 (+{SITE_URL}/about/)",
)
FETCH_TIMEOUT = int(os.environ.get("FETCH_TIMEOUT", "20"))
# После скольких ошибок подряд источник помечается как сломанный.
SOURCE_MAX_FAILURES = 3

# --- ИИ ----------------------------------------------------------------------

# Провайдер: "deepseek" (по умолчанию) или "anthropic".
AI_PROVIDER = os.environ.get("AI_PROVIDER", "deepseek").strip().lower()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Модели по умолчанию для каждого провайдера. Названия моделей DeepSeek меняются —
# сверьте их командой `python manage.py check_ai` и при необходимости задайте через env.
_DEFAULT_MODELS = {
    "deepseek": {"classifier": "deepseek-flash", "writer": "deepseek-v4-pro"},
    "anthropic": {"classifier": "claude-haiku-4-5", "writer": "claude-sonnet-5"},
}.get(AI_PROVIDER, {"classifier": "", "writer": ""})
AI_CLASSIFIER_MODEL = os.environ.get("AI_CLASSIFIER_MODEL") or _DEFAULT_MODELS["classifier"]
AI_WRITER_MODEL = os.environ.get("AI_WRITER_MODEL") or _DEFAULT_MODELS["writer"]
AI_VERIFIER_MODEL = os.environ.get("AI_VERIFIER_MODEL") or AI_CLASSIFIER_MODEL
# Уровень усилий для модели-автора Anthropic (low/medium/high). Пусто — не передавать.
AI_WRITER_EFFORT = os.environ.get("AI_WRITER_EFFORT", "medium")

# Цены в долларах за 1 млн токенов. input — вход без попадания в кэш, cache_read — вход
# из кэша, cache_write — запись в кэш (только Anthropic). Это оценка для лимита бюджета:
# сверяйте с официальными тарифами и правьте здесь или через AI_PRICING_JSON.
# Для DeepSeek взяты пиковые (более высокие) цены: вне пика реальный счёт будет ниже.
AI_PRICING = {
    "deepseek-v4-flash": {"input": "0.30", "cache_read": "0.03", "output": "1.20"},
    "deepseek-flash": {"input": "0.30", "cache_read": "0.03", "output": "1.20"},
    "deepseek-v4-pro": {"input": "1.32", "cache_read": "0.13", "output": "3.96"},
    "deepseek-pro": {"input": "1.32", "cache_read": "0.13", "output": "3.96"},
    "claude-haiku-4-5": {"input": "1.00", "cache_read": "0.10", "cache_write": "1.25", "output": "5.00"},
    "claude-haiku-5-5": {"input": "0.10", "cache_read": "0.01", "cache_write": "0.125", "output": "0.50"},
    "claude-sonnet-5": {"input": "2.00", "cache_read": "0.20", "cache_write": "2.50", "output": "10.00"},
    "claude-sonnet-5-5": {"input": "2.00", "cache_read": "0.20", "cache_write": "2.50", "output": "10.00"},
    # Сигналы из соцсетей: "request" — плата за один запрос с поиском, сверх токенов.
    # Оценка с запасом; сверьте с тарифами Perplexity и xAI и поправьте через AI_PRICING_JSON.
    "perplexity/sonar": {"input": "1.00", "output": "1.00", "request": "0.012"},
    "grok-4.7": {"input": "3.00", "output": "15.00", "request": "0.05"},
}
# Пример: AI_PRICING_JSON='{"deepseek-flash": {"input": "0.14", "cache_read": "0.014", "output": "0.28"}}'
if pricing_json := os.environ.get("AI_PRICING_JSON"):
    import json

    AI_PRICING.update(json.loads(pricing_json))

# --- Сигналы из соцсетей -----------------------------------------------------
# Соцсети — только подсказки: заметки пишутся и публикуются по подтверждению от СМИ
# или официального источника. Каждый сборщик включается галочкой в настройках сайта.
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_API_URL = os.environ.get("PERPLEXITY_API_URL", "https://api.perplexity.ai/v1/responses")
PERPLEXITY_MODEL = os.environ.get("PERPLEXITY_MODEL", "perplexity/sonar")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
XAI_API_URL = os.environ.get("XAI_API_URL", "https://api.x.ai/v1/responses")
XAI_MODEL = os.environ.get("XAI_MODEL", "grok-4.7")
TG_API_ID = os.environ.get("TG_API_ID", "")
TG_API_HASH = os.environ.get("TG_API_HASH", "")
TG_SESSION = os.environ.get("TG_SESSION", "")  # строка сессии от `manage.py telegram_login`
# Сбор сигналов останавливается, когда потрачена эта доля дневного бюджета на ИИ:
# остаток остаётся на отбор и написание заметок.
SIGNALS_BUDGET_SHARE = float(os.environ.get("SIGNALS_BUDGET_SHARE", "0.7"))

# --- Telegram ----------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_CHANNEL_URL = os.environ.get("TELEGRAM_CHANNEL_URL", "https://t.me/")

# Демо-режим: показывает плашку «демо-данные» (для локального просмотра с seed_demo).
DEMO_MODE = env_bool("DEMO_MODE", False)
FORMS_URLFIELD_ASSUME_HTTPS = True
SERVE_MEDIA = env_bool("SERVE_MEDIA", False)

# --- API для удалённого управления ----------------------------------------------
# Доступ — только сотрудникам (is_staff) по токену: заголовок «Authorization: Token <ключ>».
# Токен создаётся командой `python manage.py drf_create_token <логин>` или в админке.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "600/hour"},
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Florida RU — API управления",
    "DESCRIPTION": "Заметки, источники, реклама, настройки, страницы, запуск конвейера и статистика. "
                   "Авторизация: заголовок `Authorization: Token <ключ>` (ключ сотрудника).",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
}
