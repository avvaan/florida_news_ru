"""Единый словарь топонимов Флориды: как писать по-русски.

TOPONYMS попадает в промпт автора заметок (prompt_block). WRONG_STEMS — частые ошибки транслитерации,
которые исправляются в готовом тексте с сохранением падежного окончания («Брауарде» → «Броварде»).
Новые названия добавляйте сюда — больше нигде их править не нужно.
"""

from __future__ import annotations

import re

TOPONYMS: dict[str, str] = {
    # Юго-восток
    "Miami": "Майами", "Miami-Dade": "Майами-Дейд", "Miami Beach": "Майами-Бич",
    "North Miami": "Норт-Майами", "North Miami Beach": "Норт-Майами-Бич", "Hialeah": "Хайалиа",
    "Homestead": "Хомстед", "Doral": "Дорал", "Coral Gables": "Корал-Гейблс", "Kendall": "Кендалл",
    "Aventura": "Авентура", "Sunny Isles Beach": "Санни-Айлс-Бич", "Bal Harbour": "Бал-Харбор",
    "Broward": "Бровард", "Fort Lauderdale": "Форт-Лодердейл", "Hollywood": "Холливуд",
    "Hallandale Beach": "Холландейл-Бич", "Dania Beach": "Дания-Бич", "Pompano Beach": "Помпано-Бич",
    "Deerfield Beach": "Дирфилд-Бич", "Coral Springs": "Корал-Спрингс", "Pembroke Pines": "Пемброк-Пайнс",
    "Plantation": "Плантейшн", "Sunrise": "Санрайз", "Weston": "Уэстон", "Coconut Creek": "Коконат-Крик",
    "Palm Beach": "Палм-Бич", "West Palm Beach": "Уэст-Палм-Бич", "Boca Raton": "Бока-Ратон",
    "Delray Beach": "Делрей-Бич", "Boynton Beach": "Бойнтон-Бич", "Jupiter": "Джупитер",
    "Monroe": "Монро", "Florida Keys": "Флорида-Кис", "Key West": "Ки-Уэст", "Key Largo": "Ки-Ларго",
    "Everglades": "Эверглейдс",
    # Центр и Космическое побережье
    "Orlando": "Орландо", "Orange County": "округ Ориндж", "Osceola": "Осеола", "Seminole": "Семинол",
    "Kissimmee": "Киссимми", "Winter Park": "Уинтер-Парк", "Winter Garden": "Уинтер-Гарден",
    "Sanford": "Сэнфорд", "Lake Mary": "Лейк-Мэри", "Longwood": "Лонгвуд", "Altamonte Springs": "Алтамонт-Спрингс",
    "Oviedo": "Овьедо", "Apopka": "Апопка", "Lake County": "округ Лейк", "Volusia": "Волусия",
    "Daytona Beach": "Дейтона-Бич", "Brevard": "Бревард", "Melbourne": "Мелбурн", "Palm Bay": "Палм-Бей",
    "Titusville": "Титусвилл", "Cocoa Beach": "Какао-Бич", "Cape Canaveral": "мыс Канаверал",
    "Polk": "Полк", "Lakeland": "Лейкленд", "Ocala": "Окала", "Marion": "Марион",
    # Тампа-Бэй и юго-запад
    "Tampa": "Тампа", "Tampa Bay": "Тампа-Бэй", "Hillsborough": "Хиллсборо", "Pinellas": "Пинеллас",
    "Pasco": "Паско", "St. Petersburg": "Сент-Питерсберг", "Clearwater": "Клируотер", "Largo": "Ларго",
    "Oldsmar": "Олдсмар", "Brandon": "Брэндон", "Sarasota": "Сарасота", "Manatee": "Манати",
    "Bradenton": "Брейдентон", "Palmetto": "Палметто", "Venice": "Венис", "North Port": "Норт-Порт",
    "Charlotte": "Шарлотт", "Port Charlotte": "Порт-Шарлотт", "Lee County": "округ Ли",
    "Fort Myers": "Форт-Майерс", "Cape Coral": "Кейп-Корал", "Naples": "Нейплс", "Collier": "Коллиер",
    # Север и Панхэндл
    "Jacksonville": "Джексонвилл", "Duval": "Дувал", "St. Johns": "Сент-Джонс", "St. Augustine": "Сент-Огастин",
    "Clay County": "округ Клей", "Nassau": "Нассо", "Jacksonville Beach": "Джексонвилл-Бич",
    "Gainesville": "Гейнсвилл", "Alachua": "Алачуа", "Tallahassee": "Таллахасси", "Leon County": "округ Леон",
    "Pensacola": "Пенсакола", "Escambia": "Эскамбия", "Panama City": "Панама-Сити", "Panhandle": "Панхэндл",
    "Lake Okeechobee": "озеро Окичоби",
}

# Неверная основа → верная. Окончание после основы сохраняется: «Брауарда» → «Броварда».
WRONG_STEMS: list[tuple[str, str]] = [
    ("Брауард", "Бровард"), ("Броуард", "Бровард"), ("Броард", "Бровард"),
    ("Голливуд", "Холливуд"),  # Hollywood во Флориде, не в Калифорнии
    ("Халландейл", "Холландейл"), ("Даниа-Бич", "Дания-Бич"),
    ("Палм Бич", "Палм-Бич"), ("Уэст Палм", "Уэст-Палм"), ("Вест-Палм", "Уэст-Палм"),
    ("Форт Лодердейл", "Форт-Лодердейл"), ("Форт-Лаудердейл", "Форт-Лодердейл"),
    ("Майами Дейд", "Майами-Дейд"), ("Майами-Дэйд", "Майами-Дейд"),
    ("Оранж Каунти", "округ Ориндж"), ("округе Оранж", "округе Ориндж"), ("округ Оранж", "округ Ориндж"),
    ("Киссими ", "Киссимми "), ("Санни Айлс", "Санни-Айлс"),
    ("Ки Уэст", "Ки-Уэст"), ("Ки-Вест", "Ки-Уэст"),
]
# Не трогаем прилагательные: «голливудские звёзды» — это Калифорния.
NOT_BEFORE = {"Голливуд": "ск"}
_WRONG_RE = [
    (re.compile(rf"(?<![А-Яа-яЁё]){re.escape(wrong)}" + (f"(?!{NOT_BEFORE[wrong]})" if wrong in NOT_BEFORE else "")),
     right)
    for wrong, right in WRONG_STEMS
]


def prompt_block() -> str:
    """Словарь для промпта: «English — русский» по строке."""
    lines = "\n".join(f"- {en} — {ru}" for en, ru in TOPONYMS.items())
    return ("Топонимы Флориды пиши строго так (склоняй по правилам русского языка, «в Броварде», "
            f"«округа Бревард»):\n{lines}")


def fix_text(text: str) -> str:
    """Исправляет частые ошибки транслитерации в готовом тексте."""
    for pattern, right in _WRONG_RE:
        text = pattern.sub(right, text)
    return text
