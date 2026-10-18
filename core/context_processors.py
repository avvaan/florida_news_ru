from django.conf import settings
from django.utils import timezone

from news.models import Region, Topic

from .models import Page, SiteSettings
from .seed import DISCLAIMER, SITE_OWNER


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
        "nav_topics": Topic.objects.all(),
        "footer_pages": Page.objects.filter(in_footer=True),
        "disclaimer": DISCLAIMER,
        "site_owner": SITE_OWNER,
        "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        "now": timezone.localtime(),
        "demo_mode": getattr(settings, "DEMO_MODE", False),
    }
