"""Стартовые темы гайдов: только заголовки, подсказки и официальные сайты. Текст пишет draft_guide."""

GUIDES = [
    ("prava-vo-floride-dlya-priezzhih", "Водительские права во Флориде для приезжих", ["laws", "roads"],
     "flhsmv.gov",
     "Как получить или обменять водительские права во Флориде после переезда из другого штата или страны: "
     "сроки, документы (REAL ID), экзамены, запись в офис, стоимость."),
    ("registraciya-mashiny", "Регистрация машины во Флориде", ["roads", "laws"], "flhsmv.gov",
     "Как зарегистрировать машину и получить номера во Флориде: сроки после переезда, страховка PIP/PDL, "
     "проверка VIN, title, стоимость, продление регистрации."),
    ("sunpass-i-platnye-dorogi", "SunPass и платные дороги Флориды", ["roads", "money"],
     "sunpass.com, floridasturnpike.com, fdot.gov",
     "Как работают платные дороги во Флориде: SunPass и другие транспондеры, Toll-By-Plate, тарифы, "
     "что будет, если проехать без транспондера, как оплатить счёт."),
    ("podgotovka-k-uraganu", "Как подготовиться к урагану", ["weather", "safety"],
     "floridadisaster.org, nhc.noaa.gov, ready.gov",
     "Как подготовиться к сезону ураганов: зоны эвакуации, набор на случай ЧС, план для семьи и животных, "
     "что значат watch и warning, где следить за официальными сообщениями."),
    ("strahovka-doma-i-navodneniya", "Страховка дома и страховка от наводнения", ["housing", "money"],
     "floir.com, myfloridacfo.com, floodsmart.gov, fema.gov",
     "Какая страховка жилья нужна во Флориде: homeowners и наводнение (NFIP), Citizens, франшиза на ураган, "
     "как подать претензию, куда жаловаться на страховую."),
    ("zapis-v-shkolu", "Как записать ребёнка в школу во Флориде", ["education"], "fldoe.org",
     "Как записать ребёнка в государственную школу во Флориде: документы, прививки, школьный округ, "
     "charter и magnet-школы, программы английского языка (ESOL)."),
    ("nalogi-shtata", "Налоги во Флориде: подоходного нет — что есть вместо него", ["money", "laws"],
     "floridarevenue.com",
     "Какие налоги платят жители Флориды: подоходного налога штата нет; налог с продаж и его ставки "
     "в округах, налог на недвижимость, налоговые каникулы."),
    ("arenda-zhilya-prava-arendatora", "Аренда жилья во Флориде: права арендатора", ["housing", "laws"],
     "flsenate.gov, leg.state.fl.us, fdacs.gov",
     "Права и обязанности арендатора во Флориде по закону штата (Chapter 83): залог, ремонт, уведомления, "
     "выселение, куда обращаться при споре с арендодателем."),
    ("homestead-exemption", "Homestead exemption: льгота на налог на жильё", ["housing", "money"],
     "floridarevenue.com",
     "Что такое Homestead exemption во Флориде: кто может получить, сколько экономит, ограничение роста "
     "оценки (Save Our Homes), сроки и куда подавать заявление."),
]


def seed_guides(apps, schema_editor):
    Guide = apps.get_model("guides", "Guide")
    Topic = apps.get_model("news", "Topic")
    for slug, title, topics, domains, brief in GUIDES:
        guide, created = Guide.objects.get_or_create(slug=slug, defaults={
            "title": title, "official_domains": domains, "brief": brief, "status": "draft",
        })
        if created:
            guide.topics.set(Topic.objects.filter(slug__in=topics))
