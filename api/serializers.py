from django.conf import settings
from django.db import transaction
from django.templatetags.static import static
from django.utils import timezone
from rest_framework import serializers

from ads.models import AdBanner
from core.models import Page, SiteSettings
from guides.models import Guide
from news.covers import all_covers
from news.models import Article, ArticleSource, Region, Tag, Topic
from pipeline.models import PipelineRun
from sources.models import Source, WeatherAlert


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ["slug", "name", "name_locative", "is_statewide", "order"]


class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ["slug", "name", "short_name", "priority", "order"]


class ArticleSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleSource
        fields = ["name", "url", "title"]


class ArticleSerializer(serializers.ModelSerializer):
    region = serializers.SlugRelatedField(slug_field="slug", queryset=Region.objects.all(),
                                          required=False, allow_null=True)
    topic = serializers.SlugRelatedField(slug_field="slug", queryset=Topic.objects.all(),
                                         required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=60), required=False, write_only=True)
    sources = ArticleSourceSerializer(many=True, required=False)
    url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    guide = serializers.SlugRelatedField(slug_field="slug", queryset=Guide.objects.all(), required=False,
                                         allow_null=True)

    class Meta:
        model = Article
        fields = [
            "id", "title", "slug", "teaser", "body", "for_you", "guide", "status", "region", "topic", "business_kind",
            "tags", "sources",
            "is_urgent", "is_sensitive", "score", "cover_image", "cover_manual", "cover_url", "review_reason",
            "verification", "published_at", "revised_at", "created_at", "updated_at", "telegram_posted_at", "url",
        ]
        read_only_fields = ["slug", "review_reason", "verification", "revised_at", "created_at", "updated_at",
                            "telegram_posted_at", "cover_manual"]
        extra_kwargs = {"status": {"required": False}}

    def get_url(self, obj) -> str:
        return f"{settings.SITE_URL}{obj.get_absolute_url()}"

    def get_cover_url(self, obj) -> str:
        return f"{settings.SITE_URL}{static(obj.cover + '.webp')}"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["tags"] = [t.name for t in instance.tags.all()]
        return data

    def validate_cover_image(self, value):
        if value and value not in all_covers():
            raise serializers.ValidationError("Нет такой обложки. Список: GET /api/v1/covers/")
        return value

    @transaction.atomic
    def create(self, validated):
        tags = validated.pop("tags", [])
        sources = validated.pop("sources", [])
        validated.setdefault("status", Article.Status.DRAFT)
        if validated["status"] == Article.Status.PUBLISHED and not validated.get("published_at"):
            validated["published_at"] = timezone.now()
        validated["cover_manual"] = bool(validated.get("cover_image"))
        article = Article.objects.create(**validated)
        self._save_relations(article, tags, sources)
        return article

    @transaction.atomic
    def update(self, article, validated):
        tags = validated.pop("tags", None)
        sources = validated.pop("sources", None)
        if article.published_at and any(
                key in validated and validated[key] != getattr(article, key) for key in ("title", "teaser", "body", "for_you")):
            article.revised_at = timezone.now()
        if "cover_image" in validated and validated["cover_image"] != article.cover_image:
            article.cover_manual = bool(validated["cover_image"])
        for key, value in validated.items():
            setattr(article, key, value)
        if article.status == Article.Status.PUBLISHED and not article.published_at:
            article.published_at = timezone.now()
        article.save()
        self._save_relations(article, tags, sources)
        return article

    @staticmethod
    def _save_relations(article, tags, sources):
        if tags is not None:
            article.tags.set([
                Tag.objects.filter(name__iexact=n.strip()).first() or Tag.objects.create(name=n.strip())
                for n in tags if n.strip()
            ])
        if sources is not None:
            article.sources.all().delete()
            for order, src in enumerate(sources):
                ArticleSource.objects.create(article=article, order=order, **src)


class SourceSerializer(serializers.ModelSerializer):
    region = serializers.SlugRelatedField(slug_field="slug", queryset=Region.objects.all(),
                                          required=False, allow_null=True)

    class Meta:
        model = Source
        exclude = ["etag", "last_modified"]
        read_only_fields = ["is_verified", "verified_at", "last_fetched_at", "last_success_at",
                            "consecutive_failures", "last_error"]


class WeatherAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeatherAlert
        fields = ["id", "event", "event_ru", "headline", "area", "severity", "url", "effective",
                  "expires", "is_active", "is_hidden"]
        read_only_fields = [f for f in fields if f != "is_hidden"]


class AdBannerSerializer(serializers.ModelSerializer):
    region = serializers.SlugRelatedField(slug_field="slug", queryset=Region.objects.all(),
                                          required=False, allow_null=True)

    class Meta:
        model = AdBanner
        fields = ["id", "advertiser", "slot", "image", "headline", "url", "region", "starts_at",
                  "ends_at", "is_active", "priority", "created_at"]
        read_only_fields = ["created_at"]


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ["slug", "title", "body", "in_footer", "order", "updated_at"]
        read_only_fields = ["updated_at"]


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        exclude = ["id"]


class PipelineRunSerializer(serializers.ModelSerializer):
    running = serializers.SerializerMethodField()

    class Meta:
        model = PipelineRun
        fields = ["id", "started_at", "finished_at", "running", "success", "stats", "log"]

    def get_running(self, obj) -> bool:
        return obj.finished_at is None


class PipelineStartSerializer(serializers.Serializer):
    fetch = serializers.BooleanField(default=True, help_text="Собирать фиды")
    write = serializers.BooleanField(default=True, help_text="Отбирать и писать заметки (тратит ИИ)")


class CoverBatchSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), required=False,
                                help_text="Конкретные заметки. Если заданы, остальные условия не применяются")
    only_empty = serializers.BooleanField(default=True,
                                          help_text="Только заметки без выбранной обложки (обложка по очереди)")
    status = serializers.ChoiceField(choices=Article.Status.choices, default=Article.Status.PUBLISHED)
    topic = serializers.SlugField(required=False, help_text="slug темы")
    limit = serializers.IntegerField(default=50, min_value=1, max_value=500, help_text="Сколько заметок, новые первыми")

    def article_ids(self) -> list[int]:
        data = self.validated_data
        if data.get("ids"):
            return list(Article.objects.filter(pk__in=data["ids"]).values_list("pk", flat=True))
        qs = Article.objects.filter(status=data["status"])
        if data["only_empty"]:
            qs = qs.filter(cover_image="")
        if data.get("topic"):
            qs = qs.filter(topic__slug=data["topic"])
        return list(qs.order_by("-published_at", "-created_at").values_list("pk", flat=True)[:data["limit"]])
