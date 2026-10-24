"""Привязка к месту без внешних сервисов: ZIP-коды Флориды и их регионы по первым трём цифрам."""

# Флорида — ZIP 32003…34997. Первые три цифры (SCF) достаточно точно задают район.
FLORIDA_ZIP_RANGE = (32003, 34997)

REGION_BY_PREFIX = {
    # Майами-Дейд, Бровард, Палм-Бич
    "330": "miami", "331": "miami", "332": "miami", "333": "miami", "334": "miami",
    # Центральная Флорида: Орландо, Дейтона, Космическое побережье
    "321": "orlando", "327": "orlando", "328": "orlando", "329": "orlando", "347": "orlando",
    # Тампа-Бэй, Лейкленд, Сарасота и Брейдентон
    "335": "tampa", "336": "tampa", "337": "tampa", "338": "tampa", "342": "tampa", "346": "tampa",
    # Северо-Восток
    "320": "jacksonville", "322": "jacksonville",
}


def is_florida_zip(zip_code: str) -> bool:
    return len(zip_code) == 5 and zip_code.isdigit() and FLORIDA_ZIP_RANGE[0] <= int(zip_code) <= FLORIDA_ZIP_RANGE[1]


def region_slug_for_zip(zip_code: str) -> str:
    """Код региона сайта для ZIP или «other», если это остальная Флорида (Таллахасси, Нейплс, Форт-Майерс…)."""
    return REGION_BY_PREFIX.get(zip_code[:3], "other") if is_florida_zip(zip_code) else ""
