"""API удалённого управления сайтом. Документация: /api/docs/ (Swagger)."""

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.templatetags.static import static
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from ads.models import AdBanner
from core.models import Page, SiteSettings
from news.covers import cover_pools, describe
from news.models import Article, Region, Topic
from pipeline.budget import current_budget
from pipeline.models import AICall, PipelineRun
from pipeline.services import publish_article, reject_article
from pipeline.telegram import post_article
from sources.fetch import check_source, fetch_all
from sources.models import Source, WeatherAlert

from . import serializers as s
from .runner import AlreadyRunning, start_pipeline


@extend_schema(parameters=[
    OpenApiParameter("status", str, description="review / published / rejected / draft"),
    OpenApiParameter("region", str, description="slug региона"),
    OpenApiParameter("topic", str, description="slug темы"),
    OpenApiParameter("urgent", bool),
    OpenApiParameter("q", str, description="поиск по заголовку и тексту"),
])
class ArticleViewSet(viewsets.ModelViewSet):
    """Заметки: список с фильтрами, создание, правка, удаление, публикация."""

    serializer_class = s.ArticleSerializer

    def get_queryset(self):
        qs = (Article.objects.select_related("region", "topic").prefetch_related("tags", "sources")
              .order_by("-created_at"))
        params = self.request.query_params
        if value := params.get("status"):
            qs = qs.filter(status=value)
        if value := params.get("region"):
            qs = qs.filter(region__slug=value)
        if value := params.get("topic"):
            qs = qs.filter(topic__slug=value)
        if params.get("urgent") in ("1", "true"):
            qs = qs.filter(is_urgent=True)
        if value := params.get("q"):
            qs = qs.filter(Q(title__icontains=value) | Q(body__icontains=value) | Q(teaser__icontains=value))
        return qs

    @extend_schema(request=None, responses=s.ArticleSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Опубликовать на сайте (и отправить в Telegram, если он включён)."""
        article = publish_article(self.get_object())
        return Response(self.get_serializer(article).data)

    @extend_schema(request=None, responses=s.ArticleSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Отклонить / снять с сайта."""
        article = reject_article(self.get_object())
        return Response(self.get_serializer(article).data)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def telegram(self, request, pk=None):
        """Отправить опубликованную заметку в Telegram (повторно не отправляет)."""
        article = self.get_object()
        if article.status != Article.Status.PUBLISHED:
            return Response({"detail": "Сначала опубликуйте заметку"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = post_article(article)
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"result": result})


class SourceViewSet(viewsets.ModelViewSet):
    """Источники новостей: включение, вес доверия, проверка фида, сбор."""

    queryset = Source.objects.select_related("region").order_by("source_type", "name")
    serializer_class = s.SourceSerializer

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def check(self, request, pk=None):
        """Проверить, что адрес отдаёт RSS/Atom. С ?activate=1 — включить/выключить по итогам."""
        source = self.get_object()
        ok, detail = check_source(source)
        source.is_verified = ok
        source.verified_at = timezone.now()
        if request.query_params.get("activate") in ("1", "true"):
            source.is_active = ok
            if ok:
                source.is_broken, source.consecutive_failures = False, 0
        source.save()
        return Response({"ok": ok, "detail": detail, "source": self.get_serializer(source).data})

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def fetch(self, request, pk=None):
        """Собрать новые записи из этого источника прямо сейчас (без ИИ)."""
        result = fetch_all(Source.objects.filter(pk=self.get_object().pk), include_broken=True)[0]
        return Response({"created": result.created, "skipped": result.skipped,
                         "not_modified": result.not_modified, "error": result.error})

    @extend_schema(request=None, responses=s.SourceSerializer)
    @action(detail=True, methods=["post"])
    def reset(self, request, pk=None):
        """Сбросить счётчик ошибок и отметку «сломан»."""
        source = self.get_object()
        source.is_broken, source.consecutive_failures, source.last_error = False, 0, ""
        source.save()
        return Response(self.get_serializer(source).data)


class WeatherAlertViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Погодные предупреждения. Можно скрыть предупреждение с сайта (is_hidden)."""

    queryset = WeatherAlert.objects.order_by("-is_active", "-effective")
    serializer_class = s.WeatherAlertSerializer
    http_method_names = ["get", "patch"]


class AdBannerViewSet(viewsets.ModelViewSet):
    """Рекламные блоки. Картинку загружайте как multipart/form-data, поле image."""

    queryset = AdBanner.objects.select_related("region")
    serializer_class = s.AdBannerSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]


class PageViewSet(viewsets.ModelViewSet):
    """Статические страницы: «О проекте», «Реклама», «Контакты», политика и т.д."""

    queryset = Page.objects.all()
    serializer_class = s.PageSerializer
    lookup_field = "slug"


class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Region.objects.all()
    serializer_class = s.RegionSerializer
    lookup_field = "slug"
    pagination_class = None


class TopicViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = s.TopicSerializer
    lookup_field = "slug"
    pagination_class = None


class PipelineViewSet(viewsets.ReadOnlyModelViewSet):
    """Запуски конвейера: история и запуск нового прохода в фоне."""

    queryset = PipelineRun.objects.all()
    serializer_class = s.PipelineRunSerializer

    @extend_schema(request=s.PipelineStartSerializer, responses={202: s.PipelineRunSerializer, 409: dict})
    @action(detail=False, methods=["post"])
    def run(self, request):
        """Запустить конвейер сейчас. Ответ сразу, ход — в GET /pipeline/{id}/."""
        params = s.PipelineStartSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        try:
            run = start_pipeline(**params.validated_data)
        except AlreadyRunning as busy:
            return Response({"detail": "Конвейер уже работает", "run": s.PipelineRunSerializer(busy.run).data},
                            status=status.HTTP_409_CONFLICT)
        return Response(s.PipelineRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class SettingsView(APIView):
    """Настройки сайта и конвейера: пороги, лимиты, Telegram, AdSense."""

    @extend_schema(responses=s.SiteSettingsSerializer)
    def get(self, request):
        return Response(s.SiteSettingsSerializer(SiteSettings.load()).data)

    @extend_schema(request=s.SiteSettingsSerializer, responses=s.SiteSettingsSerializer)
    def patch(self, request):
        serializer = s.SiteSettingsSerializer(SiteSettings.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StatsView(APIView):
    """Сводка: заметки, расходы на ИИ, лимиты, источники, последний запуск."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        day_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

        def costs(qs):
            agg = qs.aggregate(cost=Sum("cost_usd"), calls=Count("id"))
            return {"usd": str(agg["cost"] or 0), "calls": agg["calls"],
                    "by_purpose": {row["purpose"]: str(row["cost"]) for row in
                                   qs.values("purpose").annotate(cost=Sum("cost_usd"))}}

        budget = current_budget()
        last = PipelineRun.objects.first()
        return Response({
            "articles": {
                "by_status": dict(Article.objects.values_list("status").annotate(n=Count("id"))),
                "published_today": Article.objects.filter(published_at__gte=day_start).count(),
            },
            "ai": {
                "provider": settings.AI_PROVIDER,
                "today": costs(AICall.objects.today()),
                "month": costs(AICall.objects.this_month()),
                "budget_usd": str(budget.budget),
                "articles_today": budget.articles_today,
                "max_articles": budget.max_articles,
                "urgent_only": budget.urgent_only,
            },
            "sources": {
                "active": Source.objects.filter(is_active=True).count(),
                "broken": Source.objects.filter(is_broken=True).count(),
                "total": Source.objects.count(),
            },
            "weather_alerts_active": WeatherAlert.objects.filter(is_active=True, is_hidden=False).count(),
            "last_run": s.PipelineRunSerializer(last).data if last else None,
        })


class CoversView(APIView):
    """Все обложки с описаниями — id подходит для поля cover_image заметки."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({
            pool: [{"id": c.base, "is_photo": c.is_photo, "description": describe(c),
                    "url": f"{settings.SITE_URL}{static(c.base + '-640.webp')}"} for c in covers]
            for pool, covers in sorted(cover_pools().items())
        })
