"""Наборы обложек по рубрикам.

Файлы лежат в static/covers/ и называются по рубрике:
- weather.webp, weather-2.webp … — иллюстрации «Флорида Сегодня» (Higgsfield);
- weather-photo-1.webp … — стоковые фото (Freepik / Magnific, лицензия Premium).
Для каждой обложки есть .webp (1200×675), -640.webp и .jpg. Новая картинка подхватится
сама после перезапуска, если положить три файла по этому шаблону.

Заметке достаётся обложка из набора её рубрики по номеру заметки, поэтому соседние
заметки одной рубрики получают разные картинки, а у одной заметки обложка не меняется.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings

COVER_RE = re.compile(r"^(?P<pool>[a-z]+)(?P<photo>-photo)?(?:-(?P<n>\d+))?\.jpg$")


@dataclass(frozen=True)
class Cover:
    base: str       # путь в static/ без расширения: covers/weather-2
    is_photo: bool  # стоковое фото, а не наша иллюстрация

    @property
    def credit(self) -> str:
        return "Фото: Freepik (иллюстративное)" if self.is_photo else ""


@lru_cache(maxsize=1)
def cover_pools() -> dict[str, tuple[Cover, ...]]:
    folder = settings.BASE_DIR / "static" / "covers"
    pools: dict[str, list[tuple[tuple, Cover]]] = {}
    for path in folder.glob("*.jpg"):
        match = COVER_RE.match(path.name)
        if not match or not (folder / f"{path.stem}-640.webp").exists():
            continue
        cover = Cover(base=f"covers/{path.stem}", is_photo=bool(match["photo"]))
        sort_key = (cover.is_photo, int(match["n"] or 1))
        pools.setdefault(match["pool"], []).append((sort_key, cover))
    # Чередуем иллюстрации и фото, чтобы подряд не шли однотипные картинки.
    result = {}
    for name, items in pools.items():
        drawings = [c for key, c in sorted(items, key=lambda kc: kc[0]) if not c.is_photo]
        photos = [c for key, c in sorted(items, key=lambda kc: kc[0]) if c.is_photo]
        mixed = []
        for i in range(max(len(drawings), len(photos))):
            mixed += drawings[i:i + 1] + photos[i:i + 1]
        result[name] = tuple(mixed)
    return result


def pick_cover(pool: str, number: int | None) -> Cover:
    pools = cover_pools()
    covers = pools.get(pool) or pools.get("florida") or (Cover("covers/florida", False),)
    return covers[(number or 0) % len(covers)]
