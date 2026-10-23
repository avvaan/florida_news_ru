"""Хранилище статики для прода: сжатие и хэши WhiteNoise, но без 500 из-за одной картинки."""

import logging

from whitenoise.storage import CompressedManifestStaticFilesStorage

log = logging.getLogger(__name__)


class ForgivingManifestStorage(CompressedManifestStaticFilesStorage):
    """Если файла нет в манифесте этой сборки — отдаём адрес без хэша, а не падаем с 500.

    Так бывает во время выкладки на Render: миграции идут в сборке, пока ещё работает старая
    версия сайта, и новая запись в базе (например, рубрика с новой обложкой) ссылается на картинку,
    которой нет в манифесте старой сборки. Страница должна открыться, пусть и без этой картинки.
    """

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            log.warning("Статика: нет файла %s в манифесте этой сборки — ссылка без хэша", name)
            return name
