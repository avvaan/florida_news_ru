from django.contrib import admin
from django.shortcuts import redirect

from .models import Page, SiteSettings

admin.site.site_header = "Флорида Сегодня — редакция"
admin.site.site_title = "Флорида Сегодня"
admin.site.index_title = "Управление сайтом"


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Отбор и публикация", {"fields": (
            "min_score_to_write", "publish_without_review", "auto_publish_enabled", "auto_publish_min_score", "min_verifier_confidence",
        )}),
        ("Лимиты расходов", {"fields": ("max_articles_per_day", "ai_budget_per_day_usd")}),
        ("Сбор и склейка", {"fields": ("max_items_per_source", "cluster_window_hours", "cluster_similarity")}),
        ("Telegram", {"fields": ("telegram_enabled", "telegram_channel_url")}),
        ("Сайт", {"fields": ("contact_email", "adsense_enabled", "adsense_client")}),
        ("Сигналы из соцсетей (только подсказки, не источник публикаций)", {"fields": (
            "signals_perplexity_enabled", "signals_grok_enabled", "signals_telegram_enabled",
            "signals_max_per_source",
        )}),
        ("Агент DMCA (страница /dmca/)", {"fields": (
            "dmca_agent_name", "dmca_agent_address", "dmca_agent_phone", "dmca_agent_email",
        )}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = SiteSettings.load()
        return redirect("admin:core_sitesettings_change", obj.pk)


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "in_footer", "order", "updated_at")
    list_editable = ("in_footer", "order")
