"""Афиша: концерты и стендап на русском во Флориде, октябрь 2026 — май 2027 (таблица редакции от 19.10.2026).

Источники таблицы — afishamira.com и worldafisha.com; ссылки на билеты проверены, площадки FEDUK и «Арии»
уточнены по «Афише мира». Адрес указан только там, где он точно известен. Цены — «от», уточняются
на странице билетов. Фестивали от редакции (0003) остаются сверху: их показывает блок «Главные события».
"""

from datetime import date, time

from django.db import migrations
from django.utils import timezone

from core.text import make_slug

GULFSTREAM = ("Sport of Kings Club, Gulfstream Park", "901 S Federal Hwy", "Халландейл-Бич", "miami")
LAUDERHILL = ("Lauderhill Performing Arts Center", "3800 NW 11th Pl", "Лодерхилл", "miami")
CENTRO = ("Centro Asturiano de Tampa", "1913 N Nebraska Ave", "Тампа", "tampa")

# (дата, время, название, тип, (площадка, адрес, город, регион), цена от, ссылка, организатор)
EVENTS = [
    (date(2026, 10, 23), time(20), "Мумий Тролль", "Концерт", GULFSTREAM, 70,
     "https://bnd.lc/mumiytrolltour", "Мумий Тролль"),
    (date(2026, 10, 24), time(20), "Антон Лирник — «Вид на жительство»", "Стендап",
     ("Wave Lounge", "", "Майами", "miami"), 65, "https://www.lirnik.com", "Антон Лирник"),
    (date(2026, 10, 24), time(20), "Мумий Тролль", "Концерт",
     ("Jannus Live", "200 1st Ave N", "Сент-Питерсберг", "tampa"), 80, "https://bnd.lc/mumiytrolltour", "Мумий Тролль"),
    (date(2026, 11, 6), time(20), "FEDUK — «15 лет в игре»", "Концерт",
     ("Sport of Kings Theater, Gulfstream Park", "901 S Federal Hwy", "Халландейл-Бич", "miami"), 85,
     "https://afishamira.com/event/feduk-v-majami/", "Афиша мира"),
    (date(2026, 11, 8), time(20), "Расул Чабдаров", "Стендап",
     ("Hollywood Performing Arts Center", "", "Холливуд", "miami"), None,
     "https://eventcartel.com/vendors/standup-tour", "Event Cartel"),
    (date(2026, 11, 10), time(20), "КИНО — «Невероятный концерт»", "Концерт", GULFSTREAM, 85,
     "https://kino.band/kontserty/2026/", "Группа КИНО"),
    (date(2026, 11, 14), time(19), "Александр Незлобин — «I'm файн»", "Стендап",
     ("Brooklyn Blues", "", "Сарасота", "tampa"), 55, "https://nezlobin.com/", "Александр Незлобин"),
    (date(2026, 11, 15), time(20), "Ария", "Концерт", GULFSTREAM, 75,
     "https://afishamira.com/event/gruppa-ariya-v-majami/", "Афиша мира"),
    (date(2026, 11, 23), time(20), "Anacondaz — «Ночь с астраханцем»", "Концерт",
     ("Wave Restaurant, Bar and Lounge", "", "Майами", "miami"), 50, "https://anacondaz.ru/", "Anacondaz"),
    (date(2026, 12, 3), time(18, 30), "Валерий Жидков", "Концерт",
     ("Cultural Community Center", "", "Халландейл-Бич", "miami"), 45, "https://linktr.ee/vareryzhidkov",
     "Валерий Жидков"),
    (date(2026, 12, 3), time(20), "Кристина Орбакайте", "Концерт", LAUDERHILL, 89,
     "https://eventcartel.com/ru/kristina-orbakaite-tickets/artist/31", "Event Cartel"),
    (date(2026, 12, 4), time(20), "Кристина Орбакайте", "Концерт", CENTRO, 69,
     "https://eventcartel.com/ru/kristina-orbakaite-tickets/artist/31", "Event Cartel"),
    (date(2026, 12, 26), time(18), "Александр Незлобин — рождественское шоу", "Стендап",
     ("Boca Black Box Center for the Arts", "", "Бока-Ратон", "miami"), None, "https://nezlobin.com/",
     "Александр Незлобин"),
    (date(2027, 1, 26), time(20), "Андрей Айрапетов", "Стендап",
     ("Savor Cinema", "503 SE 6th St", "Форт-Лодердейл", "miami"), 59, "https://airapetovcomedy.com/#tickets",
     "Андрей Айрапетов"),
    (date(2027, 2, 6), time(19), "Максим Галкин", "Концерт", LAUDERHILL, None,
     "https://eventcartel.com/ru/maxim-galkin-tickets/artist/30", "Event Cartel"),
    (date(2027, 2, 8), time(20), "Максим Галкин", "Концерт", CENTRO, None,
     "https://eventcartel.com/ru/maxim-galkin-tickets/artist/30", "Event Cartel"),
    (date(2027, 2, 19), time(20), "The HARDKISS", "Концерт", ("Площадка уточняется", "", "Тампа", "tampa"), 75,
     "https://www.thehardkiss.com/", "The HARDKISS"),
    (date(2027, 4, 7), time(20), "Каста", "Концерт", GULFSTREAM, 65, "https://kasta.world/tour/", "Каста"),
    (date(2027, 4, 9), time(20), "Каста", "Концерт", ("Brass Mug", "", "Тампа", "tampa"), None,
     "https://kasta.world/tour/", "Каста"),
    (date(2027, 5, 1), time(20), "Валерий Меладзе", "Концерт",
     ("James L. Knight Center", "400 SE 2nd Ave", "Майами", "miami"), 85, "https://tickets-meladze.com",
     "Валерий Меладзе"),
]


def describe(kind, title, venue, city, start, price) -> str:
    where = f"{venue}, {city}" if venue != "Площадка уточняется" else f"{city}, площадка уточняется"
    money = f"Билеты — от ${price}." if price else "Цены — на странице билетов."
    return (f"{kind} на русском языке: {title}. {where}, начало в {start:%H:%M}. {money} "
            "Перед покупкой проверьте дату, площадку и цену на странице билетов.")


def add_events(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Region = apps.get_model("news", "Region")
    regions = {r.slug: r for r in Region.objects.all()}
    now = timezone.now()
    for day, start, title, kind, (venue, address, city, region), price, url, organizer in EVENTS:
        slug = make_slug(f"{title} {city} {day:%Y-%m-%d}", max_length=110)
        Event.objects.update_or_create(slug=slug, defaults={
            "status": "approved", "title": title,
            "description": describe(kind, title, venue, city, start, price),
            "starts_on": day, "starts_at": start, "ends_on": None,
            "venue": venue, "address": address, "city": city, "region": regions.get(region),
            "price": f"от ${price}" if price else "", "url": url, "organizer": organizer,
            "contact_name": "Редакция Florida RU", "contact_email": "info@citrustack.com",
            "violation": "none", "reason": "Добавлено редакцией по таблице от 19.10.2026", "moderated_at": now,
        })


def remove_events(apps, schema_editor):
    slugs = [make_slug(f"{e[2]} {e[4][2]} {e[0]:%Y-%m-%d}", max_length=110) for e in EVENTS]
    apps.get_model("events", "Event").objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0003_festivals_2027"),
    ]

    operations = [migrations.RunPython(add_events, remove_events)]
