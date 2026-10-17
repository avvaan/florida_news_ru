"""Наборы обложек по рубрикам.

Файлы лежат в static/covers/ и называются по рубрике:
- weather.webp, weather-2.webp … — иллюстрации «Florida RU» (Higgsfield);
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


# Что изображено на каждой обложке — по этим описаниям ИИ выбирает картинку к заметке.
# Новую картинку без описания ИИ тоже увидит, но только по имени рубрики.
CATALOG = {
    "covers/weather": "иллюстрация: цапля в Эверглейдс под грозовыми тучами с молниями",
    "covers/weather-2": "иллюстрация: солнечный пляж, спасательная вышка, облака и радуга после дождя",
    "covers/weather-3": "иллюстрация: затопленная после ливня улица, машина едет по воде",
    "covers/weather-photo-1": "фото: пальмы гнутся на ветру под тёмными грозовыми тучами",
    "covers/weather-photo-2": "фото: пальма на сильном ветру, голубое небо с перистыми облаками",
    "covers/weather-photo-3": "фото: штормовой тропический пляж, пальмы клонятся, тёмное небо",
    "covers/hurricane": "иллюстрация: спираль урагана над Мексиканским заливом и полуостровом Флорида",
    "covers/hurricane-2": "иллюстрация: штормовой нагон, волны бьют в дома с заколоченными окнами",
    "covers/hurricane-photo-1": "фото с воздуха: затопленный жилой район Флориды после урагана",
    "covers/hurricane-photo-2": "фото: упавшее дерево на линиях электропередачи после урагана",
    "covers/hurricane-photo-3": "фото с воздуха: машины едут по затопленной улице после урагана",
    "covers/safety": "иллюстрация: подготовка к шторму — фонарик, вода, мешки с песком, ставни",
    "covers/safety-2": "иллюстрация: отключение света ночью, бригада чинит провода с автовышки",
    "covers/safety-3": "иллюстрация: кипячение воды — кастрюля на плите, бутыли с водой, кран",
    "covers/safety-photo-1": "фото: окна дома заколочены фанерой перед ураганом",
    "covers/safety-photo-2": "фото: металлические штормовые ставни на окнах дома",
    "covers/laws": "иллюстрация: судейский молоток, документ, удостоверение, здание правительства",
    "covers/laws-2": "иллюстрация: окно госучреждения — бланки, печать, удостоверение",
    "covers/laws-3": "иллюстрация: урна для голосования и бюллетень, выборы",
    "covers/laws-photo-1": "фото: исторический Капитолий Флориды в Таллахасси",
    "covers/laws-photo-3": "фото: паспорт США на американском флаге — иммиграция, гражданство",
    "covers/housing": "иллюстрация: кондо и дом под зонтом, ключи — страхование жилья",
    "covers/housing-2": "иллюстрация: жилой комплекс с бассейном, ключ, коробка — аренда, переезд",
    "covers/housing-3": "иллюстрация: кровельщик меняет черепицу, синий брезент — ремонт крыши",
    "covers/housing-photo-1": "фото с воздуха: частные дома в пригороде Флориды среди сосен",
    "covers/housing-photo-2": "фото: высотные кондоминиумы Санни-Айлс-Бич у океана",
    "covers/housing-photo-3": "фото: табличка «For Rent» перед домом — аренда",
    "covers/roads": "иллюстрация: мост-дамба над заливом, машины и дорожные конусы",
    "covers/roads-2": "иллюстрация: многоуровневая развязка с платным порталом, закат",
    "covers/roads-photo-1": "фото с воздуха: большая развязка в Майами среди озёр и кварталов",
    "covers/roads-photo-2": "фото с воздуха: развязка хайвея в Майами, идёт стройка",
    "covers/roads-photo-3": "фото: межштатная трасса I-75 и указатель съезда",
    "covers/money": "иллюстрация: корзина с апельсинами, чек, монеты, бензоколонка — цены",
    "covers/money-2": "иллюстрация: счётчики, кран, копилка, калькулятор — коммунальные счета",
    "covers/money-3": "иллюстрация: пакеты с покупками, рюкзак, ноутбук — налоговые каникулы",
    "covers/money-photo-3": "фото: руки держат стодолларовые купюры, калькулятор",
    "covers/education": "иллюстрация: школьный автобус, дети с рюкзаками у школы",
    "covers/education-2": "иллюстрация: пустой класс с партами и глобусом, окно с пальмами",
    "covers/education-photo-1": "фото: жёлтый школьный автобус",
    "covers/education-photo-2": "фото: ряд школьных автобусов",
    "covers/education-photo-3": "фото: ученики поднимают руки на уроке",
    "covers/health": "иллюстрация: клиника, стетоскоп, солнцезащитный крем, комар",
    "covers/health-2": "иллюстрация: аптечные полки, сердце, градусник, шляпа — жара и здоровье",
    "covers/health-photo-1": "фото: врач в белом халате со стетоскопом",
    "covers/health-photo-2": "фото: полки аптеки с лекарствами",
    "covers/health-photo-3": "фото: комар на коже — болезни, которые переносят комары",
    "covers/events": "иллюстрация: праздник на набережной, фейерверк, фудтрак, гирлянды",
    "covers/events-2": "иллюстрация: бесплатный концерт в парке на закате, пледы",
    "covers/events-3": "иллюстрация: ярмарка и фермерский рынок, тенты, фрукты",
    "covers/events-photo-1": "фото: толпа на ночном концерте, свет сцены",
    "covers/events-photo-2": "фото: фейерверк над рекой и зрители",
    "covers/events-photo-3": "фото: прилавок фермерского рынка с овощами",
    "covers/incidents": "иллюстрация: полицейская и пожарная машины на тихой улице ночью",
    "covers/incidents-2": "иллюстрация: береговая охрана — катер и спасательный вертолёт у маяка",
    "covers/incidents-3": "иллюстрация: пожарная часть, пожарная машина и скорая",
    "covers/incidents-photo-1": "фото: полицейская машина с мигалками ночью",
    "covers/florida": "иллюстрация: панорама городов Флориды вдоль побережья",
    "covers/florida-2": "иллюстрация: отели ар-деко на Ocean Drive в Майами-Бич",
    "covers/florida-3": "иллюстрация: природный источник Флориды с ламантином и кипарисами",
    "covers/florida-photo-1": "фото: Орландо, небоскрёбы над озером Эола",
    "covers/florida-photo-2": "фото: Тампа, небоскрёбы на закате у реки Хилсборо",
    "covers/florida-photo-3": "фото: Джексонвилл, мост Акоста ночью",
}


def all_covers() -> dict[str, Cover]:
    return {c.base: c for pool in cover_pools().values() for c in pool}


def describe(cover: Cover) -> str:
    return CATALOG.get(cover.base) or cover.base.split("/")[-1]


def candidates_for(topic_slug: str | None, is_urgent: bool = False) -> list[Cover]:
    """Обложки, из которых ИИ выбирает: рубрика, ураган для срочной погоды/ЧП и общие виды Флориды."""
    pools = cover_pools()
    names = [topic_slug or "florida"]
    if topic_slug in ("weather", "safety"):
        names.insert(0 if is_urgent else 1, "hurricane")
    if "florida" not in names:
        names.append("florida")
    seen, result = set(), []
    for name in names:
        for cover in pools.get(name, ()):
            if cover.base not in seen:
                seen.add(cover.base)
                result.append(cover)
    return result
