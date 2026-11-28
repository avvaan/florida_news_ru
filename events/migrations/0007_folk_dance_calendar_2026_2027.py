"""Афиша: фольклорные и греческие фестивали Флориды из календаря floridafolkdancer.org (14.11.2026).

Из календаря Florida Folk Dance Council взяты только события во Флориде. Каждое сверено с сайтом
организатора: даты, часы, площадка и цена — оттуда. Не вошли: Machol Miami (даты 2026 нет на официальных
страницах), греческий фестиваль в Мельбурне (дата 2027 не объявлена), праздник клуба в Орландо 16.12
и Fall Fling 2027 (нет ни площадки, ни времени). Если цена на 2027 год не объявлена, поле пустое.

Заодно поправлен Фестиваль славянской еды (0003): организаторы перенесли его в Reiter Park в Лонгвуде
и сделали вход бесплатным.
"""

from datetime import date, time

from django.db import migrations
from django.utils import timezone

from core.text import make_slug

# (начало, конец, время, название, описание, (площадка, адрес, город, регион), цена, ссылка, организатор)
EVENTS = [
    (date(2026, 11, 12), date(2026, 11, 15), time(11), "Греческий фестиваль в Дейтона-Бич",
     "49-й греческий фестиваль при церкви Святого Димитрия: гирос, сувлаки, пастицио, мусака, долма, кальмары "
     "и пахлава, греческий кофе, пиво, вино и узо. Выступают ансамбль греческого танца и живая группа. "
     "С четверга по субботу — с 11:00 до 21:00, в воскресенье — до 18:00. Бесплатный шаттл.",
     ("Церковь Святого Димитрия", "129 N Halifax Ave", "Дейтона-Бич", "orlando"), "Вход свободный",
     "http://www.greekfestivaldaytonabeach.com/", "Saint Demetrios Greek Orthodox Church"),
    (date(2026, 11, 13), date(2026, 11, 15), time(16), "Jax Greek Fest — греческий фестиваль в Джексонвилле",
     "Семейный греческий фестиваль: домашняя греческая еда и десерты, живая музыка и танцы. "
     "Пятница — 16:00–21:00, суббота — 10:00–21:00, воскресенье — 11:00–17:00. Парковка бесплатная.",
     ("Церковь Святого Иоанна Богослова", "12760 Beach Blvd", "Джексонвилл", "jacksonville"),
     "$5, оплата только картой", "http://jaxgreekfest.com/", "St. John the Divine Greek Orthodox Church"),
    (date(2026, 11, 28), date(2026, 11, 29), time(10), "FusionFest — мультикультурный фестиваль Орландо",
     "Бесплатный фестиваль культур мира: больше 110 культур и 500 местных артистов на главной сцене, мастер-классы "
     "танцев народов мира, еда разных кухонь, показ национальных костюмов, выставки и занятия для детей. "
     "Суббота — 10:00–20:00, воскресенье — 12:00–18:00.",
     ("Loch Haven Park", "777 E Princeton St", "Орландо", "orlando"), "Бесплатно",
     "https://fusionfest.org/annual-festival-2026/", "FusionFest"),
    (date(2027, 1, 22), date(2027, 1, 24), time(19, 30), "Florida Snow Ball — выходные контрданса",
     "Три дня контрданса, кадрилей и парных танцев под живую музыку групп Engine Room и River Road, "
     "ведущие — Seth Tepfer и Alexandra Deis-Lauby. Первый танец в пятницу в 19:30, в субботу — танцы весь день "
     "и вечерний бал, в воскресенье — до обеда. Нужна регистрация на сайте.",
     ("Спортзал Boca Ciega High School", "924 58th St S", "Галфпорт", "tampa"),
     "$135 за выходные, молодёжь — $75", "https://floridasnowball.com/", "Tampa Friends of Old-Time Dance"),
    (date(2027, 2, 5), date(2027, 2, 7), time(11), "Super Greek Fest — греческий фестиваль в Сент-Питерсберге",
     "Три дня греческой еды, музыки и танцев: гирос и сувлаки, греческое кафе, уроки греческого танца и языка, "
     "экскурсии по храму, ярмарка и детская зона. Пятница и суббота — 11:00–22:00, воскресенье — 11:00–18:00. "
     "Проходит в любую погоду, парковка бесплатная.",
     ("Церковь Святого Стефана", "3600 76th St N", "Сент-Питерсберг", "tampa"),
     "$3, дети до 10 лет и военные — бесплатно", "http://ststefanos.org/events/super-greek-fest",
     "St. Stefanos Greek Orthodox Church"),
    (date(2027, 2, 5), date(2027, 2, 8), None, "Зимний семинар народного танца Florida Folk Dance Council",
     "Ежегодные выходные международного народного танца: боснийские танцы ведёт Efie Derksen, болгарские — "
     "Konstantin Marinov, вечерние танцы под живую музыку. В пятницу вечеринка, в субботу и воскресенье "
     "занятия и вечеринки, в понедельник повторение. Регистрация — на сайте совета.",
     ("Holiday Inn Celebration", "5711 W Irlo Bronson Memorial Hwy", "Киссимми", "orlando"),
     "Пятница $25, суббота или воскресенье $80, пакет с отелем от $484",
     "https://floridafolkdancer.org/Camp2027/index.html", "Florida Folk Dance Council"),
    (date(2027, 2, 19), date(2027, 2, 21), time(11), "Glendi — греческий фестиваль в Сарасоте",
     "42-й фестиваль при церкви Святой Варвары: греческая еда, напитки и выпечка, живая греческая музыка, "
     "выступления ансамбля St. Barbara Hellenic Dancers, ярмарка, экскурсии по храму и лотерея. "
     "Пятница и суббота — 11:00–21:00, воскресенье — 12:00–18:00. Билеты — только на входе, парковка бесплатная.",
     ("Церковь Святой Варвары", "7671 Lockwood Ridge Rd", "Сарасота", "tampa"),
     "$5 за три дня, дети до 12 лет — бесплатно", "https://stbarbarafestival.org/",
     "St. Barbara Greek Orthodox Church"),
    (date(2027, 2, 19), date(2027, 2, 21), time(11), "Греческий фестиваль в Форт-Майерсе",
     "Фестиваль при Благовещенской церкви, который проходит больше 50 лет: греческая еда и вино, живая музыка, "
     "народные танцы, экскурсии по храму, аттракционы для детей и лотерея. Пятница и суббота — 11:00–23:00, "
     "воскресенье — 11:00–19:00. Цену входа на 2027 год организаторы ещё не объявили.",
     ("Благовещенская церковь", "8210 Cypress Lake Dr", "Форт-Майерс", ""), "",
     "https://greekfestfortmyers.com/", "Annunciation Greek Orthodox Church"),
    (date(2027, 3, 6), None, None, "SPIFFS — Международная фольклорная ярмарка",
     "51-я ярмарка Международного фольклорного общества Сент-Питерсберга: еда, танцы, музыка и напитки примерно "
     "двух десятков народов, ярмарка мастеров, парад наций и концерты на нескольких сценах. В прошлом году "
     "выступали русские и украинские коллективы. 4 и 5 марта — дни для школ, для всех открыта суббота, 6 марта. "
     "Время и цены на 2027 год ещё не объявлены.",
     ("England Brothers Park", "5010 81st Ave N", "Пинеллас-Парк", "tampa"), "",
     "https://www.spiffs.org/folkfair", "St. Petersburg International Folk Fair Society"),
]

SLAVIC = "festival-slavyanskoy-edy-2027-02-27"


def _slug(day, title, city):
    return make_slug(f"{title} {city} {day:%Y-%m-%d}", max_length=110)


def add_events(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Region = apps.get_model("news", "Region")
    regions = {r.slug: r for r in Region.objects.all()}
    now = timezone.now()
    for day, last, start, title, text, (venue, address, city, region), price, url, organizer in EVENTS:
        Event.objects.update_or_create(slug=_slug(day, title, city), defaults={
            "status": "approved", "title": title, "description": text,
            "starts_on": day, "starts_at": start, "ends_on": last,
            "venue": venue, "address": address, "city": city, "region": regions.get(region),
            "price": price, "url": url, "organizer": organizer,
            "contact_name": "Редакция Florida RU", "contact_email": "info@florida-ru.com",
            "violation": "none", "reason": "Добавлено редакцией по календарю floridafolkdancer.org от 14.11.2026",
            "moderated_at": now,
        })
    Event.objects.filter(slug=SLAVIC).update(
        venue="Reiter Park", address="311 W Warren Ave", city="Лонгвуд", price="Бесплатно",
        url="https://slavicfoodfestival.com/ru/",
        description="Семейный праздник на целый день в Reiter Park в Лонгвуде, с 10:00 до 20:00. Блюда готовят "
                    "прямо на месте: борщ, блины, вареники, шашлык, болгарские фаршированные перцы и булочки, "
                    "квас, компот и чай из самовара. На сцене — детская программа, русская программа Musical "
                    "Traditions, украинские, сербские, болгарские, польские и хорватские песни и танцы. Есть детская "
                    "зона и ярмарка. Вход бесплатный, еду оплачивают на месте наличными или картой. "
                    "Фестиваль проходит в любую погоду.",
    )


def remove_events(apps, schema_editor):
    slugs = [_slug(e[0], e[3], e[5][2]) for e in EVENTS]
    apps.get_model("events", "Event").objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0006_elka_winter_park_2026"),
        ("news", "0013_cover_manual_db_default"),
    ]

    operations = [migrations.RunPython(add_events, remove_events)]
