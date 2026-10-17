from django.contrib import admin
from django.db.models import Count, Sum

from core.models import SiteSettings

from .budget import current_budget
from .models import AICall, PipelineRun


@admin.register(AICall)
class AICallAdmin(admin.ModelAdmin):
    list_display = ("created_at", "purpose", "model", "input_tokens", "output_tokens", "cache_read_tokens",
                    "cost_usd", "success", "story")
    list_filter = ("purpose", "model", "success")
    date_hierarchy = "created_at"
    raw_id_fields = ("story",)
    change_list_template = "admin/pipeline/aicall_change_list.html"

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        def summary(qs):
            agg = qs.aggregate(cost=Sum("cost_usd"), calls=Count("id"), inp=Sum("input_tokens"),
                               out=Sum("output_tokens"), cached=Sum("cache_read_tokens"))
            by_purpose = qs.values("purpose").annotate(cost=Sum("cost_usd"), calls=Count("id")).order_by("purpose")
            return {**agg, "by_purpose": [
                {**row, "label": AICall.Purpose(row["purpose"]).label} for row in by_purpose
            ]}

        conf = SiteSettings.load()
        extra_context = {
            **(extra_context or {}),
            "today": summary(AICall.objects.today()),
            "month": summary(AICall.objects.this_month()),
            "budget": current_budget(conf),
        }
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "finished_at", "success", "stats")
    readonly_fields = ("started_at", "finished_at", "success", "stats", "log")

    def has_add_permission(self, request):
        return False
