"""Сериализаторы разделов сайта: афиша, справочник, гайды, объявления, комментарии, соцсигналы."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from classifieds.models import LIFETIME, Ad
from classifieds.models import Category as AdCategory
from classifieds.models import Photo as AdPhoto
from comments.models import Comment
from core.models import Author, SiteSettings
from directory.models import Category, Listing, Submission
from events.models import Event
from gallery.models import MediaItem
from guides.models import Guide, GuideSource
from news.models import Article, Region, Tag, Topic
from social.models import Hint, SignalSource

from .media import MediaBriefSerializer, import_media, media_fields, resolve_media


def absolute(path: str) -> str:
    return path if not path or path.startswith("http") else f"{settings.SITE_URL}{path}"


def region_field():
    return serializers.SlugRelatedField(slug_field="slug", queryset=Region.objects.all(), required=False,
                                        allow_null=True, help_text="slug региона: GET /api/v1/regions/")


# --- Афиша ---------------------------------------------------------------------------------------

class EventSerializer(serializers.ModelSerializer):
    region = region_field()
    page_url = serializers.SerializerMethodField()
    locals().update(media_fields("image", MediaItem.Kind.PHOTO, "Картинка афиши"))
    image_remove = serializers.BooleanField(write_only=True, required=False, help_text="true — убрать картинку")

    class Meta:
        model = Event
        fields = ["id", "slug", "status", "title", "description", "starts_on", "starts_at", "ends_on", "venue",
                  "address", "city", "region", "price", "url", "organizer", "language",
                  "image", "image_url", "image_file", "image_caption", "image_credit", "image_remove",
                  "image_status", "contact_name", "contact_email", "violation", "reason", "public_reason",
                  "created_at", "moderated_at", "page_url"]
        read_only_fields = ["slug", "image_status", "violation", "reason", "public_reason", "created_at",
                            "moderated_at"]
        extra_kwargs = {
            "status": {"required": False, "help_text": "approved — сразу на сайте (по умолчанию), pending — "
                                                       "на проверку ИИ, rejected — снято"},
            "language": {"help_text": "пусто — обе версии сайта; ru или uk — только эта версия, текст пишите "
                                      "на её языке (без ИИ-перевода)"},
            "address": {"required": False, "allow_blank": True},
            "organizer": {"required": False, "allow_blank": True},
            "contact_name": {"required": False, "allow_blank": True},
            "contact_email": {"required": False, "allow_blank": True},
        }

    def get_fields(self):
        fields = super().get_fields()
        # image_url в ответе — адрес опубликованной картинки; на запись — ссылка для загрузки (см. media_fields).
        fields["image_url"] = serializers.CharField(
            required=False, allow_blank=True, max_length=1000,
            help_text="Чтение: адрес картинки на сайте. Запись: ссылка на картинку — скачаем и поставим")
        fields.pop("image", None)
        fields["image"] = serializers.PrimaryKeyRelatedField(
            queryset=MediaItem.objects.filter(kind=MediaItem.Kind.PHOTO), required=False, allow_null=True,
            write_only=True, help_text="id фото из медиатеки")
        return fields

    def get_page_url(self, obj) -> str:
        return absolute(obj.get_absolute_url()) if obj.slug and obj.status == Event.Status.APPROVED else ""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["image_url"] = instance.image_url
        return data

    def validate(self, attrs):
        starts = attrs.get("starts_on") or getattr(self.instance, "starts_on", None)
        ends = attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        if starts and ends and ends < starts:
            raise serializers.ValidationError({"ends_on": "Окончание раньше начала"})
        title = attrs.get("title") or getattr(self.instance, "title", "")
        resolve_media(attrs, "image", MediaItem.Kind.PHOTO, title)
        return attrs

    @staticmethod
    def _apply_image(event, image, remove):
        if remove:
            event.image_url, event.image_file_id, event.image_status = "", "", Event.ImageStatus.NONE
        elif image is not None:
            event.image_url, event.image_file_id = image.url, ""
            event.image_status, event.image_note, event.image_data = Event.ImageStatus.PUBLISHED, "", None

    def _finish(self, event, image, remove, fresh: bool):
        self._apply_image(event, image, remove)
        if event.status == Event.Status.APPROVED:
            if not event.slug:
                event.slug = event.make_unique_slug()
            if fresh or not event.moderated_at:
                event.moderated_at = timezone.now()
                event.violation = "none"
                event.reason = event.reason or f"Добавлено через API ({self.context['request'].user})"
        event.save()
        return event

    @transaction.atomic
    def create(self, validated):
        image, remove = validated.pop("image", None), validated.pop("image_remove", False)
        validated.pop("image_url", None)
        validated.setdefault("status", Event.Status.APPROVED)
        validated.setdefault("contact_name", "Редакция")
        validated.setdefault("contact_email", SiteSettings.load().contact_email or "info@florida-ru.com")
        validated.setdefault("organizer", "")
        validated.setdefault("address", "")
        event = Event(**validated)
        return self._finish(event, image, remove, fresh=True)

    @transaction.atomic
    def update(self, event, validated):
        image, remove = validated.pop("image", None), validated.pop("image_remove", False)
        validated.pop("image_url", None)
        for key, value in validated.items():
            setattr(event, key, value)
        return self._finish(event, image, remove, fresh=False)


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000,
                                   help_text="Почему (для журнала; заявителю — public_reason)")
    public_reason = serializers.CharField(required=False, allow_blank=True, max_length=2000,
                                          help_text="Что показать заявителю")


# --- Справочник ----------------------------------------------------------------------------------

class DirectoryCategorySerializer(serializers.ModelSerializer):
    listings_count = serializers.IntegerField(read_only=True, required=False)
    page_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "kind", "slug", "name", "description", "schema_type", "order", "listings_count", "page_url"]
        extra_kwargs = {"slug": {"required": False, "help_text": "латиница; если не указать — из названия"}}

    def get_page_url(self, obj) -> str:
        return absolute(obj.get_absolute_url())

    def validate(self, attrs):
        if not attrs.get("slug") and not self.instance:
            from core.text import make_slug

            base = make_slug(attrs.get("name", ""), max_length=70) or "razdel"
            slug, n = base, 2
            while Category.objects.filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            attrs["slug"] = slug
        return attrs


class ListingSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", queryset=Category.objects.all(),
                                            help_text="slug категории: GET /api/v1/directory/categories/")
    region = region_field()
    locals().update(media_fields("photo", MediaItem.Kind.PHOTO, "Фото или логотип"))
    photo_info = MediaBriefSerializer(source="photo", read_only=True)
    page_url = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = ["id", "category", "name", "description", "url", "phone", "address", "city", "region",
                  "languages", "hours", "guide_slug", "is_recommended", "is_partner", "is_active", "from_owner",
                  "editor_note", "order", "photo", "photo_url", "photo_file", "photo_caption", "photo_credit",
                  "photo_info", "created_at", "updated_at", "page_url"]
        read_only_fields = ["created_at", "updated_at"]
        # без default в multipart отсутствующая галочка считается false — и запись пропала бы с сайта
        extra_kwargs = {"is_active": {"default": True}}

    def get_page_url(self, obj) -> str:
        return absolute(obj.get_absolute_url() or "")

    def validate(self, attrs):
        resolve_media(attrs, "photo", MediaItem.Kind.PHOTO, attrs.get("name") or getattr(self.instance, "name", ""))
        return attrs


class SubmissionSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = Submission
        exclude = ["token", "ip_hash"]
        read_only_fields = [f.name for f in Submission._meta.fields]


class SubmissionApproveSerializer(serializers.Serializer):
    category = serializers.SlugRelatedField(slug_field="slug", queryset=Category.objects.all(), required=False,
                                            help_text="Другая категория (по умолчанию — выбранная заявителем)")
    region = region_field()
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000,
                                        help_text="Описание для справочника (по умолчанию — от заявителя)")


# --- Гайды ---------------------------------------------------------------------------------------

class GuideSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuideSource
        fields = ["name", "url", "title"]


class GuideSerializer(serializers.ModelSerializer):
    sources = GuideSourceSerializer(many=True, required=False)
    topics = serializers.SlugRelatedField(slug_field="slug", queryset=Topic.objects.all(), many=True, required=False)
    page_url = serializers.SerializerMethodField()

    class Meta:
        model = Guide
        fields = ["id", "title", "slug", "teaser", "body", "status", "section", "order", "cover", "topics", "brief",
                  "official_domains", "sources", "review_notes", "human_reviewed", "reviewed_at", "created_at",
                  "updated_at", "revised_at", "published_at", "telegram_posted_at", "page_url"]
        read_only_fields = ["review_notes", "reviewed_at", "created_at", "updated_at", "revised_at",
                            "published_at", "telegram_posted_at"]
        extra_kwargs = {
            "slug": {"required": False},
            "status": {"read_only": True, "help_text": "Меняется действиями publish / unpublish"},
            "body": {"help_text": "Текст в разметке гайдов: ## заголовки, абзацы, списки «- », ссылки [текст](url)"},
        }

    def get_page_url(self, obj) -> str:
        return absolute(obj.get_absolute_url())

    def validate(self, attrs):
        if "human_reviewed" in attrs:
            attrs["reviewed_at"] = timezone.now() if attrs["human_reviewed"] else None
        return attrs

    @transaction.atomic
    def create(self, validated):
        sources, topics = validated.pop("sources", []), validated.pop("topics", [])
        guide = Guide.objects.create(**validated)
        guide.topics.set(topics)
        self._sources(guide, sources)
        return guide

    @transaction.atomic
    def update(self, guide, validated):
        sources, topics = validated.pop("sources", None), validated.pop("topics", None)
        if guide.published_at and any(k in validated and validated[k] != getattr(guide, k)
                                      for k in ("title", "teaser", "body")):
            guide.revised_at = timezone.now()
        for key, value in validated.items():
            setattr(guide, key, value)
        if guide.status == Guide.Status.PUBLISHED and not guide.human_reviewed:
            guide.status = Guide.Status.DRAFT
        guide.save()
        if topics is not None:
            guide.topics.set(topics)
        if sources is not None:
            self._sources(guide, sources)
        return guide

    @staticmethod
    def _sources(guide, sources):
        guide.sources.all().delete()
        for order, src in enumerate(sources):
            GuideSource.objects.create(guide=guide, order=order, **src)


# --- Объявления ----------------------------------------------------------------------------------

class AdCategorySerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field="slug", queryset=AdCategory.objects.filter(parent=None),
                                          required=False, allow_null=True,
                                          help_text="slug раздела; пусто — это сам раздел")

    class Meta:
        model = AdCategory
        fields = ["id", "parent", "slug", "name", "description", "price_label", "order"]


class AdPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdPhoto
        fields = ["id", "order", "status", "url", "note"]
        read_only_fields = fields


class AdSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", queryset=AdCategory.objects.exclude(parent=None),
                                            help_text="slug рубрики (не раздела): GET /api/v1/classifieds/categories/")
    region = region_field()
    photos = AdPhotoSerializer(many=True, read_only=True)
    add_photos = serializers.PrimaryKeyRelatedField(
        queryset=MediaItem.objects.filter(kind=MediaItem.Kind.PHOTO), many=True, write_only=True, required=False,
        help_text="id фото из медиатеки — добавятся к объявлению (всего до 5)")
    add_photo_urls = serializers.ListField(child=serializers.CharField(max_length=1000), write_only=True,
                                           required=False, help_text="Ссылки на фото — добавятся к объявлению")
    page_url = serializers.SerializerMethodField()

    class Meta:
        model = Ad
        fields = ["id", "slug", "status", "category", "title", "description", "price", "price_unit", "city",
                  "zip_code", "region", "contact_name", "phone", "has_whatsapp", "telegram", "photos", "add_photos",
                  "add_photo_urls", "violation", "reason", "public_reason", "views", "contact_views", "created_at",
                  "moderated_at", "published_at", "expires_at", "closed_at", "page_url"]
        read_only_fields = ["slug", "violation", "reason", "public_reason", "views", "contact_views", "created_at",
                            "moderated_at", "published_at", "closed_at"]
        extra_kwargs = {"status": {"required": False, "help_text": "approved — сразу на сайте на 30 дней "
                                                                   "(по умолчанию), pending — на проверку ИИ"},
                        "expires_at": {"required": False}}

    def get_page_url(self, obj) -> str:
        return absolute(obj.get_absolute_url()) if obj.is_public else ""

    def validate(self, attrs):
        title = attrs.get("title") or getattr(self.instance, "title", "")
        photos = list(attrs.pop("add_photos", []))
        photos += [import_media(url=u, kind=MediaItem.Kind.PHOTO, meta={"title": title}, field="add_photo_urls")
                   for u in attrs.pop("add_photo_urls", []) if u.strip()]
        have = self.instance.photos.exclude(status=AdPhoto.Status.REJECTED).count() if self.instance else 0
        from classifieds.models import MAX_PHOTOS

        if have + len(photos) > MAX_PHOTOS:
            raise serializers.ValidationError({"add_photos": f"У объявления может быть до {MAX_PHOTOS} фото"})
        attrs["_photos"] = photos
        return attrs

    @staticmethod
    def _add_photos(ad, photos):
        start = (ad.photos.order_by("-order").values_list("order", flat=True).first() or -1) + 1
        for n, item in enumerate(photos):
            AdPhoto.objects.create(ad=ad, order=start + n, status=AdPhoto.Status.PUBLISHED, url=item.url,
                                   note="Добавлено через API")

    @staticmethod
    def _publish(ad):
        now = timezone.now()
        ad.moderated_at = ad.moderated_at or now
        if not ad.published_at:
            ad.published_at = now
        if not ad.expires_at:
            ad.expires_at = now + LIFETIME

    @transaction.atomic
    def create(self, validated):
        photos = validated.pop("_photos", [])
        validated.setdefault("status", Ad.Status.APPROVED)
        ad = Ad(**validated)
        if ad.status == Ad.Status.APPROVED:
            self._publish(ad)
            ad.violation, ad.reason = "none", f"Добавлено через API ({self.context['request'].user})"
        ad.save()
        self._add_photos(ad, photos)
        return ad

    @transaction.atomic
    def update(self, ad, validated):
        photos = validated.pop("_photos", [])
        for key, value in validated.items():
            setattr(ad, key, value)
        if ad.status == Ad.Status.APPROVED:
            self._publish(ad)
        ad.save()
        self._add_photos(ad, photos)
        return ad


# --- Комментарии и отзывы ------------------------------------------------------------------------

class CommentSerializer(serializers.ModelSerializer):
    article = serializers.PrimaryKeyRelatedField(queryset=Article.objects.all(), required=False, allow_null=True)
    listing = serializers.PrimaryKeyRelatedField(queryset=Listing.objects.all(), required=False, allow_null=True)
    page_url = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "article", "listing", "status", "name", "email", "text", "rating", "violation", "reason",
                  "public_reason", "reports", "created_at", "moderated_at", "page_url"]
        read_only_fields = ["violation", "reason", "public_reason", "reports", "created_at", "moderated_at"]
        extra_kwargs = {"status": {"required": False}, "name": {"required": False},
                        "email": {"required": False}}

    def get_page_url(self, obj) -> str:
        return absolute(obj.get_absolute_url())

    def validate(self, attrs):
        article = attrs.get("article", getattr(self.instance, "article", None))
        listing = attrs.get("listing", getattr(self.instance, "listing", None))
        if bool(article) == bool(listing):
            raise serializers.ValidationError("Укажите что-то одно: article (id новости) или listing (id бизнеса)")
        rating = attrs.get("rating")
        if rating is not None and not 1 <= rating <= 5:
            raise serializers.ValidationError({"rating": "Оценка от 1 до 5"})
        return attrs

    def create(self, validated):
        validated.setdefault("status", Comment.Status.APPROVED)
        validated.setdefault("name", "Редакция")
        validated.setdefault("email", SiteSettings.load().contact_email or "info@florida-ru.com")
        validated["moderated_at"] = timezone.now()
        validated["violation"] = "none"
        validated["reason"] = f"Добавлено через API ({self.context['request'].user})"
        return Comment.objects.create(**validated)


# --- Остальное -----------------------------------------------------------------------------------

class TagSerializer(serializers.ModelSerializer):
    articles_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Tag
        fields = ["id", "name", "slug", "articles_count"]
        read_only_fields = ["slug"]


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name", "slug", "role", "bio", "photo", "is_active", "order"]


class SignalSourceSerializer(serializers.ModelSerializer):
    region = region_field()

    class Meta:
        model = SignalSource
        fields = "__all__"
        read_only_fields = ["last_fetched_at", "last_success_at", "consecutive_failures", "last_error",
                            "last_message_id"]


class HintSerializer(serializers.ModelSerializer):
    region = region_field()
    topic = serializers.SlugRelatedField(slug_field="slug", queryset=Topic.objects.all(), required=False,
                                         allow_null=True)

    class Meta:
        model = Hint
        fields = ["id", "title", "summary", "region", "topic", "status", "story", "created_at", "confirmed_at",
                  "updated_at"]
        read_only_fields = ["story", "created_at", "confirmed_at", "updated_at"]
