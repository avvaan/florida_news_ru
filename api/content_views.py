"""API разделов сайта: медиатека, афиша, справочник, гайды, объявления, комментарии, соцсигналы."""

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from classifieds import moderation as ad_moderation
from classifieds.models import LIFETIME, Ad
from classifieds.models import Category as AdCategory
from classifieds.models import Photo as AdPhoto
from comments import moderation as comment_moderation
from comments.models import Comment
from core import images
from core.models import Author
from directory import moderation as dir_moderation
from directory.models import Category, Listing, Submission
from events import moderation as event_moderation
from events.models import Event
from gallery import services as media_services
from gallery.models import MediaItem
from guides.services import NotReviewed, publish_guide, unpublish_guide
from guides.models import Guide
from news.models import Tag
from social.models import Hint, SignalSource

from . import content_serializers as cs
from .media import MediaItemSerializer

PARSERS = [JSONParser, MultiPartParser, FormParser]


def truthy(value) -> bool:
    return str(value).lower() in ("1", "true", "yes")


def editor(request) -> str:
    return f"редакцией через API ({request.user})"


# --- Медиатека -----------------------------------------------------------------------------------

@extend_schema(parameters=[
    OpenApiParameter("kind", str, description="photo / video"),
    OpenApiParameter("q", str, description="поиск по названию, подписи, автору"),
])
class MediaViewSet(viewsets.ModelViewSet):
    """Фото и видео. Добавить: multipart с полем file или JSON {"source": "<ссылка>"}.

    Ссылки YouTube / Vimeo / Rutube / VK встраиваются плеером; картинки и видеофайлы по ссылке
    скачиваются и хранятся у нас (ImageKit, без него — на диске сайта). Потом id подключается к
    заметке (photo, video, gallery), событию (image), бизнесу (photo), объявлению (add_photos).
    """

    serializer_class = MediaItemSerializer
    parser_classes = PARSERS

    def get_queryset(self):
        qs = MediaItem.objects.all()
        params = self.request.query_params
        if value := params.get("kind"):
            qs = qs.filter(kind=value)
        if value := params.get("q"):
            qs = qs.filter(Q(title__icontains=value) | Q(caption__icontains=value) | Q(credit__icontains=value))
        return qs

    def perform_destroy(self, instance):
        media_services.delete_file(instance)
        instance.delete()


# --- Афиша ---------------------------------------------------------------------------------------

@extend_schema(parameters=[
    OpenApiParameter("status", str, description="pending / approved / rejected"),
    OpenApiParameter("upcoming", bool, description="только предстоящие опубликованные"),
    OpenApiParameter("region", str, description="slug региона"),
    OpenApiParameter("language", str, description="ru / uk — события только для этой версии; all — для обеих"),
    OpenApiParameter("date_from", str, description="ГГГГ-ММ-ДД: начинаются не раньше"),
    OpenApiParameter("date_to", str, description="ГГГГ-ММ-ДД: начинаются не позже"),
    OpenApiParameter("q", str, description="поиск по названию, описанию, месту, организатору"),
])
class EventViewSet(viewsets.ModelViewSet):
    """Афиша «Куда сходить». Событие от API сразу публикуется (status=approved), если не указать иное."""

    serializer_class = cs.EventSerializer
    parser_classes = PARSERS

    def get_queryset(self):
        params = self.request.query_params
        qs = Event.objects.upcoming() if truthy(params.get("upcoming")) else Event.objects.all()
        qs = qs.select_related("region").defer("image_data")
        if value := params.get("status"):
            qs = qs.filter(status=value)
        if value := params.get("region"):
            qs = qs.filter(region__slug=value)
        if value := params.get("language"):
            qs = qs.filter(language="" if value == "all" else value)
        if value := params.get("date_from"):
            qs = qs.filter(starts_on__gte=value)
        if value := params.get("date_to"):
            qs = qs.filter(starts_on__lte=value)
        if value := params.get("q"):
            qs = qs.filter(Q(title__icontains=value) | Q(description__icontains=value) | Q(venue__icontains=value)
                           | Q(organizer__icontains=value) | Q(city__icontains=value))
        return qs

    def perform_destroy(self, instance):
        images.delete(instance.image_file_id)
        instance.delete()

    @extend_schema(request=None, responses=cs.EventSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Опубликовать в афише (без проверки ИИ)."""
        event = self.get_object()
        serializer = self.get_serializer(event, data={"status": Event.Status.APPROVED}, partial=True)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        if event.image_status == Event.ImageStatus.PENDING and event.image_data:
            event_moderation.upload_image(event)
            event.save()
        return Response(self.get_serializer(event).data)

    @extend_schema(request=cs.RejectSerializer, responses=cs.EventSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Снять с афиши и отклонить."""
        params = cs.RejectSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        event = event_moderation.reject(self.get_object(), "other",
                                        params.validated_data.get("reason") or f"Отклонено {editor(request)}",
                                        params.validated_data.get("public_reason", ""))
        return Response(self.get_serializer(event).data)

    @extend_schema(request=None, responses=cs.EventSerializer)
    @action(detail=True, methods=["post"])
    def remoderate(self, request, pk=None):
        """Отдать заявку «на проверке» ИИ прямо сейчас."""
        event = self.get_object()
        if event.status != Event.Status.PENDING:
            return Response({"detail": "Проверяются только заявки со статусом pending"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(event_moderation.moderate(event)).data)


# --- Справочник ----------------------------------------------------------------------------------

@extend_schema(parameters=[OpenApiParameter("kind", str, description="business / links")])
class DirectoryCategoryViewSet(viewsets.ModelViewSet):
    """Разделы (категории) справочника. Адрес раздела: /links/<slug>/."""

    serializer_class = cs.DirectoryCategorySerializer
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self):
        qs = Category.objects.annotate(listings_count=Count("listings", filter=Q(listings__is_active=True)))
        if value := self.request.query_params.get("kind"):
            qs = qs.filter(kind=value)
        return qs


@extend_schema(parameters=[
    OpenApiParameter("category", str, description="slug категории"),
    OpenApiParameter("kind", str, description="business / links"),
    OpenApiParameter("active", bool),
    OpenApiParameter("city", str),
    OpenApiParameter("q", str, description="поиск по названию, описанию, адресу"),
])
class ListingViewSet(viewsets.ModelViewSet):
    """Записи справочника: бизнесы и полезные ссылки."""

    serializer_class = cs.ListingSerializer
    parser_classes = PARSERS

    def get_queryset(self):
        qs = Listing.objects.select_related("category", "region", "photo").order_by("category__order", "order", "name")
        params = self.request.query_params
        if value := params.get("category"):
            qs = qs.filter(category__slug=value)
        if value := params.get("kind"):
            qs = qs.filter(category__kind=value)
        if (value := params.get("active")) is not None:
            qs = qs.filter(is_active=truthy(value))
        if value := params.get("city"):
            qs = qs.filter(city__icontains=value)
        if value := params.get("q"):
            qs = qs.filter(Q(name__icontains=value) | Q(description__icontains=value) | Q(address__icontains=value))
        return qs


@extend_schema(parameters=[OpenApiParameter("status", str, description="pending / approved / rejected")])
class SubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    """Заявки бизнесов через форму на сайте: просмотр, одобрение, отклонение."""

    serializer_class = cs.SubmissionSerializer

    def get_queryset(self):
        qs = Submission.objects.select_related("category", "listing")
        if value := self.request.query_params.get("status"):
            qs = qs.filter(status=value)
        return qs

    @extend_schema(request=cs.SubmissionApproveSerializer, responses=cs.SubmissionSerializer)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Одобрить без ИИ: создаёт запись в справочнике с меткой «Данные от владельца»."""
        sub = self.get_object()
        if sub.listing_id:
            Listing.objects.filter(pk=sub.listing_id).update(is_active=True)
        else:
            params = cs.SubmissionApproveSerializer(data=request.data)
            params.is_valid(raise_exception=True)
            data = params.validated_data
            category = data.get("category") or sub.category
            if category is None:
                return Response({"category": "Укажите категорию"}, status=status.HTTP_400_BAD_REQUEST)
            sub.listing = Listing.objects.create(
                category=category, name=sub.name, description=data.get("description") or sub.description[:1000],
                url=sub.url, phone=sub.phone, address=sub.address, city=sub.city, region=data.get("region"),
                languages=sub.languages, hours=sub.hours, from_owner=True,
                editor_note=f"Заявка от владельца ({sub.contact_name}, {sub.contact_email}), одобрена {editor(request)}",
            )
        sub.status, sub.violation, sub.public_reason = Submission.Status.APPROVED, "none", ""
        sub.reason = f"Одобрено {editor(request)}"
        sub.moderated_at = timezone.now()
        sub.save()
        return Response(self.get_serializer(sub).data)

    @extend_schema(request=cs.RejectSerializer, responses=cs.SubmissionSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Отклонить (и скрыть запись в справочнике, если она уже есть)."""
        params = cs.RejectSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        sub = self.get_object()
        if sub.listing_id:
            Listing.objects.filter(pk=sub.listing_id).update(is_active=False)
        sub = dir_moderation.reject(sub, "other", params.validated_data.get("reason") or f"Отклонено {editor(request)}",
                                    params.validated_data.get("public_reason", ""))
        return Response(self.get_serializer(sub).data)

    @extend_schema(request=None, responses=cs.SubmissionSerializer)
    @action(detail=True, methods=["post"])
    def remoderate(self, request, pk=None):
        """Отдать заявку «на проверке» ИИ прямо сейчас."""
        sub = self.get_object()
        if sub.status != Submission.Status.PENDING:
            return Response({"detail": "Проверяются только заявки со статусом pending"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(dir_moderation.moderate(sub)).data)


# --- Гайды ---------------------------------------------------------------------------------------

@extend_schema(parameters=[
    OpenApiParameter("status", str, description="draft / published"),
    OpenApiParameter("section", str),
    OpenApiParameter("q", str),
])
class GuideViewSet(viewsets.ModelViewSet):
    """Гайды. Публикация — действием publish и только с отметкой human_reviewed=true."""

    serializer_class = cs.GuideSerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = Guide.objects.prefetch_related("sources", "topics")
        params = self.request.query_params
        if value := params.get("status"):
            qs = qs.filter(status=value)
        if value := params.get("section"):
            qs = qs.filter(section=value)
        if value := params.get("q"):
            qs = qs.filter(Q(title__icontains=value) | Q(body__icontains=value))
        return qs

    @extend_schema(request=None, responses={200: dict, 400: dict})
    @action(detail=True, methods=["post"])
    def publish(self, request, slug=None):
        """Опубликовать (и отправить в Telegram, если он включён). Нужна отметка human_reviewed."""
        guide = self.get_object()
        if not guide.body.strip():
            return Response({"detail": "Пустой текст — не публикуем"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            telegram = publish_guide(guide)
        except NotReviewed as exc:
            return Response({"detail": f"{exc}: PATCH {{\"human_reviewed\": true}}"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"telegram": telegram, "guide": self.get_serializer(guide).data})

    @extend_schema(request=None, responses=cs.GuideSerializer)
    @action(detail=True, methods=["post"])
    def unpublish(self, request, slug=None):
        """Снять с публикации (станет черновиком)."""
        guide = self.get_object()
        unpublish_guide(guide)
        return Response(self.get_serializer(guide).data)


# --- Объявления ----------------------------------------------------------------------------------

class AdCategoryViewSet(viewsets.ModelViewSet):
    """Рубрикатор объявлений: разделы (parent=null) и рубрики внутри них."""

    queryset = AdCategory.objects.select_related("parent").order_by("parent__order", "order", "name")
    serializer_class = cs.AdCategorySerializer
    lookup_field = "slug"
    pagination_class = None


@extend_schema(parameters=[
    OpenApiParameter("status", str, description="pending / approved / rejected / hidden / closed"),
    OpenApiParameter("category", str, description="slug рубрики или раздела"),
    OpenApiParameter("active", bool, description="только живые (опубликованы и не истекли)"),
    OpenApiParameter("q", str),
])
class AdViewSet(viewsets.ModelViewSet):
    """Частные объявления. Объявление от API сразу публикуется на 30 дней (status=approved)."""

    serializer_class = cs.AdSerializer
    parser_classes = PARSERS

    def get_queryset(self):
        qs = Ad.objects.select_related("category", "region").prefetch_related("photos")
        params = self.request.query_params
        if value := params.get("status"):
            qs = qs.filter(status=value)
        if value := params.get("category"):
            qs = qs.filter(Q(category__slug=value) | Q(category__parent__slug=value))
        if truthy(params.get("active")):
            qs = qs.active()
        if value := params.get("q"):
            qs = qs.filter(search__icontains=value.lower().replace("ё", "е"))
        return qs

    def perform_destroy(self, instance):
        ad_moderation.delete_photos(instance)
        instance.delete()

    @extend_schema(request=cs.RejectSerializer, responses=cs.AdSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Снять с сайта и отклонить (фото удаляются)."""
        params = cs.RejectSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        ad = self.get_object()
        ad_moderation.delete_photos(ad)
        ad = ad_moderation.reject(ad, "other", params.validated_data.get("reason") or f"Отклонено {editor(request)}",
                                  params.validated_data.get("public_reason", ""))
        return Response(self.get_serializer(ad).data)

    @extend_schema(request=None, responses=cs.AdSerializer)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        """Вернуть на сайт (одобрить): скрытое по жалобам, отклонённое, на проверке или снятое."""
        ad = self.get_object()
        now = timezone.now()
        ad.status = Ad.Status.APPROVED
        ad.moderated_at = ad.moderated_at or now
        if not ad.expires_at or ad.expires_at < now:
            ad.published_at, ad.expires_at = now, now + LIFETIME
        ad.closed_at = None
        ad.save()
        ad.reports.all().delete()
        return Response(self.get_serializer(ad).data)

    @extend_schema(request=None, responses=cs.AdSerializer)
    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        """Продлить на 30 дней от сегодня (поднимается наверх списка)."""
        ad = self.get_object()
        if ad.status != Ad.Status.APPROVED:
            return Response({"detail": "Продлить можно только опубликованное"}, status=status.HTTP_400_BAD_REQUEST)
        ad.renew()
        ad.save()
        return Response(self.get_serializer(ad).data)

    @extend_schema(request=None, responses=cs.AdSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Снять с публикации (как будто снял автор: страница остаётся без контактов)."""
        ad = self.get_object()
        ad.status, ad.closed_at = Ad.Status.CLOSED, timezone.now()
        ad.save()
        return Response(self.get_serializer(ad).data)

    @extend_schema(request=None, responses=cs.AdSerializer)
    @action(detail=True, methods=["post"])
    def remoderate(self, request, pk=None):
        """Отдать объявление «на проверке» ИИ прямо сейчас."""
        ad = self.get_object()
        if ad.status != Ad.Status.PENDING:
            return Response({"detail": "Проверяются только объявления со статусом pending"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(ad_moderation.moderate(ad)).data)

    @extend_schema(request=None, responses=cs.AdSerializer)
    @action(detail=True, methods=["delete"], url_path=r"photos/(?P<photo_id>\d+)")
    def delete_photo(self, request, pk=None, photo_id=None):
        """Удалить одно фото объявления."""
        ad = self.get_object()
        ad_moderation.delete_photos(ad, AdPhoto.objects.filter(ad=ad, pk=photo_id))
        return Response(self.get_serializer(Ad.objects.get(pk=ad.pk)).data)


# --- Комментарии и отзывы ------------------------------------------------------------------------

@extend_schema(parameters=[
    OpenApiParameter("status", str, description="pending / approved / rejected"),
    OpenApiParameter("article", int, description="id новости"),
    OpenApiParameter("listing", int, description="id бизнеса"),
    OpenApiParameter("reported", bool, description="только с жалобами"),
    OpenApiParameter("q", str),
])
class CommentViewSet(viewsets.ModelViewSet):
    """Комментарии к новостям и отзывы о бизнесах: модерация, правка, ответ от редакции."""

    serializer_class = cs.CommentSerializer

    def get_queryset(self):
        qs = Comment.objects.select_related("article", "listing__category")
        params = self.request.query_params
        if value := params.get("status"):
            qs = qs.filter(status=value)
        if value := params.get("article"):
            qs = qs.filter(article_id=value)
        if value := params.get("listing"):
            qs = qs.filter(listing_id=value)
        if truthy(params.get("reported")):
            qs = qs.filter(reports__gt=0)
        if value := params.get("q"):
            qs = qs.filter(Q(text__icontains=value) | Q(name__icontains=value))
        return qs

    @extend_schema(request=None, responses=cs.CommentSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Опубликовать (жалобы сбрасываются)."""
        comment = self.get_object()
        comment.report_set.all().delete()
        comment.status, comment.public_reason, comment.reports = Comment.Status.APPROVED, "", 0
        comment.moderated_at = comment.moderated_at or timezone.now()
        comment.save()
        return Response(self.get_serializer(comment).data)

    @extend_schema(request=cs.RejectSerializer, responses=cs.CommentSerializer)
    @action(detail=True, methods=["post"])
    def hide(self, request, pk=None):
        """Скрыть с сайта."""
        params = cs.RejectSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        comment = comment_moderation.reject(
            self.get_object(), "other", params.validated_data.get("reason") or f"Скрыто {editor(request)}",
            params.validated_data.get("public_reason", ""))
        return Response(self.get_serializer(comment).data)


# --- Остальное -----------------------------------------------------------------------------------

class TagViewSet(viewsets.ModelViewSet):
    """Теги заметок. Удаление тега убирает его из всех заметок."""

    serializer_class = cs.TagSerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = Tag.objects.annotate(articles_count=Count("article")).order_by("-articles_count", "name")
        if value := self.request.query_params.get("q"):
            qs = qs.filter(name__icontains=value)
        return qs


class AuthorViewSet(viewsets.ModelViewSet):
    """Авторы и редакторы (страница «О проекте»). Фото — multipart, поле photo."""

    queryset = Author.objects.all()
    serializer_class = cs.AuthorSerializer
    lookup_field = "slug"
    parser_classes = PARSERS
    pagination_class = None


class SignalSourceViewSet(viewsets.ModelViewSet):
    """Источники сигналов из соцсетей: запросы Perplexity/Grok и публичные Telegram-каналы."""

    queryset = SignalSource.objects.select_related("region")
    serializer_class = cs.SignalSourceSerializer

    @extend_schema(request=None, responses=cs.SignalSourceSerializer)
    @action(detail=True, methods=["post"])
    def reset(self, request, pk=None):
        """Сбросить счётчик ошибок."""
        source = self.get_object()
        source.consecutive_failures, source.last_error = 0, ""
        source.save()
        return Response(self.get_serializer(source).data)


@extend_schema(parameters=[OpenApiParameter("status", str, description="open / confirmed / expired / dismissed")])
class HintViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                  viewsets.GenericViewSet):
    """«Подсказки» из соцсетей: темы, которых ещё нет в СМИ. Отклонить — PATCH {"status": "dismissed"}."""

    serializer_class = cs.HintSerializer
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        qs = Hint.objects.select_related("region", "topic")
        if value := self.request.query_params.get("status"):
            qs = qs.filter(status=value)
        return qs
