from django.contrib import admin, messages
from django.utils.html import format_html

from . import moderation
from .models import Comment


@admin.action(description="Проверить ИИ ещё раз (только «на проверке»)")
def action_remoderate(modeladmin, request, queryset):
    done = sum(moderation.moderate(c).status != Comment.Status.PENDING
               for c in queryset.filter(status=Comment.Status.PENDING))
    modeladmin.message_user(request, f"Проверено: {done}", messages.SUCCESS)


@admin.action(description="Скрыть с сайта")
def action_hide(modeladmin, request, queryset):
    for comment in queryset:
        moderation.reject(comment, "other", f"Скрыто редакцией ({request.user})")
    modeladmin.message_user(request, "Скрыто", messages.WARNING)


@admin.action(description="Опубликовать (жалобы необоснованны)")
def action_publish(modeladmin, request, queryset):
    n = queryset.exclude(status=Comment.Status.APPROVED).update(status=Comment.Status.APPROVED, public_reason="")
    for comment in queryset:
        comment.report_set.all().delete()
    queryset.update(reports=0)
    modeladmin.message_user(request, f"Опубликовано: {n}", messages.SUCCESS)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "short_text", "rating", "on", "status", "violation", "reports")
    list_filter = ("status", "violation", ("listing", admin.EmptyFieldListFilter))
    search_fields = ("name", "email", "text")
    date_hierarchy = "created_at"
    actions = [action_remoderate, action_hide, action_publish]
    raw_id_fields = ("article", "listing")
    readonly_fields = ("token", "status", "violation", "reason", "public_reason", "attempts", "reports", "ip_hash",
                       "created_at", "moderated_at", "link")
    fields = ("article", "listing", "link", "name", "email", "rating", "text", "status", "violation", "reason",
              "public_reason", "attempts", "reports", "ip_hash", "created_at", "moderated_at", "token")

    @admin.display(description="текст")
    def short_text(self, obj):
        return obj.text[:90]

    @admin.display(description="к чему")
    def on(self, obj):
        target = obj.target
        label = getattr(target, "title", None) or getattr(target, "name", "")
        return format_html('<a href="{}" target="_blank">{}</a>', target.get_absolute_url(), label[:50])

    @admin.display(description="на сайте")
    def link(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.get_absolute_url(), obj.get_absolute_url()) \
            if obj.pk else "—"

    def has_add_permission(self, request):
        return False
