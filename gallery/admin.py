from django.contrib import admin
from django.utils.html import format_html

from .models import MediaItem


@admin.register(MediaItem)
class MediaItemAdmin(admin.ModelAdmin):
    list_display = ("id", "preview", "kind", "title", "caption", "credit", "storage", "provider", "created_at")
    list_filter = ("kind", "storage", "provider")
    search_fields = ("title", "caption", "credit", "alt", "url", "source_url")
    readonly_fields = ("preview", "url", "storage", "file_id", "path", "embed_url", "provider", "thumbnail_url",
                       "source_url", "width", "height", "size", "mime", "created_at")
    fields = ("preview", "kind", "title", "caption", "credit", "alt", *readonly_fields[1:])

    @admin.display(description="превью")
    def preview(self, obj):
        image = obj.sized(160) if obj.is_photo else obj.thumbnail_url
        if image:
            return format_html('<a href="{}" target="_blank"><img src="{}" style="height:48px;border-radius:4px"></a>',
                               obj.url, image)
        return format_html('<a href="{}" target="_blank">открыть ↗</a>', obj.url) if obj.url else "—"

    def has_add_permission(self, request):  # добавляют через API: POST /api/v1/media/
        return False
