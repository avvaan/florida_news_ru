"""Города Центральной Флориды для каталога кружков и абзац о форме «Добавить кружок» в политике."""

import hashlib

from django.db import migrations

# slug, по-русски, по-английски, «где?», по-украински, «де?» (укр.), широта, долгота — центр города.
CITIES = [
    ("orlando", "Орландо", "Orlando", "в Орландо", "Орландо", "в Орландо", 28.5383, -81.3792),
    ("winter-park", "Винтер-Парк", "Winter Park", "в Винтер-Парке", "Вінтер-Парк", "у Вінтер-Парку", 28.6000, -81.3392),
    ("altamonte-springs", "Алтамонте-Спрингс", "Altamonte Springs", "в Алтамонте-Спрингс", "Алтамонте-Спрінгс",
     "в Алтамонте-Спрінгс", 28.6611, -81.3656),
    ("longwood", "Лонгвуд", "Longwood", "в Лонгвуде", "Лонгвуд", "у Лонгвуді", 28.7031, -81.3384),
    ("lake-mary", "Лейк-Мэри", "Lake Mary", "в Лейк-Мэри", "Лейк-Мері", "у Лейк-Мері", 28.7589, -81.3178),
    ("sanford", "Сэнфорд", "Sanford", "в Сэнфорде", "Сенфорд", "у Сенфорді", 28.8003, -81.2731),
    ("oviedo", "Овьедо", "Oviedo", "в Овьедо", "Ов'єдо", "в Ов'єдо", 28.6700, -81.2081),
    ("winter-springs", "Винтер-Спрингс", "Winter Springs", "в Винтер-Спрингс", "Вінтер-Спрінгс", "у Вінтер-Спрінгс",
     28.6989, -81.3081),
    ("apopka", "Апопка", "Apopka", "в Апопке", "Апопка", "в Апопці", 28.6934, -81.5322),
    ("kissimmee", "Киссимми", "Kissimmee", "в Киссимми", "Кіссіммі", "у Кіссіммі", 28.2920, -81.4076),
    ("clermont", "Клермонт", "Clermont", "в Клермонте", "Клермонт", "у Клермонті", 28.5494, -81.7729),
    ("ocoee", "Окои", "Ocoee", "в Окои", "Окоі", "в Окоі", 28.5692, -81.5440),
    ("winter-garden", "Винтер-Гарден", "Winter Garden", "в Винтер-Гардене", "Вінтер-Гарден", "у Вінтер-Гардені",
     28.5653, -81.5862),
    ("lake-nona", "Лейк-Нона", "Lake Nona", "в Лейк-Ноне", "Лейк-Нона", "у Лейк-Ноні", 28.3790, -81.2445),
    ("daytona-beach", "Дейтона-Бич", "Daytona Beach", "в Дейтона-Бич", "Дейтона-Біч", "у Дейтона-Біч", 29.2108, -81.0228),
]

PRIVACY_KIDS = """Если вы добавляете кружок в каталог «Детям», мы храним ваше имя и e-mail, чтобы уточнить \
данные; на сайте они не публикуются. Заявку проверяет редакция и только после этого публикует. Если вы \
сообщаете об ошибке в карточке кружка, контакт указывать не обязательно. Для защиты от спама мы храним \
не IP-адрес, а обезличенный код. Карта на странице каталога загружается с OpenStreetMap, только если вы \
нажали «Показать на карте»; карта в карточке кружка — с Google Maps."""

PRIVACY_ANCHOR = "По вопросам, связанным с данными"


def source_hash(*values) -> str:
    return hashlib.sha1("\x00".join(values).encode()).hexdigest()[:16]


def seed(apps, schema_editor):
    City = apps.get_model("kids", "City")
    for order, (slug, name, name_en, where, name_uk, where_uk, lat, lng) in enumerate(CITIES, start=1):
        City.objects.update_or_create(slug=slug, defaults={
            "name": name, "name_en": name_en, "name_locative": where, "name_uk": name_uk,
            "name_locative_uk": where_uk, "lat": lat, "lng": lng, "order": order * 10,
            "uk_hash": source_hash(name, where),  # перевод уже есть — translate_content его не трогает
        })

    Page = apps.get_model("core", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if page and "каталог «Детям»" not in page.body:
        paragraphs = page.body.replace("\r\n", "\n").split("\n\n")
        at = next((i for i, p in enumerate(paragraphs) if p.startswith(PRIVACY_ANCHOR)), len(paragraphs))
        paragraphs.insert(at, PRIVACY_KIDS)
        page.body = "\n\n".join(paragraphs)
        page.save(update_fields=["body"])


class Migration(migrations.Migration):
    dependencies = [
        ("kids", "0001_initial"),
        ("core", "0019_topic_variety"),
    ]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
