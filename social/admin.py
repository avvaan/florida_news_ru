from django.contrib import admin, messages
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from pipeline.services import RunLog

from .models import Hint, Signal, SignalSource
from .services import confirm_hints


@admin.action(description="Сбросить ошибки")
def action_reset(modeladmin, request, queryset):
    queryset.update(consecutive_failures=0, last_error="")


@admin.register(SignalSource)
class SignalSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "query_short", "region", "is_active", "health", "last_success_at")
    list_editable = ("is_active",)
    list_filter = ("kind", "is_active", "region")
    search_fields = ("name", "query")
    actions = [action_reset]
    readonly_fields = ("last_fetched_at", "last_success_at", "consecutive_failures", "last_error", "last_message_id")
    fieldsets = (
        (None, {"fields": ("name", "kind", "query", "region", "is_active", "notes"),
                "description": "Соцсети — только подсказки: по ним ничего не публикуется без подтверждения "
                               "от СМИ или официального источника. Сборщики включаются в «Настройках»."}),
        ("Состояние", {"fields": ("last_fetched_at", "last_success_at", "consecutive_failures", "last_error",
                                  "last_message_id")}),
    )

    @admin.display(description="запрос / канал")
    def query_short(self, obj):
        return obj.query if len(obj.query) <= 70 else obj.query[:70] + "…"

    @admin.display(description="состояние")
    def health(self, obj):
        if obj.consecutive_failures:
            return format_html('<span style="color:#c0392b">ошибок: {}</span>', obj.consecutive_failures)
        if not obj.last_success_at:
            return mark_safe('<span style="color:#888">ещё не собирали</span>')
        return mark_safe('<span style="color:#1e7e34">ok</span>')


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ("text_short", "source", "author", "status", "region", "topic", "link", "fetched_at")
    list_filter = ("status", "source__kind", "region", "topic")
    search_fields = ("text", "author", "url")
    list_select_related = ("source", "region", "topic")
    readonly_fields = [f.name for f in Signal._meta.fields]

    def has_add_permission(self, request):
        return False

    @admin.display(description="текст")
    def text_short(self, obj):
        return obj.text[:90]

    @admin.display(description="ссылка")
    def link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">открыть ↗</a>', obj.url)


class SignalInline(admin.TabularInline):
    model = Signal
    fields = ("link", "source", "author", "text", "published_at")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="ссылка")
    def link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">открыть ↗</a>', obj.url)


@admin.action(description="❌ Отклонить подсказку")
def action_dismiss(modeladmin, request, queryset):
    n = queryset.filter(status=Hint.Status.OPEN).update(status=Hint.Status.DISMISSED)
    modeladmin.message_user(request, f"Отклонено: {n}", messages.WARNING)


@admin.action(description="🔎 Проверить подтверждение сейчас")
def action_confirm(modeladmin, request, queryset):
    say = RunLog()
    stats = confirm_hints(say)
    for line in say.lines:
        modeladmin.message_user(request, line)
    modeladmin.message_user(request, f"Подтверждено: {stats['confirmed']}", messages.SUCCESS)


@admin.register(Hint)
class HintAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "region", "topic", "n_signals", "story_link", "created_at")
    list_filter = ("status", "region", "topic")
    search_fields = ("title", "summary")
    readonly_fields = ("story_link", "created_at", "confirmed_at")
    fields = ("title", "summary", "region", "topic", "status", "story_link", "created_at", "confirmed_at")
    inlines = [SignalInline]
    actions = [action_dismiss, action_confirm]

    def has_add_permission(self, request):
        return False

    @admin.display(description="сигналов")
    def n_signals(self, obj):
        return obj.signals.count()

    @admin.display(description="подтверждающий сюжет")
    def story_link(self, obj):
        if not obj.story_id:
            return mark_safe('<span style="color:#888">нет — ждём СМИ или официальный источник</span>')
        return format_html('<a href="/admin/news/story/{}/change/">{}</a>', obj.story_id, obj.story.title)


def social_buzz(story) -> str:
    """Блок «Обсуждают в соцсетях» для карточки сюжета в админке."""
    signals = list(story.signals.select_related("source")[:20])
    if not signals:
        return mark_safe('<span style="color:#888">—</span>')
    return format_html("<b>Обсуждают в соцсетях</b><ul>{}</ul>", format_html_join(
        "", '<li><a href="{}" target="_blank" rel="noopener">{}</a> — {}</li>',
        ((s.url, s.author or s.source.get_kind_display(), s.text[:120]) for s in signals),
    ))
