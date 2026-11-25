from django.contrib import admin

from django.contrib import messages

from core.i18n import uk_fieldset

from . import moderation
from .models import Category, Listing, ListingUpdate, Submission


class ListingInline(admin.TabularInline):
    model = Listing
    extra = 0
    fields = ("name", "url", "city", "is_recommended", "is_partner", "is_active", "order")
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "n_listings", "order")
    list_filter = ("kind",)
    list_editable = ("order",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ListingInline]

    @admin.display(description="записей")
    def n_listings(self, obj):
        return obj.listings.filter(is_active=True).count()


OUTREACH_MESSAGE = (
    "Здравствуйте! Это редакция TutFlorida — русскоязычного сайта новостей и справочника Флориды. "
    "«{name}» есть в нашем бесплатном справочнике: {url} . Проверьте, пожалуйста, данные — если что-то "
    "устарело, поправить можно по ссылке «Обновить данные» на странице ({update_url}). Там же есть значок "
    "«Мы в справочнике TutFlorida» для вашего сайта: клиенты смогут оставить вам отзыв."
)


@admin.action(description="Выгрузить для обзвона и писем (CSV)")
def action_export_outreach(modeladmin, request, queryset):
    """CSV для связи с владельцами: контакты, ссылки на страницу и правку, готовый текст сообщения."""
    import csv

    from django.conf import settings
    from django.http import HttpResponse

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="tutflorida-outreach.csv"'
    response.write("\ufeff")  # Excel откроет кириллицу без кракозябр
    writer = csv.writer(response)
    writer.writerow(["Название", "Категория", "Город", "Телефон", "Сайт", "Страница на TutFlorida", "Ссылка на правку",
                     "Показывается", "Данные от владельца", "Текст сообщения"])
    for item in queryset.select_related("category").filter(category__kind="business"):
        page = settings.SITE_URL + item.get_absolute_url()
        update = settings.SITE_URL + item.get_update_url()
        writer.writerow([item.name, item.category.name, item.city, item.phone, item.url, page, update,
                         "да" if item.is_active else "нет", "да" if item.from_owner else "нет",
                         OUTREACH_MESSAGE.format(name=item.name, url=page, update_url=update)])
    return response


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    actions = [action_export_outreach]
    list_display = ("name", "category", "city", "is_recommended", "is_partner", "from_owner", "is_active", "updated_at")
    list_filter = ("category__kind", "category", "specialty", "is_recommended", "is_partner", "from_owner", "is_active",
                   "region")
    list_editable = ("is_recommended", "is_partner", "is_active")
    search_fields = ("name", "description", "city", "address", "editor_note")
    fieldsets = (
        (None, {"fields": ("category", "specialty", "name", "description", "url", "phone")}),
        ("Где и когда", {"fields": ("address", "city", "region", "hours", "languages")}),
        ("Показ", {"fields": ("is_recommended", "is_partner", "is_active", "order", "guide_slug", "from_owner", "editor_note"),
                   "description": "Платное размещение обязательно отмечайте «партнёр»: читатели видят метку."}),
        uk_fieldset(Listing),
    )


@admin.action(description="Проверить ИИ ещё раз (только «на проверке»)")
def action_remoderate(modeladmin, request, queryset):
    done = sum(moderation.moderate(sub).status != Submission.Status.PENDING
               for sub in queryset.filter(status=Submission.Status.PENDING))
    modeladmin.message_user(request, f"Проверено заявок: {done}", messages.SUCCESS)


@admin.action(description="Снять с публикации и отклонить")
def action_reject(modeladmin, request, queryset):
    for sub in queryset:
        if sub.listing_id:
            Listing.objects.filter(pk=sub.listing_id).update(is_active=False)
        moderation.reject(sub, "other", f"Отклонено редакцией ({request.user})")
    modeladmin.message_user(request, "Отклонено", messages.WARNING)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "category", "city", "status", "violation", "listing", "contact_email")
    list_filter = ("status", "violation", "category")
    search_fields = ("name", "description", "contact_email", "contact_name", "phone", "url")
    date_hierarchy = "created_at"
    actions = [action_remoderate, action_reject]
    readonly_fields = [f.name for f in Submission._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.action(description="Применить правку (или снять бизнес, если владелец просит)")
def action_apply_update(modeladmin, request, queryset):
    done = 0
    for update in queryset.filter(status=ListingUpdate.Status.PENDING).select_related("listing"):
        update.apply()
        done += 1
    modeladmin.message_user(request, f"Применено правок: {done}", messages.SUCCESS)


@admin.action(description="Отклонить правку")
def action_reject_update(modeladmin, request, queryset):
    from django.utils import timezone

    n = queryset.filter(status=ListingUpdate.Status.PENDING).update(status=ListingUpdate.Status.REJECTED,
                                                                    handled_at=timezone.now())
    modeladmin.message_user(request, f"Отклонено: {n}", messages.WARNING)


@admin.register(ListingUpdate)
class ListingUpdateAdmin(admin.ModelAdmin):
    """Правки от владельцев: сравнить «было → стало» и применить одним действием."""

    list_display = ("created_at", "listing", "status", "remove", "contact_name", "contact_email")
    list_filter = ("status", "remove")
    search_fields = ("listing__name", "contact_name", "contact_email", "comment")
    actions = [action_apply_update, action_reject_update]
    readonly_fields = ("listing", "diff", "created_at", "handled_at", "ip_hash")
    fields = ("listing", "status", "diff", "remove", "comment", "description", "phone", "url", "address", "city",
              "hours", "languages", "contact_name", "contact_email", "contact_phone", "created_at", "handled_at")

    def has_add_permission(self, request):
        return False

    @admin.display(description="было → стало")
    def diff(self, obj):
        from django.utils.html import format_html_join

        rows = [(name, old or "—", new) for name, (old, new) in obj.changes().items()]
        if not rows:
            return "Без изменений в полях" + (" — просит убрать бизнес" if obj.remove else "")
        return format_html_join("", "<p><b>{}</b>: {} → <b>{}</b></p>", rows)
