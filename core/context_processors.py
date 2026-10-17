from django.conf import settings
from django.utils import timezone

from news.models import Region, Topic

from .models import Page, SiteSettings
from .seed import DISCLAIMER, SITE_OWNER


def site(request):
    conf = SiteSettings.load()
    return {
        "site_name": settings.SITE_NAME,
        "site_url": settings.SITE_URL,
        "site_conf": conf,
        "telegram_url": conf.telegram_channel_url or settings.TELEGRAM_CHANNEL_URL,
        "nav_regions": Region.objects.all(),
        "nav_topics": Topic.objects.all(),
        "footer_pages": Page.objects.filter(in_footer=True),
        "disclaimer": DISCLAIMER,
        "site_owner": SITE_OWNER,
        "now": timezone.localtime(),
        "demo_mode": getattr(settings, "DEMO_MODE", False),
    }
