"""Стартовые категории справочника, официальные ссылки и первые проверенные записи.

Бизнесы сюда не придумываем: добавляет редакция в админке после проверки (рекомендации читателей,
платные партнёры — с меткой «Партнёр»).
"""

# (slug, name, description, schema_type, order)
LINK_CATEGORIES = [
    ("ekstrennye-sluzhby", "Экстренные службы и погода",
     "Куда смотреть при урагане, наводнении и других ЧС: официальные сайты штата и федеральных служб.", "", 1),
    ("dokumenty-i-immigraciya", "Документы и иммиграция",
     "Права и ID, иммиграционные формы, номер социального страхования, паспорт.", "", 2),
    ("nalogi-i-dengi", "Налоги, деньги и бизнес",
     "Федеральные и штатные налоги, регистрация компании, кредитная история.", "", 3),
    ("rabota", "Работа и пособия", "Пособие по безработице, поиск работы, права работника.", "", 4),
    ("zdorove", "Здоровье и медстраховка", "Marketplace, Medicaid, KidCare, Medicare и департамент здравоохранения.", "", 5),
    ("obrazovanie", "Школы и образование", "Школы, детский сад VPK, стипендии и колледжи.", "", 6),
    ("zhile-i-strahovka", "Жильё и страховка", "Страховка дома и от наводнения, жалобы на страховые, гранты на укрепление дома.", "", 7),
    ("dorogi", "Дороги и транспорт", "Платные дороги, пробки и перекрытия.", "", 8),
    ("moshennichestvo", "Защита от мошенников", "Куда сообщить о мошенничестве и проверить, не обман ли это.", "", 9),
]

BUSINESS_CATEGORIES = [
    ("cerkvi", "Церкви и религиозные общины", "Православные и другие приходы, где служат или говорят по-русски и по-украински.", "Church", 1),
    ("vrachi", "Врачи и клиники", "Семейные врачи, педиатры и клиники с русскоязычным персоналом.", "MedicalClinic", 2),
    ("stomatologi", "Стоматологи", "Стоматологические клиники, где говорят по-русски или по-украински.", "Dentist", 3),
    ("yuristy", "Юристы и иммиграционные адвокаты", "Иммиграционные адвокаты, юристы по ДТП, аренде и семейным делам.", "LegalService", 4),
    ("buhgaltery", "Бухгалтеры и налоги", "Налоговые декларации, ITIN, бухгалтерия для малого бизнеса.", "AccountingService", 5),
    ("nedvizhimost", "Недвижимость и аренда", "Риелторы, ипотечные брокеры, управление арендой.", "RealEstateAgent", 6),
    ("strahovanie", "Страховые агенты", "Автострахование, страховка дома и медстраховка.", "InsuranceAgency", 7),
    ("avto", "Автосервис и автосалоны", "Ремонт, техобслуживание, покупка машин.", "AutoRepair", 8),
    ("produkty", "Магазины и продукты", "Русские, украинские и европейские магазины и деликатесы.", "GroceryStore", 9),
    ("restorany", "Рестораны и кафе", "Кухня Восточной Европы, Грузии и Средней Азии.", "Restaurant", 10),
    ("krasota", "Красота и здоровье", "Салоны красоты, массаж, фитнес.", "BeautySalon", 11),
    ("deti", "Детские сады, кружки и репетиторы", "Детские сады, школы выходного дня, кружки, репетиторы.", "EducationalOrganization", 12),
    ("prazdniki", "Праздники и развлечения", "Аниматоры, шоу и организация детских и семейных праздников.", "EntertainmentBusiness", 12),
    ("pozhilye", "Уход за пожилыми и дневные центры", "Дневные центры для пенсионеров, уход на дому, досуг для старшего поколения.", "LocalBusiness", 2),
    ("podarki", "Подарки, цветы и сладости на заказ", "Торты, букеты, сладкие подарки и композиции с доставкой.", "Store", 12),
    ("perevody", "Переводы и нотариус", "Сертифицированные переводы, нотариусы, апостиль.", "ProfessionalService", 13),
    ("remont", "Ремонт и строительство", "Ремонт, кровля, кондиционеры, электрика — с лицензией штата.", "HomeAndConstructionBusiness", 14),
    ("zhivotnye", "Животные: груминг, ветеринары, зоотовары", "Груминг, ветеринарные клиники, зоомагазины и передержка.", "PetStore", 14),
    ("pereezd", "Переезд и доставка", "Переезды, перевозка машин, посылки.", "MovingCompany", 15),
    ("drugoe", "Другие услуги", "Всё, что не вошло в другие категории.", "LocalBusiness", 16),
]

# category slug -> [(name, url, phone, description, guide slug, order)]
LINKS = {
    "ekstrennye-sluzhby": [
        ("Florida Division of Emergency Management", "https://www.floridadisaster.org/", "",
         "Официальный сайт ЧС Флориды: подготовка к урагану, приказы об эвакуации, убежища.", "podgotovka-k-uraganu", 1),
        ("Know Your Zone — узнать свою зону эвакуации", "https://www.floridadisaster.org/knowyourzone/", "",
         "Введите адрес — сайт покажет зону эвакуации и ссылку на округ.", "zony-evakuacii", 2),
        ("National Hurricane Center", "https://www.nhc.noaa.gov/", "",
         "Прогнозы и конусы ураганов, предупреждения watch и warning.", "podgotovka-k-uraganu", 3),
        ("National Weather Service", "https://www.weather.gov/", "",
         "Официальные прогнозы и предупреждения о жаре, грозах, наводнениях по вашему адресу.", "zhara-molnii-techeniya-alligatory", 4),
        ("FEMA — помощь после бедствий", "https://www.disasterassistance.gov/", "1-800-621-3362",
         "Заявка на федеральную помощь после урагана или наводнения.", "posle-uragana", 5),
        ("Poison Control — отравления", "https://poisonhelp.hrsa.gov/", "1-800-222-1222",
         "Бесплатная круглосуточная линия при отравлении, в том числе угарным газом. При угрозе жизни — 911.",
         "generator-bez-ugarnogo-gaza", 6),
    ],
    "dokumenty-i-immigraciya": [
        ("FLHSMV — права, ID и машины", "https://www.flhsmv.gov/", "",
         "Водительские права, Florida ID, регистрация машины, проверка статуса прав.", "prava-vo-floride-dlya-priezzhih", 1),
        ("USCIS — иммиграционная служба", "https://www.uscis.gov/", "",
         "Формы, пошлины, статус дела, смена адреса, гражданство и грин-карта.", "grin-karta", 2),
        ("Social Security Administration", "https://www.ssa.gov/", "",
         "Номер социального страхования, замена карточки, пенсии и Medicare.", "ssn-i-itin", 3),
        ("Паспорт США — Госдепартамент", "https://travel.state.gov/content/travel/en/passports.html", "",
         "Первый паспорт после гражданства, продление, срочное оформление.", "grazhdanstvo-ssha", 4),
        ("Бесплатная иммиграционная помощь (EOIR)", "https://www.justice.gov/eoir/find-legal-representation", "",
         "Списки аккредитованных организаций и бесплатных юридических услуг Минюста.", "moshennichestvo", 5),
    ],
    "nalogi-i-dengi": [
        ("IRS — налоговая служба", "https://www.irs.gov/", "",
         "Федеральные налоги, ITIN, бесплатная подача декларации (Free File), статус возврата.", "nalogi-shtata", 1),
        ("Florida Department of Revenue", "https://floridarevenue.com/", "",
         "Налог с продаж, налоговые каникулы, налог на недвижимость.", "nalogi-shtata", 2),
        ("Sunbiz — регистрация компаний", "https://dos.fl.gov/sunbiz/", "",
         "Регистрация LLC и корпораций, годовой отчёт, Fictitious Name.", "svoj-biznes-llc", 3),
        ("AnnualCreditReport.com", "https://www.annualcreditreport.com/", "",
         "Единственный официальный сайт бесплатных кредитных отчётов трёх бюро.", "bankovskij-schet-i-kreditnaya-istoriya", 4),
        ("CFPB — защита потребителей финансовых услуг", "https://www.consumerfinance.gov/", "",
         "Жалобы на банки, кредиты и коллекторов, понятные объяснения.", "bankovskij-schet-i-kreditnaya-istoriya", 5),
    ],
    "rabota": [
        ("FloridaCommerce — пособие по безработице", "https://www.floridajobs.org/", "",
         "Reemployment Assistance: подача заявки и еженедельные отметки.", "posobie-po-bezrabotice", 1),
        ("Employ Florida — поиск работы", "https://www.employflorida.com/", "",
         "Вакансии штата и обязательная регистрация для получателей пособия.", "posobie-po-bezrabotice", 2),
        ("US Department of Labor — Wage and Hour", "https://www.dol.gov/agencies/whd", "",
         "Жалобы на невыплату зарплаты и сверхурочных.", "prava-rabotnika", 3),
    ],
    "zdorove": [
        ("HealthCare.gov — Marketplace", "https://www.healthcare.gov/", "",
         "Медстраховка с субсидиями, сроки записи, проверка права на помощь.", "medstrahovka-marketplace-medicaid", 1),
        ("ACCESS Florida — Medicaid и продуктовая помощь", "https://www.myflorida.com/accessflorida/", "",
         "Заявки на Medicaid, SNAP и денежную помощь в штате.", "medstrahovka-marketplace-medicaid", 2),
        ("Florida KidCare", "https://www.floridakidcare.org/", "",
         "Медстраховка для детей до 19 лет.", "medstrahovka-marketplace-medicaid", 3),
        ("Medicare.gov", "https://www.medicare.gov/", "",
         "Сравнение планов Medicare, сроки записи, покрытие.", "medicare", 4),
        ("Florida Department of Health", "https://www.floridahealth.gov/", "",
         "Департаменты здоровья округов, прививки, проверка лицензий врачей.", "kak-najti-vracha", 5),
    ],
    "obrazovanie": [
        ("Florida Department of Education", "https://www.fldoe.org/", "",
         "Школы, выбор школы, стипендии, сертификация учителей.", "zapis-v-shkolu", 1),
        ("Florida Division of Early Learning — VPK", "https://www.fldoe.org/schools/early-learning/parents/vpk-parents.stml", "",
         "Бесплатный детский сад VPK для 4-летних и субсидии School Readiness.", "vpk-detskij-sad", 2),
        ("Bright Futures и стипендии штата", "https://www.floridastudentfinancialaidsg.org/", "",
         "Стипендии Bright Futures, FSAG и другие программы Флориды.", "kolledzh-in-state-bright-futures", 3),
        ("Step Up For Students", "https://www.stepupforstudents.org/", "",
         "Заявки на школьные стипендии (FES, FTC) для частных школ и домашнего обучения.", "zapis-v-shkolu", 4),
    ],
    "zhile-i-strahovka": [
        ("Florida Office of Insurance Regulation", "https://floir.com/", "",
         "Регулятор страховых компаний: информация о страховщиках и рынке.", "strahovka-doma-i-navodneniya", 1),
        ("Florida Department of Financial Services", "https://www.myfloridacfo.com/", "",
         "Жалобы на страховые, медиация после урагана, проверка агентов.", "posle-uragana", 2),
        ("Citizens Property Insurance", "https://www.citizensfla.com/", "",
         "Государственный страховщик жилья последней инстанции.", "strahovka-doma-i-navodneniya", 3),
        ("FloodSmart — страховка от наводнения (NFIP)", "https://www.floodsmart.gov/", "",
         "Федеральная программа страхования от наводнения.", "strahovka-doma-i-navodneniya", 4),
        ("My Safe Florida Home", "https://mysafeflhome.com/", "",
         "Бесплатная инспекция и гранты на укрепление дома от ураганов.", "strahovka-doma-i-navodneniya", 5),
    ],
    "dorogi": [
        ("SunPass", "https://www.sunpass.com/", "",
         "Транспондер и оплата платных дорог Флориды.", "sunpass-i-platnye-dorogi", 1),
        ("Florida 511 — пробки и перекрытия", "https://fl511.com/", "",
         "Дорожная обстановка, аварии и перекрытия в реальном времени.", "sunpass-i-platnye-dorogi", 2),
    ],
    "moshennichestvo": [
        ("ReportFraud.ftc.gov", "https://reportfraud.ftc.gov/", "",
         "Сообщить о мошенничестве в Федеральную торговую комиссию.", "moshennichestvo", 1),
        ("Генеральный прокурор Флориды", "https://www.myfloridalegal.com/", "",
         "Жалобы на мошенников и недобросовестные компании во Флориде.", "moshennichestvo", 2),
        ("FDACS — защита потребителей", "https://www.fdacs.gov/Consumer-Resources", "",
         "Жалобы потребителей, проверка компаний, запрет на звонки.", "moshennichestvo", 3),
        ("IC3 — интернет-мошенничество (FBI)", "https://www.ic3.gov/", "",
         "Сообщить о мошенничестве в интернете и с криптовалютой.", "moshennichestvo", 4),
    ],
}

# Бизнесы: только проверенные редакцией записи.
BUSINESSES = {
    "cerkvi": [{
        "name": "Православный приход Святой Нины (Saint Nina Orthodox Church)",
        "url": "https://www.stninaorlando.org/",
        "address": "6832 Hanging Moss Rd, Orlando, FL 32807",
        "city": "Орландо",
        "region": "orlando",
        "languages": "английский, церковнославянский; прихожане говорят по-русски, по-украински, по-грузински",
        "hours": "Вечерня в субботу вечером, Божественная Литургия в воскресенье утром, по средам — чтение и обсуждение Евангелия; точное расписание — на сайте",
        "description": "Православная миссия в Орландо (Православная Церковь в Америке, Южная епархия). "
                       "Среди прихожан — американцы, украинцы, русские, белорусы, грузины. Службы в основном "
                       "на английском, с частями на церковнославянском. Можно прийти впервые, без подготовки: "
                       "после воскресной Литургии остаются на кофе и общение.",
        "is_recommended": True,
    }],
}


def seed_directory(apps, schema_editor):
    Category = apps.get_model("directory", "Category")
    Listing = apps.get_model("directory", "Listing")
    Region = apps.get_model("news", "Region")
    for kind, rows in (("links", LINK_CATEGORIES), ("business", BUSINESS_CATEGORIES)):
        for slug, name, description, schema_type, order in rows:
            Category.objects.get_or_create(slug=slug, defaults={
                "kind": kind, "name": name, "description": description,
                "schema_type": schema_type or "", "order": order,
            })
    for slug, rows in LINKS.items():
        category = Category.objects.get(slug=slug)
        for name, url, phone, description, guide_slug, order in rows:
            Listing.objects.get_or_create(category=category, url=url, defaults={
                "name": name, "phone": phone, "description": description, "order": order,
                "guide_slug": guide_slug,
            })
    for slug, rows in BUSINESSES.items():
        category = Category.objects.get(slug=slug)
        for row in rows:
            row = dict(row)
            region = Region.objects.filter(slug=row.pop("region", "")).first()
            Listing.objects.get_or_create(category=category, url=row["url"], defaults={**row, "region": region})


def import_businesses(apps, schema_editor, filename="businesses_2026_10.json"):
    """Бизнесы из таблицы редакции (directory/data/*.json). Скрытые (active=false) ждут проверки в админке."""
    import json
    from pathlib import Path

    Category = apps.get_model("directory", "Category")
    Listing = apps.get_model("directory", "Listing")
    Region = apps.get_model("news", "Region")
    rows = json.loads((Path(__file__).parent / "data" / filename).read_text(encoding="utf-8"))
    for row in rows:
        category = Category.objects.get(slug=row["category"])
        Listing.objects.get_or_create(category=category, name=row["name"], defaults={
            "description": row["description"], "url": row["url"], "phone": row["phone"],
            "address": row["address"], "city": row["city"], "languages": row["languages"],
            "region": Region.objects.filter(slug=row["region"]).first() if row["region"] else None,
            "is_active": row["active"], "editor_note": row["note"],
            "hours": row.get("hours", ""), "is_recommended": row.get("recommended", False),
        })


def import_wayside(apps, schema_editor):
    import_businesses(apps, schema_editor, "businesses_2026_10_wayside.json")


def apply_business_updates(apps, schema_editor, filename):
    """Обновления справочника: {"match": "существующее название"} дополняет запись, иначе создаётся новая.

    В объекте — только поля, которые нужно задать: name, category, region, city, description, languages,
    address, phone, url, hours, active, recommended, note.
    """
    import json
    from pathlib import Path

    Category = apps.get_model("directory", "Category")
    Listing = apps.get_model("directory", "Listing")
    Region = apps.get_model("news", "Region")
    rows = json.loads((Path(__file__).parent / "data" / filename).read_text(encoding="utf-8"))
    fields = {"name": "name", "description": "description", "languages": "languages", "address": "address",
              "phone": "phone", "url": "url", "hours": "hours", "city": "city", "active": "is_active",
              "recommended": "is_recommended", "note": "editor_note", "guide": "guide_slug"}
    for row in rows:
        names = [n for n in (row.get("match"), row.get("name")) if n]
        item = Listing.objects.filter(name__in=names).first()
        if item is None:
            if not row.get("category"):
                continue  # обновлять нечего: запись удалили вручную
            item = Listing(category=Category.objects.get(slug=row["category"]))
        elif row.get("category"):
            item.category = Category.objects.get(slug=row["category"])
        for key, attr in fields.items():
            if key in row:
                setattr(item, attr, row[key])
        if "region" in row:
            item.region = Region.objects.filter(slug=row["region"]).first() if row["region"] else None
        item.save()


def import_batch2(apps, schema_editor):
    Category = apps.get_model("directory", "Category")
    for slug, name, description, schema_type, order in BUSINESS_CATEGORIES:
        Category.objects.get_or_create(slug=slug, defaults={
            "kind": "business", "name": name, "description": description, "schema_type": schema_type, "order": order,
        })
    apply_business_updates(apps, schema_editor, "businesses_2026_10_batch2.json")
