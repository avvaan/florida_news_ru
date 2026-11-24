"""Перевод типов предупреждений NWS на русский. Список событий конечный, ИИ не нужен.

В базе (WeatherAlert.event_ru) хранится русское название; на украинской версии сайта его переводит gettext
(строки помечены gettext_noop и попадают в locale/uk).
"""

from django.utils.translation import gettext, gettext_lazy, gettext_noop

EVENTS_RU = {
    "Hurricane Warning": gettext_noop("Предупреждение об урагане"),
    "Hurricane Watch": gettext_noop("Угроза урагана"),
    "Tropical Storm Warning": gettext_noop("Предупреждение о тропическом шторме"),
    "Tropical Storm Watch": gettext_noop("Угроза тропического шторма"),
    "Storm Surge Warning": gettext_noop("Предупреждение о штормовом нагоне"),
    "Storm Surge Watch": gettext_noop("Угроза штормового нагона"),
    "Extreme Wind Warning": gettext_noop("Предупреждение об экстремальном ветре"),
    "Evacuation Immediate": gettext_noop("Немедленная эвакуация"),
    "Civil Emergency Message": gettext_noop("Экстренное сообщение властей"),
    "Tornado Warning": gettext_noop("Предупреждение о торнадо"),
    "Tornado Watch": gettext_noop("Угроза торнадо"),
    "Severe Thunderstorm Warning": gettext_noop("Предупреждение о сильной грозе"),
    "Severe Thunderstorm Watch": gettext_noop("Угроза сильной грозы"),
    "Flash Flood Emergency": gettext_noop("Чрезвычайная ситуация: внезапное наводнение"),
    "Flash Flood Warning": gettext_noop("Предупреждение о внезапном наводнении"),
    "Flash Flood Watch": gettext_noop("Угроза внезапного наводнения"),
    "Flood Warning": gettext_noop("Предупреждение о наводнении"),
    "Flood Watch": gettext_noop("Угроза наводнения"),
    "Flood Advisory": gettext_noop("Подтопления"),
    "Coastal Flood Warning": gettext_noop("Предупреждение о прибрежном наводнении"),
    "Coastal Flood Advisory": gettext_noop("Прибрежные подтопления"),
    "Rip Current Statement": gettext_noop("Опасные обратные течения"),
    "High Surf Advisory": gettext_noop("Высокий прибой"),
    "Heat Advisory": gettext_noop("Сильная жара"),
    "Excessive Heat Warning": gettext_noop("Предупреждение об экстремальной жаре"),
    "Extreme Heat Warning": gettext_noop("Предупреждение об экстремальной жаре"),
    "Red Flag Warning": gettext_noop("Высокая пожарная опасность"),
    "Fire Weather Watch": gettext_noop("Угроза пожароопасной погоды"),
    "Dense Fog Advisory": gettext_noop("Густой туман"),
    "Wind Advisory": gettext_noop("Сильный ветер"),
    "High Wind Warning": gettext_noop("Предупреждение о штормовом ветре"),
    "Small Craft Advisory": gettext_noop("Опасно для малых судов"),
    "Freeze Warning": gettext_noop("Предупреждение о заморозках"),
    "Frost Advisory": gettext_noop("Заморозки"),
    "Special Weather Statement": gettext_noop("Особое погодное сообщение"),
    "Air Quality Alert": gettext_noop("Плохое качество воздуха"),
}

# Эти события сразу идут в конвейер как срочные сюжеты.
SEVERE_EVENTS = {
    "Hurricane Warning", "Hurricane Watch", "Tropical Storm Warning", "Storm Surge Warning",
    "Extreme Wind Warning", "Evacuation Immediate", "Civil Emergency Message",
    "Tornado Warning", "Flash Flood Emergency",
}


# Подписи степени опасности на сайте — те же, что в WeatherAlert.Severity, но с переводом.
SEVERITY_LABELS = {
    "Extreme": gettext_lazy("чрезвычайное"),
    "Severe": gettext_lazy("сильное"),
    "Moderate": gettext_lazy("умеренное"),
    "Minor": gettext_lazy("слабое"),
    "Unknown": gettext_lazy("неизвестно"),
}


def translate_event(event: str) -> str:
    return EVENTS_RU.get(event, event)


def event_label(event: str, event_ru: str = "") -> str:
    """Название события на языке страницы: русское из базы (или из словаря), через gettext — украинское."""
    ru = event_ru or EVENTS_RU.get(event, "")
    return gettext(ru) if ru else event


def severity_label(severity: str) -> str:
    label = SEVERITY_LABELS.get(severity)
    return str(label) if label else ""
