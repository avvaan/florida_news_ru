from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import format_html

from core.i18n import uk_fieldset

from .models import STALE_DAYS, City, Club, ClubPhoto, ClubReport


class StaleFilter(admin.SimpleListFilter):
    title = "проверка"
    parameter_name = "verified"

    def lookups(self, request, model_admin):
        return [("stale", f"не проверялось > {STALE_DAYS} дней"), ("never", "ни разу не проверялось"),
                ("fresh", f"проверено за {STALE_DAYS} дней")]

    def queryset(self, request, queryset):
        border = timezone.localdate() - timedelta(days=STALE_DAYS)
        if self.value() == "stale":
            return queryset.stale()
        if self.value() == "never":
            return queryset.filter(last_verified_at__isnull=True)
        if self.value() == "fresh":
            return queryset.filter(last_verified_at__gte=border)
        return queryset


class ClubPhotoInline(admin.TabularInline):
    model = ClubPhoto
    extra = 0
    autocomplete_fields = ["media"]
    fields = ("media", "permission_confirmed", "order")


class ClubReportInline(admin.TabularInline):
    model = ClubReport
    extra = 0
    fields = ("created_at", "reason", "comment", "contact", "status")
    readonly_fields = ("created_at", "reason", "comment", "contact")
    can_delete = True


def _set_status(status, label):
    @admin.action(description=label)
    def action(modeladmin, request, queryset):
        if status == Club.Status.PUBLISHED:
            no_city = queryset.exclude(format="online").filter(city__isnull=True)
            if no_city.exists():
                modeladmin.message_user(request, "Не опубликованы (нет города у очных занятий): " +
                                        ", ".join(no_city.values_list("name", flat=True)), messages.WARNING)
                queryset = queryset.exclude(pk__in=no_city)
        n = queryset.update(status=status, updated_at=timezone.now())
        modeladmin.message_user(request, f"{label}: {n}", messages.SUCCESS)
    action.__name__ = f"set_{status}"
    return action


@admin.action(description="Отметить «проверено сегодня»")
def mark_verified(modeladmin, request, queryset):
    n = queryset.update(last_verified_at=timezone.localdate(), updated_at=timezone.now())
    modeladmin.message_user(request, f"Проверено сегодня: {n}", messages.SUCCESS)


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "city", "status", "esa_status", "last_verified_at", "origin", "n_reports",
                    "is_featured", "view_link")
    list_filter = ("status", StaleFilter, "category", "city", "esa_status", "format", "origin", "is_featured",
                   "lang_ru", "lang_uk")
    search_fields = ("name", "website", "description", "address", "phone", "email", "editor_note")
    actions = [_set_status(Club.Status.PUBLISHED, "Опубликовать"), _set_status(Club.Status.DRAFT, "В черновики"),
               _set_status(Club.Status.ARCHIVED, "В архив"), mark_verified]
    readonly_fields = ("origin", "created_at", "updated_at", "submitter_role", "submitter_name", "submitter_email",
                       "photos_link")
    inlines = [ClubPhotoInline, ClubReportInline]
    fieldsets = (
        (None, {"fields": ("status", "name", "slug", "category", "description", "is_featured")}),
        ("Возраст и язык", {"fields": (("age_min", "age_max"), ("lang_ru", "lang_uk", "lang_en", "lang_bilingual"))}),
        ("Где", {"fields": ("format", "city", "address", ("lat", "lng"))}),
        ("Расписание и стоимость", {"fields": ("schedule_text", "price_text"),
                                    "description": "Только проверенные данные. Неизвестно — оставьте пустым."}),
        ("Стипендии Step Up For Students", {"fields": ("esa_status", ("esa_pep", "esa_fes_ua", "esa_fes_eo", "esa_ftc"),
                                                        "esa_note")}),
        ("Контакты", {"fields": ("phone", "email", "website", "instagram", "facebook", "telegram", "whatsapp")}),
        ("Проверка", {"fields": ("source_url", "last_verified_at", "editor_note")}),
        ("Заявка с сайта", {"classes": ("collapse",),
                            "fields": ("origin", "submitter_role", "submitter_name", "submitter_email", "photos_link",
                                       "created_at", "updated_at")}),
        uk_fieldset(Club),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("city").annotate(
            _reports=Count("reports", filter=Q(reports__status=ClubReport.Status.NEW)))

    @admin.display(description="сообщений", ordering="_reports")
    def n_reports(self, obj):
        return obj._reports or ""

    @admin.display(description="")
    def view_link(self, obj):
        return format_html('<a href="{}" target="_blank">на сайте</a>', obj.get_absolute_url()) if obj.pk else ""


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "slug", "n_clubs", "order", "is_active")
    list_editable = ("order", "is_active")
    prepopulated_fields = {"slug": ("name_en",)}
    fieldsets = ((None, {"fields": ("name", "name_en", "name_locative", "slug", ("lat", "lng"), "order", "is_active")}),
                 uk_fieldset(City))

    @admin.display(description="опубликовано кружков")
    def n_clubs(self, obj):
        return obj.clubs.filter(status=Club.Status.PUBLISHED).count()


@admin.action(description="Отметить «разобрано»")
def mark_done(modeladmin, request, queryset):
    queryset.update(status=ClubReport.Status.DONE)


@admin.register(ClubReport)
class ClubReportAdmin(admin.ModelAdmin):
    list_display = ("club", "reason", "comment", "contact", "status", "created_at")
    list_filter = ("status", "reason")
    search_fields = ("club__name", "comment")
    actions = [mark_done]
    raw_id_fields = ("club",)
