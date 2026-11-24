from django.conf import settings
from django.urls import reverse, translate_url
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_noop

from news.models import HIDDEN_IN_NAV, Region, Topic

from .models import Page, SiteSettings
from .seed import DISCLAIMER, SITE_OWNER

# Строка-образец для makemessages: та же, что core.seed.DISCLAIMER (её переводит gettext ниже).
# Поменяли текст в seed.py — поменяйте и здесь, иначе на украинской версии останется русский.
gettext_noop(
    "Мы пересказываем новости своими словами и всегда даём ссылку на первоисточник. "
    "Это не юридическая и не финансовая консультация."
)


def telegram_url(conf) -> str:
    """Ссылка на канал: настройка TELEGRAM_CHANNEL_URL (env), запасной вариант — поле в «Настройках».

    Ссылку без названия канала (https://t.me/) считаем пустой — тогда кнопки не показываются.
    """
    url = (settings.TELEGRAM_CHANNEL_URL or conf.telegram_channel_url or "").strip()
    return url if url.rstrip("/").rsplit("/", 1)[-1] not in {"", "t.me", "telegram.me"} else ""


def site(request):
    conf = SiteSettings.load()
    return {
        "site_name": settings.SITE_NAME,
        "site_url": settings.SITE_URL,
        "site_conf": conf,
        "telegram_url": telegram_url(conf),
        "nav_regions": Region.objects.all(),
        "nav_topics": Topic.objects.exclude(slug__in=HIDDEN_IN_NAV),
        "footer_pages": Page.objects.filter(in_footer=True),
        "disclaimer": gettext(DISCLAIMER),
        "site_owner": SITE_OWNER,
        "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        "now": timezone.localtime(),
        "demo_mode": getattr(settings, "DEMO_MODE", False),
    }


SWITCH_LABELS = {"ru": "RU", "uk": "UA"}


def languages(request):
    """Переключатель языка и hreflang: адрес текущей страницы на каждом языке сайта."""
    current = translation.get_language()
    path = request.get_full_path()
    # Страница только на одном языке (core.i18n.only_language): на другом — раздел fallback, без hreflang.
    only, fallback = getattr(request, "only_language", ("", ""))
    switch = []
    # «UA | RU»: украинский первым.
    for code, name in sorted(settings.LANGUAGES, key=lambda lang: lang[0] != "uk"):
        url = translate_url(path, code) if code != current else path
        missing = only and code != only
        if missing or (url == path and code != current):  # адрес не разобрался (404 и т. п.) — на главную языка
            with translation.override(code):
                url = reverse(fallback if missing else "news:home")
        switch.append({"code": code, "name": name, "label": SWITCH_LABELS.get(code, code.upper()),
                       "url": url, "current": code == current, "missing": missing})
    return {
        "LANGUAGE_CODE": current,
        "is_uk": current == "uk",
        "lang_switch": switch,
        "lang_urls": {item["code"]: item["url"].split("?", 1)[0] for item in switch if not item["missing"]},
    }
