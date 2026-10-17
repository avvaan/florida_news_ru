from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from .models import Guide, GuideSource
from .services import publish_guide, unpublish_guide

CONTENT_FIELDS = {"title", "teaser", "body"}


class GuideSourceInline(admin.TabularInline):
    model = GuideSource
    extra = 0
    fields = ("name", "url", "title", "order")


@admin.action(description="✅ Опубликовать (после проверки)")
def action_publish(modeladmin, request, queryset):
    for guide in queryset:
        if not guide.body.strip():
            modeladmin.message_user(request, f"«{guide.title}»: пустой текст — не публикуем", messages.ERROR)
            continue
        result = publish_guide(guide)
        modeladmin.message_user(request, f"Опубликован «{guide.title}». Telegram: {result}", messages.SUCCESS)


@admin.action(description="Снять с публикации")
def action_unpublish(modeladmin, request, queryset):
    for guide in queryset:
        unpublish_guide(guide)
    modeladmin.message_user(request, "Сняты с публикации", messages.WARNING)


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = ("title", "section", "order", "status", "has_text", "n_sources", "revised_at", "published_at", "preview")
    list_filter = ("status", "section", "topics")
    search_fields = ("title", "body")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("topics",)
    inlines = [GuideSourceInline]
    actions = [action_publish, action_unpublish]
    readonly_fields = ("review_notes", "created_at", "updated_at", "published_at", "telegram_posted_at", "preview")
    fieldsets = (
        (None, {"fields": ("title", "slug", "teaser", "section", "order", "cover", "body", "preview"),
                "description": "Гайды создаются черновиками (команда draft_guide) и публикуются только вручную: "
                               "проверьте текст и источники, затем поставьте статус «опубликован». Гайды из файлов "
                               "guides/content/ загружает import_guides; правка здесь сохранится, пока файл не изменят."}),
        ("Публикация", {"fields": ("status", "published_at", "revised_at", "telegram_posted_at")}),
        ("Для черновика", {"fields": ("topics", "brief", "official_domains", "review_notes")}),
        ("Служебное", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="текст", boolean=True)
    def has_text(self, obj):
        return bool(obj.body.strip())

    @admin.display(description="источников")
    def n_sources(self, obj):
        return obj.sources.count()

    @admin.display(description="на сайте")
    def preview(self, obj):
        if not obj.pk:
            return "—"
        label = "открыть" if obj.is_published else "предпросмотр черновика"
        return format_html('<a href="{}" target="_blank">{} ↗</a>', obj.get_absolute_url(), label)

    def save_model(self, request, obj, form, change):
        becomes_published = "status" in form.changed_data and obj.status == Guide.Status.PUBLISHED
        if change and obj.is_published and CONTENT_FIELDS & set(form.changed_data):
            obj.revised_at = timezone.now()
        if becomes_published:
            obj.status = Guide.Status.DRAFT  # публикует publish_guide: дата и пост в Telegram
        super().save_model(request, obj, form, change)
        if becomes_published:
            result = publish_guide(obj)
            self.message_user(request, f"Гайд опубликован. Telegram: {result}", messages.SUCCESS)
