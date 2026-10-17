"""Перевод типов предупреждений NWS на русский. Список событий конечный, ИИ не нужен."""

EVENTS_RU = {
    "Hurricane Warning": "Предупреждение об урагане",
    "Hurricane Watch": "Угроза урагана",
    "Tropical Storm Warning": "Предупреждение о тропическом шторме",
    "Tropical Storm Watch": "Угроза тропического шторма",
    "Storm Surge Warning": "Предупреждение о штормовом нагоне",
    "Storm Surge Watch": "Угроза штормового нагона",
    "Extreme Wind Warning": "Предупреждение об экстремальном ветре",
    "Evacuation Immediate": "Немедленная эвакуация",
    "Civil Emergency Message": "Экстренное сообщение властей",
    "Tornado Warning": "Предупреждение о торнадо",
    "Tornado Watch": "Угроза торнадо",
    "Severe Thunderstorm Warning": "Предупреждение о сильной грозе",
    "Severe Thunderstorm Watch": "Угроза сильной грозы",
    "Flash Flood Emergency": "Чрезвычайная ситуация: внезапное наводнение",
    "Flash Flood Warning": "Предупреждение о внезапном наводнении",
    "Flash Flood Watch": "Угроза внезапного наводнения",
    "Flood Warning": "Предупреждение о наводнении",
    "Flood Watch": "Угроза наводнения",
    "Flood Advisory": "Подтопления",
    "Coastal Flood Warning": "Предупреждение о прибрежном наводнении",
    "Coastal Flood Advisory": "Прибрежные подтопления",
    "Rip Current Statement": "Опасные обратные течения",
    "High Surf Advisory": "Высокий прибой",
    "Heat Advisory": "Сильная жара",
    "Excessive Heat Warning": "Предупреждение об экстремальной жаре",
    "Extreme Heat Warning": "Предупреждение об экстремальной жаре",
    "Red Flag Warning": "Высокая пожарная опасность",
    "Fire Weather Watch": "Угроза пожароопасной погоды",
    "Dense Fog Advisory": "Густой туман",
    "Wind Advisory": "Сильный ветер",
    "High Wind Warning": "Предупреждение о штормовом ветре",
    "Small Craft Advisory": "Опасно для малых судов",
    "Freeze Warning": "Предупреждение о заморозках",
    "Frost Advisory": "Заморозки",
    "Special Weather Statement": "Особое погодное сообщение",
    "Air Quality Alert": "Плохое качество воздуха",
}

# Эти события сразу идут в конвейер как срочные сюжеты.
SEVERE_EVENTS = {
    "Hurricane Warning", "Hurricane Watch", "Tropical Storm Warning", "Storm Surge Warning",
    "Extreme Wind Warning", "Evacuation Immediate", "Civil Emergency Message",
    "Tornado Warning", "Flash Flood Emergency",
}


def translate_event(event: str) -> str:
    return EVENTS_RU.get(event, event)
