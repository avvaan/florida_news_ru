from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import AdBanner


@admin.register(AdBanner)
class AdBannerAdmin(admin.ModelAdmin):
    list_display = ("advertiser", "slot", "region", "preview", "starts_at", "ends_at", "is_active", "running")
    list_filter = ("slot", "is_active", "region")
    list_editable = ("is_active",)
    search_fields = ("advertiser", "headline")

    @admin.display(description="картинка")
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:40px">', obj.image.url)
        return obj.headline or "—"

    @admin.display(description="показывается сейчас", boolean=True)
    def running(self, obj):
        now = timezone.now()
        return (
            obj.is_active
            and (obj.starts_at is None or obj.starts_at <= now)
            and (obj.ends_at is None or obj.ends_at >= now)
        )
