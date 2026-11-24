"""Объявления из групп «Русские в Орландо» и «Большой Орландо» (таблица редакции от 28.10.2026).

Берём только те посты, где автор сам оставил телефон. Тексты короткие и только по фактам из поста;
город и ZIP уточнены по открытым источникам (Lacomka — Винтер-Парк, Pristine Beauty Academy — список
Департамента здравоохранения Флориды, Miss Figgy — Майами по Adopt-a-Pet). Нотариус, клиника после ДТП
и страховые агенты сюда не идут: по правилам объявлений их место в справочнике бизнесов.

Миграция зовёт исторические модели, а у них нет Ad.save(), поэтому slug, поиск и координаты считаем сами.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import migrations
from django.utils import timezone

from core import geo
from core.text import make_slug

REASON = "Добавлено редакцией по таблице от 28.10.2026 (посты в группах Орландо)"
TRUCK_UNTIL = datetime(2026, 11, 8, tzinfo=ZoneInfo("America/New_York"))  # рейс 31.10, обратно через неделю

# (рубрика, заголовок, текст, город, ZIP, регион, имя, телефон, до какого числа или None — на 30 дней)
ADS = [
    ("vakansii", "Кассир-продавец в русский магазин и пекарню «Лакомка»",
     "Русский магазин и пекарня «Лакомка» (Lacomka Bakery & Russian Store, 2050 Semoran Blvd, Винтер-Парк) "
     "ищет кассира-продавца.\n\nГрафик и оплату уточняйте по телефону.",
     "Винтер-Парк", "32792", "orlando", "«Лакомка»", "+14076771101", None),
    ("avtoservis", "Сервис для грузовиков в Лейкленде: все виды работ, паркинг",
     "Сервис для грузовиков в Лейкленде: все виды работ. Есть паркинг.\n\n"
     "Адрес и цены уточняйте по телефону.",
     "Лейкленд", "", "tampa", "Сервис для грузовиков", "+19546133623", None),
    ("pereezdy", "Трак Майами → Нью-Йорк 31 октября, обратно через неделю",
     "Трак едет из Майами в Нью-Йорк 31 октября и возвращается примерно через неделю.\n\n"
     "Объём груза и стоимость уточняйте по телефону.",
     "Майами", "", "miami", "Грузоперевозки Майами — Нью-Йорк", "+19088030090", TRUCK_UNTIL),
    ("krasota", "Салон Oxyoxy Beauty by Oksana Karvehina на Millennia Blvd",
     "Салон красоты Oxyoxy Beauty, мастер Оксана Карвехина. Адрес: 4976 Millennia Blvd, Ste D, Орландо.\n\n"
     "Запись по телефону или на сайте салона.",
     "Орландо", "32839", "orlando", "Oxyoxy Beauty", "+13219772397", None),
    ("repetitory", "Набор в школу косметологии и лазерной эпиляции Pristine Beauty Academy, скидки в ноябре",
     "Pristine Beauty Academy в Орландо набирает учеников на курсы косметологии и лазерной эпиляции. "
     "Школа есть в списке учебных заведений, которые Департамент здравоохранения Флориды одобрил "
     "для обучения лазерной эпиляции.\n\nВ ноябре — скидки на обучение. Условия уточняйте по телефону.",
     "Орландо", "32809", "orlando", "Pristine Beauty Academy", "+14077497436", None),
    ("pristroit", "Miss Figgy: 5 лет в приюте, кошка ищет дом",
     "Кошке Miss Figgy пять лет, и всё это время она живёт в приюте. Ищет дом и семью.\n\n"
     "Об условиях пристройства спрашивайте по телефону.",
     "Майами", "", "miami", "Miss Figgy", "+13059721130", None),
]


def add_ads(apps, schema_editor):
    Ad = apps.get_model("classifieds", "Ad")
    Category = apps.get_model("classifieds", "Category")
    Region = apps.get_model("news", "Region")
    regions = {r.slug: r for r in Region.objects.all()}
    now = timezone.now()
    for category, title, text, city, zip_code, region, name, phone, until in ADS:
        lat, lon = geo.locate(city) or (None, None)
        Ad.objects.update_or_create(title=title, phone=phone, defaults={
            "category": Category.objects.get(slug=category), "status": "approved",
            "slug": make_slug(title, max_length=80) or "obyavlenie", "description": text,
            "search": " ".join([title, text, city, zip_code]).lower().replace("ё", "е"),
            "city": city, "zip_code": zip_code, "region": regions.get(region), "lat": lat, "lon": lon,
            "contact_name": name, "violation": "none", "reason": REASON,
            "moderated_at": now, "published_at": now, "expires_at": until or now + timedelta(days=30),
        })


def remove_ads(apps, schema_editor):
    Ad = apps.get_model("classifieds", "Ad")
    for ad in ADS:
        Ad.objects.filter(title=ad[1], phone=ad[7]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("classifieds", "0004_photo_checked_status"),
        ("news", "0012_article_cover_manual"),
    ]

    operations = [migrations.RunPython(add_ads, remove_ads)]
