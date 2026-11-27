from datetime import timedelta

from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from pipeline.models import AICall

from .assistant import PURPOSES
from .models import STALE_DAYS, AssistantSettings, Chunk, Question, Reader, Source


@admin.register(AssistantSettings)
class AssistantSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "enabled", "daily_questions", "monthly_budget_usd", "retention_days")
    list_editable = ("enabled",)
    list_display_links = ("__str__",)

    def has_add_permission(self, request):
        return not AssistantSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class FreshnessFilter(admin.SimpleListFilter):
    title = "свежесть"
    parameter_name = "fresh"

    def lookups(self, request, model_admin):
        return [("stale", f"не проверялся > {STALE_DAYS} дней"), ("broken", "не скачивается")]

    def queryset(self, request, queryset):
        if self.value() == "stale":
            border = timezone.now() - timedelta(days=STALE_DAYS)
            return queryset.filter(checked_at__lt=border) | queryset.filter(checked_at__isnull=True)
        if self.value() == "broken":
            return queryset.exclude(status=Source.Status.OK)
        return queryset


class ChunkInline(admin.TabularInline):
    model = Chunk
    extra = 0
    fields = ("position", "section", "text")
    readonly_fields = ("position", "section", "text")
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("title", "agency", "kind", "status", "n_chunks", "checked_at", "changed_at", "fresh", "is_active")
    list_filter = (FreshnessFilter, "status", "agency", "kind", "is_active", "language")
    search_fields = ("title", "url")
    readonly_fields = ("content_hash", "fetched_at", "checked_at", "changed_at", "last_error", "status")
    list_editable = ("is_active",)
    inlines = [ChunkInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_chunks=Count("chunks"))

    @admin.display(description="фрагментов", ordering="_chunks")
    def n_chunks(self, obj):
        return obj._chunks

    @admin.display(description="свежий", boolean=True)
    def fresh(self, obj):
        return not obj.is_stale


@admin.action(description="Отметить «разобрано»")
def mark_reviewed(modeladmin, request, queryset):
    queryset.update(reviewed=True)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Вопросы читателей. Сверху — расход и число вопросов; фильтр «👎 не разобрано» — очередь на разбор."""

    list_display = ("created_at", "short_question", "kind", "language", "feedback", "reviewed", "cost_usd")
    list_filter = ("feedback", "reviewed", "kind", "language")
    search_fields = ("question", "answer")
    readonly_fields = ("user", "language", "question", "kind", "answer", "sources", "lawyers", "search_query",
                       "cost_usd", "feedback", "created_at")
    actions = [mark_reviewed]
    change_list_template = "admin/immigration/question/change_list.html"

    def has_add_permission(self, request):
        return False

    @admin.display(description="вопрос")
    def short_question(self, obj):
        return obj.question[:90]

    def changelist_view(self, request, extra_context=None):
        calls = AICall.objects.filter(purpose__in=PURPOSES)
        conf = AssistantSettings.load()
        month = calls.this_month().total_cost()
        stale_border = timezone.now() - timedelta(days=STALE_DAYS)
        extra_context = {
            **(extra_context or {}),
            "imm_stats": {
                "enabled": conf.enabled,
                "cost_today": calls.today().total_cost(),
                "cost_month": month,
                "budget": conf.monthly_budget_usd,
                "questions_today": Question.objects.today().count(),
                "questions_month": Question.objects.filter(
                    created_at__gte=timezone.localtime().replace(day=1, hour=0, minute=0, second=0)).count(),
                "thumbs_down": Question.objects.filter(feedback=-1, reviewed=False).count(),
                "sources_ok": Source.objects.filter(is_active=True, status=Source.Status.OK).count(),
                "sources_stale": Source.objects.filter(is_active=True, checked_at__lt=stale_border).count(),
                "sources_broken": Source.objects.exclude(status=Source.Status.OK).count(),
                "chunks": Chunk.objects.filter(source__is_active=True).count(),
            },
        }
        return super().changelist_view(request, extra_context)


@admin.register(Reader)
class ReaderAdmin(admin.ModelAdmin):
    list_display = ("__str__", "region", "consent_at", "consent_version", "created_at", "n_questions")
    list_filter = ("region", "consent_version")
    readonly_fields = ("user", "consent_at", "consent_version", "consent_ip", "created_at")
    search_fields = ("user__email",)

    @admin.display(description="вопросов")
    def n_questions(self, obj):
        return format_html("{}", obj.user.immigration_questions.count())
