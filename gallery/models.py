"""Медиатека: фото и видео, которые редакция или её агент добавляют через API или админку.

Фото хранится в ImageKit (если есть ключ), иначе — на диске сайта (MEDIA_ROOT). Видео — ссылка
на YouTube / Vimeo / Rutube / VK (встраивается плеером) или файл mp4/webm (ImageKit, диск или
прямая ссылка). Фото и видео подключаются к заметкам, событиям афиши, бизнесам справочника и
объявлениям.
"""

from django.db import models
from django.utils import timezone


class MediaItem(models.Model):
    class Kind(models.TextChoices):
        PHOTO = "photo", "фото"
        VIDEO = "video", "видео"

    class Storage(models.TextChoices):
        IMAGEKIT = "imagekit", "ImageKit"
        LOCAL = "local", "диск сайта"
        EXTERNAL = "external", "внешняя ссылка"

    kind = models.CharField("вид", max_length=5, choices=Kind.choices, db_index=True)
    title = models.CharField("название", max_length=200, blank=True, help_text="Для поиска в медиатеке")
    caption = models.CharField("подпись", max_length=300, blank=True, help_text="Показывается под фото или видео")
    credit = models.CharField("автор / источник", max_length=200, blank=True,
                              help_text="Например: «Фото: NOAA» или «Видео: WPLG Local 10»")
    alt = models.CharField("описание для незрячих (alt)", max_length=300, blank=True)

    url = models.URLField("адрес файла", max_length=1000)
    storage = models.CharField("где хранится", max_length=10, choices=Storage.choices)
    file_id = models.CharField("ImageKit fileId", max_length=80, blank=True)
    path = models.CharField("путь на диске", max_length=300, blank=True)
    embed_url = models.URLField("адрес плеера", max_length=500, blank=True,
                                help_text="Для YouTube, Vimeo, Rutube, VK — встраиваемый плеер")
    provider = models.CharField("площадка", max_length=20, blank=True)
    thumbnail_url = models.URLField("превью", max_length=1000, blank=True)
    source_url = models.URLField("откуда взято", max_length=1000, blank=True)
    width = models.PositiveIntegerField("ширина", null=True, blank=True)
    height = models.PositiveIntegerField("высота", null=True, blank=True)
    size = models.PositiveBigIntegerField("размер, байт", null=True, blank=True)
    mime = models.CharField("тип файла", max_length=60, blank=True)
    created_at = models.DateTimeField("добавлено", default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "фото или видео"
        verbose_name_plural = "медиатека: фото и видео"

    def __str__(self):
        return f"{self.get_kind_display()} #{self.pk}: {self.title or self.caption or self.url[-60:]}"

    @property
    def is_photo(self) -> bool:
        return self.kind == self.Kind.PHOTO

    @property
    def is_embed(self) -> bool:
        return bool(self.embed_url)

    def sized(self, width: int) -> str:
        """Фото нужной ширины: у ImageKit — преобразование на лету, у остальных — оригинал."""
        if self.storage == self.Storage.IMAGEKIT:
            from core.images import resized

            return resized(self.url, width)
        return self.url

    @property
    def poster(self) -> str:
        """Картинка-заставка видео (или само фото)."""
        if self.is_photo:
            return self.url
        return self.thumbnail_url

    @property
    def figcaption(self) -> str:
        return " · ".join(part for part in (self.caption, self.credit) if part)
