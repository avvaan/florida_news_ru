from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .fetch import check_source, fetch_all, make_session
from .models import FeedItem, Source, WeatherAlert


@admin.action(description="Проверить фид (RSS/Atom отдаётся?)")
def action_check(modeladmin, request, queryset):
    session = make_session()
    for source in queryset:
        ok, detail = check_source(source, session)
        source.is_verified = ok
        source.verified_at = timezone.now()
        source.save(update_fields=["is_verified", "verified_at"])
        modeladmin.message_user(
            request, f"{source.name}: {'OK' if ok else 'ОШИБКА'} — {detail}",
            messages.SUCCESS if ok else messages.ERROR,
        )


@admin.action(description="Собрать сейчас")
def action_fetch(modeladmin, request, queryset):
    for r in fetch_all(queryset, include_broken=True):
        level = messages.ERROR if r.error else messages.SUCCESS
        modeladmin.message_user(request, f"{r.source.name}: {r.error or f'новых {r.created}'}", level)


@admin.action(description="Сбросить ошибки (снять «сломан»)")
def action_reset(modeladmin, request, queryset):
    queryset.update(is_broken=False, consecutive_failures=0, last_error="")


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "region", "trust_weight", "is_active", "health", "last_success_at")
    list_editable = ("trust_weight", "is_active")
    list_filter = ("is_active", "is_verified", "is_broken", "source_type", "region")
    search_fields = ("name", "url")
    actions = [action_check, action_fetch, action_reset]
    readonly_fields = ("etag", "last_modified", "last_fetched_at", "last_success_at", "consecutive_failures",
                       "verified_at", "last_error")
    fieldsets = (
        (None, {"fields": ("name", "homepage", "url", "kind", "source_type", "region", "trust_weight",
                           "is_active", "notes")}),
        ("Состояние", {"fields": ("is_verified", "verified_at", "is_broken", "consecutive_failures",
                                  "last_fetched_at", "last_success_at", "last_error")}),
        ("HTTP-кэш", {"fields": ("etag", "last_modified"), "classes": ("collapse",)}),
    )

    @admin.display(description="состояние")
    def health(self, obj):
        if obj.is_broken:
            return format_html('<b style="color:#c0392b">сломан</b> ({} ошибок)', obj.consecutive_failures)
        if not obj.is_verified:
            return mark_safe('<span style="color:#c25700">не проверен</span>')
        if obj.consecutive_failures:
            return format_html('<span style="color:#c25700">ошибок: {}</span>', obj.consecutive_failures)
        return mark_safe('<span style="color:#0b7a75">ок</span>')


@admin.register(FeedItem)
class FeedItemAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "published_at", "story")
    list_filter = ("source",)
    search_fields = ("title", "summary")
    raw_id_fields = ("story",)
    date_hierarchy = "fetched_at"


@admin.register(WeatherAlert)
class WeatherAlertAdmin(admin.ModelAdmin):
    list_display = ("event_ru", "severity", "area_short", "expires", "is_active", "is_hidden")
    list_filter = ("is_active", "is_hidden", "severity", "event")
    list_editable = ("is_hidden",)

    @admin.display(description="районы")
    def area_short(self, obj):
        return (obj.area[:80] + "…") if len(obj.area) > 80 else obj.area
