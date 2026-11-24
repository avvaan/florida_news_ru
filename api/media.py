"""Фото и видео в API: медиатека и общие поля «фото по id / по ссылке / файлом» для других разделов."""

from rest_framework import serializers

from gallery import services
from gallery.models import MediaItem


class MediaItemSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, required=False,
                                 help_text="Файл фото (JPG/PNG/WebP/GIF до 20 МБ) или видео (mp4/webm/mov до 200 МБ), "
                                           "multipart/form-data")
    source = serializers.CharField(write_only=True, required=False, max_length=1000,
                                   help_text="Ссылка вместо файла: картинка или видеофайл (скачаем и сохраним у себя) "
                                             "либо YouTube / Vimeo / Rutube / VK (встроим плеер)")

    class Meta:
        model = MediaItem
        fields = ["id", "kind", "title", "caption", "credit", "alt", "file", "source", "url", "storage", "embed_url",
                  "provider", "thumbnail_url", "source_url", "width", "height", "size", "mime", "created_at"]
        read_only_fields = ["url", "storage", "embed_url", "provider", "thumbnail_url", "source_url", "width",
                            "height", "size", "mime", "created_at"]
        extra_kwargs = {"kind": {"required": False,
                                 "help_text": "photo или video; если не указать — определим по файлу или ссылке"}}

    def validate(self, attrs):
        if self.instance is None and not (attrs.get("file") or attrs.get("source")):
            raise serializers.ValidationError("Нужен file (загрузка файла) или source (ссылка)")
        if self.instance is not None and (attrs.get("file") or attrs.get("source") or "kind" in attrs):
            raise serializers.ValidationError("Файл и вид не меняются — добавьте новое фото или видео")
        return attrs

    def create(self, validated):
        meta = {k: validated.get(k, "") for k in ("title", "caption", "credit", "alt")}
        kind = validated.get("kind", "")
        try:
            item = (services.add_upload(validated["file"], meta) if validated.get("file")
                    else services.add_url(validated["source"], meta, kind=kind))
        except services.MediaError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        if kind and item.kind != kind:
            services.delete_file(item)
            item.delete()
            raise serializers.ValidationError({"kind": f"Получилось {item.get_kind_display()}, а просили {kind}"})
        return item


class MediaBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaItem
        fields = ["id", "kind", "url", "embed_url", "thumbnail_url", "caption", "credit", "alt", "width", "height"]
        read_only_fields = fields


def import_media(*, url: str = "", upload=None, kind: str, meta: dict | None = None, field: str) -> MediaItem:
    """Ссылка или файл → новая запись медиатеки нужного вида. Ошибка — ValidationError по полю."""
    try:
        item = services.add_upload(upload, meta) if upload else services.add_url(url, meta, kind=kind)
    except services.MediaError as exc:
        raise serializers.ValidationError({field: str(exc)}) from exc
    if item.kind != kind:
        services.delete_file(item)
        item.delete()
        raise serializers.ValidationError({field: f"Это {item.get_kind_display()}, а нужно "
                                                  f"{MediaItem.Kind(kind).label}"})
    return item


def media_fields(name: str, kind: str, label: str) -> dict:
    """Поля для подключения одного фото или видео: <name> (id), <name>_url (ссылка), <name>_file (файл)."""
    return {
        name: serializers.PrimaryKeyRelatedField(
            queryset=MediaItem.objects.filter(kind=kind), required=False, allow_null=True,
            help_text=f"{label}: id из медиатеки (GET /api/v1/media/); null — убрать"),
        f"{name}_url": serializers.CharField(
            write_only=True, required=False, allow_blank=True, max_length=1000,
            help_text=f"{label} по ссылке: скачаем и добавим в медиатеку"
                      + (" (YouTube/Vimeo/Rutube/VK — встроим плеер)" if kind == MediaItem.Kind.VIDEO else "")),
        f"{name}_file": serializers.FileField(
            write_only=True, required=False, help_text=f"{label} файлом (multipart/form-data)"),
        f"{name}_caption": serializers.CharField(
            write_only=True, required=False, allow_blank=True, max_length=300,
            help_text="Подпись к новому фото/видео из _url или _file"),
        f"{name}_credit": serializers.CharField(
            write_only=True, required=False, allow_blank=True, max_length=200,
            help_text="Автор / источник нового фото/видео, например «Фото: NOAA»"),
    }


def resolve_media(attrs: dict, name: str, kind: str, title: str = "") -> None:
    """Если пришли <name>_url или <name>_file — импортирует и кладёт результат в attrs[name]."""
    url = attrs.pop(f"{name}_url", "") or ""
    upload = attrs.pop(f"{name}_file", None)
    meta = {"title": title, "caption": attrs.pop(f"{name}_caption", ""), "credit": attrs.pop(f"{name}_credit", "")}
    if url.strip() or upload:
        attrs[name] = import_media(url=url, upload=upload, kind=kind, meta=meta, field=f"{name}_url")


def media_list_fields(name: str, label: str) -> dict:
    """Несколько фото: <name> (список id), <name>_urls (ссылки, добавляются в конец)."""
    return {
        f"{name}_urls": serializers.ListField(
            child=serializers.CharField(max_length=1000), write_only=True, required=False,
            help_text=f"{label}: ссылки на фото — скачаем, добавим в медиатеку и в конец списка"),
    }


def resolve_media_list(attrs: dict, name: str, current: list, title: str = "") -> None:
    urls = [u for u in attrs.pop(f"{name}_urls", []) if u.strip()]
    if urls:
        base = list(attrs[name]) if name in attrs else list(current)
        attrs[name] = base + [import_media(url=u, kind=MediaItem.Kind.PHOTO, meta={"title": title},
                                           field=f"{name}_urls") for u in urls]
