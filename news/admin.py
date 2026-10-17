from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from pipeline.runner import AlreadyRunning, start_covers
from pipeline.services import publish_article, reject_article
from pipeline.telegram import build_post, post_article

from .covers import all_covers, describe
from .models import Article, ArticleSource, Region, Story, Tag, Topic


# Правка этих полей после публикации ставит «Обновлено» на сайте.
REVISION_FIELDS = {"title", "teaser", "body", "for_you"}


class ReviewArticle(Article):
    class Meta:
        proxy = True
        verbose_name = "заметка на проверке"
        verbose_name_plural = "📝 На проверку"


class ArticleSourceInline(admin.TabularInline):
    model = ArticleSource
    extra = 0
    fields = ("name", "url", "title", "order")


@admin.action(description="✅ Опубликовать")
def action_publish(modeladmin, request, queryset):
    n = 0
    for article in queryset.exclude(status=Article.Status.PUBLISHED):
        publish_article(article)
        n += 1
    modeladmin.message_user(request, f"Опубликовано: {n}", messages.SUCCESS)


@admin.action(description="❌ Отклонить")
def action_reject(modeladmin, request, queryset):
    n = 0
    for article in queryset:
        reject_article(article)
        n += 1
    modeladmin.message_user(request, f"Отклонено: {n}", messages.WARNING)


@admin.action(description="✈️ Отправить в Telegram (если не отправлено)")
def action_telegram(modeladmin, request, queryset):
    for article in queryset.filter(status=Article.Status.PUBLISHED):
        try:
            result = post_article(article)
            modeladmin.message_user(request, f"«{article.title}»: {result}")
        except Exception as exc:  # noqa: BLE001
            modeladmin.message_user(request, f"«{article.title}»: {exc}", messages.ERROR)


@admin.action(description="🖼 Подобрать обложку ИИ по тексту")
def action_pick_cover(modeladmin, request, queryset):
    try:
        run = start_covers(list(queryset.order_by("-created_at").values_list("pk", flat=True)[:500]),
                           source="admin")
    except AlreadyRunning:
        modeladmin.message_user(request, "Конвейер уже работает — попробуйте через несколько минут",
                                messages.WARNING)
        return
    url = reverse("admin:pipeline_pipelinerun_change", args=[run.pk])
    modeladmin.message_user(
        request, format_html("Подбираю обложки в фоне. Ход — в <a href=\"{}\">журнале запуска</a>.", url),
        messages.SUCCESS)


class BaseArticleAdmin(admin.ModelAdmin):
    change_form_template = "admin/news/article_change_form.html"
    list_display = ("title", "status_badge", "region", "topic", "score", "is_urgent", "is_sensitive", "created_at")
    list_filter = ("status", "is_urgent", "is_sensitive", "region", "topic")
    search_fields = ("title", "teaser", "body")
    autocomplete_fields = ("tags",)
    inlines = [ArticleSourceInline]
    readonly_fields = ("verification_box", "telegram_preview", "story_link", "created_at", "updated_at",
                       "telegram_posted_at", "word_count", "cover_preview")
    actions = [action_publish, action_reject, action_telegram, action_pick_cover]
    fieldsets = (
        (None, {"fields": ("title", "teaser", "body", "for_you", "guide", "word_count")}),
        ("Разметка", {"fields": ("region", "topic", "tags", "is_urgent", "is_sensitive", "score")}),
        ("Обложка", {"fields": ("cover_image", "cover_preview")}),
        ("Публикация", {"fields": ("status", "review_reason", "slug", "published_at", "revised_at")}),
        ("Проверка ИИ", {"fields": ("verification_box", "story_link")}),
        ("Telegram", {"fields": ("telegram_preview", "telegram_posted_at"), "classes": ("collapse",)}),
        ("Служебное", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "cover_image":
            choices = [("", "— автоматически из набора рубрики —")] + [
                (base, f"{base.split('/')[-1]} — {describe(cover)}")
                for base, cover in sorted(all_covers().items())
            ]
            return forms.ChoiceField(choices=choices, required=False, label="обложка",
                                     help_text=db_field.help_text)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="сейчас на обложке")
    def cover_preview(self, obj):
        if not obj.pk:
            return "—"
        info = obj.cover_info
        return format_html('<img src="{}" style="max-width:320px;border-radius:6px"><br>{}',
                           static(f"{info.base}-640.webp"), describe(info))

    @admin.display(description="статус", ordering="status")
    def status_badge(self, obj):
        colors = {"review": "#c25700", "published": "#0b7a75", "rejected": "#8a8a8a", "draft": "#555"}
        return format_html(
            '<b style="color:{}">{}</b>', colors.get(obj.status, "#333"), obj.get_status_display()
        )

    @admin.display(description="слов")
    def word_count(self, obj):
        return obj.word_count if obj.pk else "—"

    @admin.display(description="результат проверки")
    def verification_box(self, obj):
        v = obj.verification or {}
        if not v:
            return "—"
        issues = v.get("issues") or []
        items = format_html_join("", "<li>{}</li>", ((i,) for i in issues)) if issues else "замечаний нет"
        return format_html(
            "<div>Вердикт: <b>{}</b>, уверенность {}<br>Решение: {}<ul>{}</ul></div>",
            "ок" if v.get("ok") else "есть сомнения", v.get("confidence"), v.get("decision", "—"), items,
        )

    @admin.display(description="пост в Telegram")
    def telegram_preview(self, obj):
        if not obj.pk:
            return "—"
        return format_html('<pre style="white-space:pre-wrap;max-width:560px">{}</pre>', build_post(obj))

    @admin.display(description="сюжет и исходные записи")
    def story_link(self, obj):
        if not obj.story_id:
            return "—"
        rows = format_html_join(
            "", '<li><a href="{}" target="_blank" rel="noopener">{}</a> — {}</li>',
            ((i.url, i.title, i.source.name) for i in obj.story.items.select_related("source")),
        )
        return format_html("<p>{}</p><ul>{}</ul>", obj.story.note, rows)

    def response_change(self, request, obj):
        if "_publish" in request.POST:
            publish_article(obj)
            self.message_user(request, f"Опубликовано: «{obj.title}»", messages.SUCCESS)
            return HttpResponseRedirect(request.path)
        if "_reject" in request.POST:
            reject_article(obj)
            self.message_user(request, f"Отклонено: «{obj.title}»", messages.WARNING)
            return HttpResponseRedirect("../../")
        return super().response_change(request, obj)


@admin.register(ReviewArticle)
class ReviewArticleAdmin(BaseArticleAdmin):
    list_display = ("title", "review_reason", "region", "topic", "score", "is_sensitive", "created_at")
    list_filter = ("is_sensitive", "is_urgent", "region", "topic")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=Article.Status.REVIEW)

    def has_add_permission(self, request):
        return False


@admin.register(Article)
class ArticleAdmin(BaseArticleAdmin):
    date_hierarchy = "created_at"

    def save_model(self, request, obj, form, change):
        if obj.status == Article.Status.PUBLISHED and not obj.published_at:
            obj.published_at = timezone.now()
        elif change and obj.published_at and REVISION_FIELDS & set(form.changed_data):
            obj.revised_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "score", "region", "topic", "is_urgent", "is_sensitive", "n_items", "created_at")
    list_filter = ("status", "is_urgent", "is_sensitive", "region", "topic")
    search_fields = ("title",)
    readonly_fields = ("classification", "items_list", "social", "created_at", "updated_at")

    @admin.display(description="соцсети")
    def social(self, obj):
        from social.admin import social_buzz

        return social_buzz(obj)

    @admin.display(description="записей")
    def n_items(self, obj):
        return obj.items.count()

    @admin.display(description="записи из источников")
    def items_list(self, obj):
        return format_html("<ul>{}</ul>", format_html_join(
            "", '<li><a href="{}" target="_blank" rel="noopener">{}</a> — {}</li>',
            ((i.url, i.title, i.source.name) for i in obj.items.select_related("source")),
        ))


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "name_locative", "is_statewide", "order")
    list_editable = ("order",)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "priority", "cover", "order")
    list_editable = ("priority", "order")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("name", "slug")
