from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from guides import markup

from .models import Destination, DestinationSource


class DestinationSourceInline(admin.TabularInline):
    model = DestinationSource
    extra = 0
    fields = ("name", "url", "title", "order")


@admin.action(description="✅ Опубликовать")
def action_publish(modeladmin, request, queryset):
    now = timezone.now()
    for item in queryset:
        item.status = Destination.Status.PUBLISHED
        item.published_at = item.published_at or now
        item.save(update_fields=["status", "published_at", "updated_at"])
    modeladmin.message_user(request, "Опубликованы", messages.SUCCESS)


@admin.action(description="Снять с публикации")
def action_unpublish(modeladmin, request, queryset):
    queryset.update(status=Destination.Status.DRAFT)
    modeladmin.message_user(request, "Сняты с публикации", messages.WARNING)


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ("title", "lang", "region", "order", "status", "chars", "n_places", "checked_on",
                    "published_at", "preview")
    list_filter = ("lang", "status", "region")
    search_fields = ("title", "body", "slug")
    inlines = [DestinationSourceInline]
    actions = [action_publish, action_unpublish]
    readonly_fields = ("content_hash", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("title", "slug", "lang", "teaser", "region", "order", "status", "checked_on")}),
        ("Текст", {"fields": ("body",), "description": "Правки здесь живут, пока не изменится файл "
                                                       "places/content/<язык>/<slug>.md — тогда import_places "
                                                       "перезапишет статью при деплое."}),
        ("Картинки", {"fields": ("cover", "cover_caption", "photo_credits")}),
        ("Служебное", {"fields": ("published_at", "revised_at", "content_hash", "created_at", "updated_at")}),
    )

    @admin.display(description="знаков")
    def chars(self, obj):
        return markup.plain_length(obj.body)

    @admin.display(description="мест")
    def n_places(self, obj):
        return len(obj.places)

    @admin.display(description="")
    def preview(self, obj):
        return format_html('<a href="{}" target="_blank">открыть ↗</a>', obj.get_absolute_url())
