from django.contrib import admin, messages
from django.utils.html import format_html

from core import images

from . import moderation
from .models import Event


@admin.action(description="Проверить ИИ ещё раз (только «на проверке»)")
def action_remoderate(modeladmin, request, queryset):
    done = sum(moderation.moderate(e).status != Event.Status.PENDING
               for e in queryset.filter(status=Event.Status.PENDING))
    modeladmin.message_user(request, f"Проверено заявок: {done}", messages.SUCCESS)


@admin.action(description="Снять с публикации и отклонить")
def action_reject(modeladmin, request, queryset):
    for event in queryset:
        images.delete(event.image_file_id)
        event.image_url, event.image_file_id = "", ""
        moderation.reject(event, "other", f"Отклонено редакцией ({request.user})")
    modeladmin.message_user(request, "Отклонено", messages.WARNING)


@admin.action(description="Убрать картинку (событие остаётся)")
def action_drop_image(modeladmin, request, queryset):
    for event in queryset.exclude(image_url=""):
        images.delete(event.image_file_id)
        event.image_url, event.image_file_id, event.image_status = "", "", Event.ImageStatus.REJECTED
        event.save()
    modeladmin.message_user(request, "Картинки убраны", messages.SUCCESS)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("starts_on", "title", "city", "status", "violation", "image_status", "preview", "contact_email")
    list_filter = ("status", "violation", "image_status", "region")
    search_fields = ("title", "description", "venue", "organizer", "contact_email", "contact_name", "url")
    date_hierarchy = "starts_on"
    actions = [action_remoderate, action_reject, action_drop_image]
    exclude = ("image_data",)
    readonly_fields = ("token", "status", "violation", "reason", "public_reason", "image_status", "image_url",
                       "image_file_id", "image_note", "contact_name", "contact_email", "ip_hash", "attempts",
                       "created_at", "moderated_at")
    fieldsets = (
        (None, {"fields": ("title", "description", "starts_on", "starts_at", "ends_on", "slug")}),
        ("Где", {"fields": ("venue", "address", "city", "region", "price", "url", "organizer")}),
        ("Модерация", {"fields": ("status", "violation", "reason", "public_reason", "attempts", "created_at",
                                  "moderated_at"),
                       "description": "Событие одобряет или отклоняет ИИ. Снять с публикации — действие в списке."}),
        ("Картинка", {"fields": ("image_status", "image_url", "image_file_id", "image_note")}),
        ("Заявитель (не публикуется)", {"fields": ("contact_name", "contact_email", "ip_hash", "token")}),
    )

    @admin.display(description="картинка")
    def preview(self, obj):
        return format_html('<img src="{}" style="height:40px;border-radius:4px">', images.resized(obj.image_url, 80)) \
            if obj.image_url else "—"

    def has_add_permission(self, request):
        return False
