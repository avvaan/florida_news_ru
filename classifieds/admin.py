from django.contrib import admin, messages
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from core import images

from . import moderation
from .models import LIFETIME, Ad, Category, Photo, Report


@admin.action(description="Проверить ИИ ещё раз (только «на проверке»)")
def action_remoderate(modeladmin, request, queryset):
    done = sum(moderation.moderate(ad).status != Ad.Status.PENDING
               for ad in queryset.filter(status=Ad.Status.PENDING).select_related("category"))
    modeladmin.message_user(request, f"Проверено объявлений: {done}", messages.SUCCESS)


@admin.action(description="Снять с публикации и отклонить (фото удаляются)")
def action_reject(modeladmin, request, queryset):
    for ad in queryset:
        moderation.delete_photos(ad)
        moderation.reject(ad, "other", f"Отклонено редакцией ({request.user})")
    modeladmin.message_user(request, "Отклонено", messages.WARNING)


@admin.action(description="Вернуть на сайт (жалобы необоснованны)")
def action_restore(modeladmin, request, queryset):
    restored = 0
    for ad in queryset.filter(status__in=[Ad.Status.HIDDEN, Ad.Status.REJECTED]):
        ad.status = Ad.Status.APPROVED
        if not ad.expires_at or ad.expires_at < timezone.now():
            ad.published_at, ad.expires_at = timezone.now(), timezone.now() + LIFETIME
        ad.save()
        ad.reports.all().delete()
        restored += 1
    modeladmin.message_user(request, f"Возвращено: {restored}", messages.SUCCESS)


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0
    can_delete = True
    fields = ("preview", "order", "status", "note")
    readonly_fields = ("preview", "status", "note")

    @admin.display(description="фото")
    def preview(self, obj):
        return format_html('<a href="{}" target="_blank"><img src="{}" style="height:60px;border-radius:4px"></a>',
                           obj.url, images.resized(obj.url, 120)) if obj.url else "—"

    def has_add_permission(self, request, obj=None):
        return False


class ReportInline(admin.TabularInline):
    model = Report
    extra = 0
    fields = ("created_at", "reason", "comment")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ("created_at", "title", "category", "city", "price_text", "status", "violation", "photo_count",
                    "report_count", "expires_at")
    list_filter = ("status", "violation", "category__parent", "region")
    search_fields = ("title", "description", "city", "zip_code", "phone", "telegram", "contact_name")
    date_hierarchy = "created_at"
    actions = [action_remoderate, action_reject, action_restore]
    inlines = [PhotoInline, ReportInline]
    autocomplete_fields = ("category",)
    readonly_fields = ("token", "status", "violation", "reason", "public_reason", "attempts", "views", "contact_views",
                       "ip_hash", "created_at", "moderated_at", "published_at", "closed_at", "manage_link")
    fieldsets = (
        (None, {"fields": ("category", "title", "description", "price", "price_unit")}),
        ("Где", {"fields": ("city", "zip_code", "region")}),
        ("Контакты (видны по кнопке)", {"fields": ("contact_name", "phone", "has_whatsapp", "telegram")}),
        ("Модерация", {"fields": ("status", "violation", "reason", "public_reason", "attempts", "created_at",
                                  "moderated_at", "published_at", "expires_at", "closed_at"),
                       "description": "Объявления одобряет или отклоняет ИИ. Снять или вернуть — действия в списке."}),
        ("Служебное", {"fields": ("views", "contact_views", "ip_hash", "token", "manage_link")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("category__parent").annotate(
            n_photos=Count("photos", distinct=True), n_reports=Count("reports", distinct=True))

    @admin.display(description="фото", ordering="n_photos")
    def photo_count(self, obj):
        return obj.n_photos or "—"

    @admin.display(description="жалобы", ordering="n_reports")
    def report_count(self, obj):
        return obj.n_reports or "—"

    @admin.display(description="цена")
    def price_text(self, obj):
        return obj.price_text

    @admin.display(description="ссылка автора")
    def manage_link(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.get_manage_url(), obj.get_manage_url())

    def has_add_permission(self, request):
        return False

    def _warn_about_photos(self, request):
        if missing := images.missing_setup():
            self.message_user(request, f"Фото объявлений сейчас не публикуются — не хватает: {', '.join(missing)}. "
                              "Фото хранятся в базе и опубликуются сами, когда ключи появятся в Render.",
                              messages.WARNING)

    def changelist_view(self, request, extra_context=None):
        self._warn_about_photos(request)
        return super().changelist_view(request, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        self._warn_about_photos(request)
        return super().change_view(request, object_id, form_url, extra_context)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "slug", "price_label", "order")
    list_editable = ("order",)
    list_filter = ("parent",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "ad", "reason", "comment")
    list_filter = ("reason",)
    readonly_fields = ("ad", "reason", "comment", "ip_hash", "created_at")

    def has_add_permission(self, request):
        return False
