from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from core.models import SiteSettings

from .budget import current_budget
from .models import AICall, PipelineRun
from .runner import AlreadyRunning, active_run, spawn_pipeline


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
    change_list_template = "admin/pipeline/pipelinerun_change_list.html"

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        run_now = self.admin_site.admin_view(self.run_now_view)
        return [path("run-now/", run_now, name="pipeline_pipelinerun_run_now"), *super().get_urls()]

    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "active_run": active_run(),
            "can_run": self.has_change_permission(request),
        }
        return super().changelist_view(request, extra_context=extra_context)

    def run_now_view(self, request):
        """Кнопка «Запустить конвейер»: тот же проход, что cron делает дважды в день."""
        changelist = reverse("admin:pipeline_pipelinerun_changelist")
        if request.method != "POST":
            return HttpResponseRedirect(changelist)
        if not self.has_change_permission(request):
            raise PermissionDenied
        write = request.POST.get("mode") != "fetch"
        try:
            run = spawn_pipeline(write=write, source=f"admin:{request.user.get_username()}")
        except AlreadyRunning as busy:
            self.message_user(request, f"Конвейер уже работает (запуск от {busy.run}) — дождитесь конца.",
                              messages.WARNING)
            return HttpResponseRedirect(changelist)
        except OSError as exc:
            self.message_user(request, f"Не удалось запустить конвейер: {exc}", messages.ERROR)
            return HttpResponseRedirect(changelist)
        what = "Конвейер запущен" if write else "Сбор и склейка запущены (без ИИ)"
        self.message_user(request, f"{what}. Обычно это занимает несколько минут — обновите страницу, "
                                   f"итоги и журнал появятся в записи «{run}».", messages.SUCCESS)
        return HttpResponseRedirect(changelist)
