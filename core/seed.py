"""Стартовые данные. Используются в data-миграциях (через apps.get_model)."""

REGIONS = [
    # slug, name, locative, statewide, description
    ("miami", "Майами", "в Майами и Южной Флориде", False,
     "Новости Майами, Санни-Айлс-Бич, Авентуры, Холливуда и Форт-Лодердейла на русском"),
    ("orlando", "Орландо", "в Орландо", False, "Новости Орландо и Центральной Флориды на русском"),
    ("tampa", "Тампа", "в Тампе", False, "Новости Тампы, Сент-Питерсберга и Клируотера на русском"),
    ("jacksonville", "Джексонвилл", "в Джексонвилле", False, "Новости Джексонвилла на русском"),
    ("florida", "Весь штат", "во Флориде", True, "Законы, погода и новости всего штата Флорида на русском"),
]

TOPICS = [
    # slug, name, short, priority, cover
    ("weather", "Погода и ураганы", "Погода", 1, "covers/weather"),
    ("safety", "Безопасность и ЧП", "ЧП", 1, "covers/safety"),
    ("laws", "Законы и правила", "Законы", 2, "covers/laws"),
    ("housing", "Жильё и страховка", "Жильё", 2, "covers/housing"),
    ("roads", "Дороги и транспорт", "Дороги", 2, "covers/roads"),
    ("money", "Деньги и цены", "Деньги", 3, "covers/money"),
    ("education", "Школы и дети", "Школы", 3, "covers/education"),
    ("health", "Здоровье", "Здоровье", 3, "covers/health"),
    ("events", "Афиша и события", "Афиша", 4, "covers/events"),
    ("incidents", "Происшествия", "Происшествия", 5, "covers/incidents"),
]

SITE_OWNER = "CITRUSTACK LLC"

# Текст политики до появления владельца — по нему миграция понимает, что страницу не правили вручную.
PRIVACY_V1 = """Мы не требуем регистрации и не собираем персональные данные читателей.

Сайт может использовать технические cookie, необходимые для его работы. Если в будущем мы подключим счётчики посещаемости или рекламные сети (например, Google AdSense), они могут использовать собственные cookie — мы обновим эту страницу и опишем, какие данные и зачем собираются.

Если вы пишете нам на электронную почту, мы используем ваш адрес только для ответа и не передаём его третьим лицам.

По вопросам, связанным с данными, пишите на адрес редакции, указанный на странице «Контакты»."""

DISCLAIMER = (
    "Мы пересказываем новости своими словами и всегда даём ссылку на первоисточник. "
    "Это не юридическая и не финансовая консультация."
)

# Текст «О проекте» до раздела E-E-A-T — по нему миграция понимает, что страницу не правили вручную.
ABOUT_V2 = f"""\
«Флорида Сегодня» — новости штата Флорида на русском языке для русско- и украиноязычных жителей \
Майами, Санни-Айлс-Бич, Авентуры, Орландо, Тампы и Джексонвилла.

Дважды в день, утром и вечером, мы просматриваем местные СМИ и официальные источники: сообщения \
губернатора, службы по чрезвычайным ситуациям, Национального центра по ураганам и \
Национальной метеослужбы США. Отбираем то, что действительно важно для жизни во Флориде, — \
погоду и ураганы, законы и правила, деньги и быт, события в городах — и коротко пересказываем \
своими словами: что случилось, кого касается и что делать.

Мы не перепечатываем чужие статьи и не берём чужие фотографии. Под каждой заметкой — ссылки \
на первоисточники, где можно прочитать подробности.

В подготовке заметок помогает искусственный интеллект. Срочные сообщения официальных служб \
и проверенные заметки публикуются автоматически, а всё, что касается криминала, частных лиц, \
детей и обвинений, редактор проверяет вручную.

{DISCLAIMER}"""

PAGES = [
    ("about", "О проекте", 1, f"""\
«Florida RU» (florida-ru.com) — новости штата Флорида на русском языке для русско- и украиноязычных \
жителей Майами, Санни-Айлс-Бич, Авентуры, Орландо, Тампы и Джексонвилла.

Издатель сайта — компания CITRUSTACK LLC, Флорида. Связаться с редакцией можно через страницу «Контакты».

Как мы работаем. Дважды в день, утром и вечером, мы просматриваем местные СМИ и официальные \
источники: сообщения губернатора, службы по чрезвычайным ситуациям, Национального центра по ураганам \
и Национальной метеослужбы США. Отбираем то, что действительно важно для жизни во Флориде, — погоду \
и ураганы, законы и правила, деньги и быт, события в городах — и коротко пересказываем своими словами: \
что случилось, кого касается и что с этим делать. Под каждой заметкой — ссылки на первоисточники.

Тексты готовятся с помощью искусственного интеллекта. ИИ помогает отобрать новости, пересказать их \
по-русски и сверить пересказ с источниками, а редакция проверяет заметки и исправляет ошибки. \
Мы не перепечатываем чужие статьи, не берём чужие фотографии и ничего не публикуем только на \
основании постов в соцсетях.

Если вы нашли ошибку, сообщите через страницу «Исправления»: мы быстро исправляем и помечаем \
исправление в заметке. Вопросы об авторских правах — на странице «Авторские права и DMCA».

{DISCLAIMER}"""),
    ("advertising", "Реклама", 2, """\
Мы размещаем прямую рекламу местного русскоязычного бизнеса Флориды: врачей, юристов, \
риелторов, страховых агентов, автосервисов, школ и магазинов.

Форматы: широкий баннер под шапкой сайта, блок в боковой колонке и блок в ленте новостей. \
Рекламу можно показывать по всему сайту или только в разделе нужного города — Майами, \
Орландо, Тампы или Джексонвилла.

Все рекламные материалы помечаются словом «Реклама». Мы не публикуем рекламу под видом новостей.

Чтобы обсудить размещение, напишите нам — контакты на странице «Контакты»."""),
    ("contacts", "Контакты", 3, """\
Нашли ошибку, хотите сообщить новость или обсудить рекламу — напишите нам.

Электронная почта редакции указана ниже. Мы отвечаем в течение одного-двух рабочих дней.

Если вы заметили неточность в заметке, пришлите ссылку на неё — мы проверим и исправим."""),
    ("privacy", "Политика конфиденциальности", 4, """\
Сайт «Florida RU» принадлежит компании CITRUSTACK LLC и управляется ею (далее — «мы»). \
Эта политика объясняет, какие данные мы получаем и как их используем.

Мы не требуем регистрации и не собираем персональные данные читателей.

Сайт может использовать технические cookie, необходимые для его работы. Если в будущем \
мы подключим счётчики посещаемости или рекламные сети (например, Google AdSense), они могут \
использовать собственные cookie — мы обновим эту страницу и опишем, какие данные и зачем \
собираются.

Если вы пишете нам на электронную почту, мы используем ваш адрес только для ответа и не \
передаём его третьим лицам.

По вопросам, связанным с данными, пишите CITRUSTACK LLC на адрес редакции, указанный на \
странице «Контакты»."""),
    ("disclaimer", "Отказ от ответственности", 5, f"""\
{DISCLAIMER}

Заметки на сайте — краткий пересказ сообщений СМИ и официальных источников. Информация может \
меняться: при угрозе урагана, эвакуации или других чрезвычайных ситуациях всегда следуйте \
указаниям местных властей и официальных служб (FDEM, NHC, NWS, офис шерифа вашего округа).

Перед принятием юридических, финансовых, медицинских или иммиграционных решений \
проконсультируйтесь с профильным специалистом.

Права на исходные материалы принадлежат их авторам. Ссылки на первоисточники приведены \
под каждой заметкой."""),
]

# Кандидаты в источники. ВСЕ создаются неактивными и непроверенными: адреса нужно
# проверить командой `python manage.py check_sources --activate` из сети с доступом
# к этим сайтам. Нерабочие останутся выключенными с текстом ошибки.
# name, homepage, url, kind, type, region, trust, notes
SOURCES = [
    # Погода — официальные
    ("National Hurricane Center (Атлантика)", "https://www.nhc.noaa.gov/",
     "https://www.nhc.noaa.gov/index-at.xml", "rss", "weather", "florida", 10,
     "Все бюллетени NHC по Атлантике"),
    ("NHC: прогноз тропической активности", "https://www.nhc.noaa.gov/",
     "https://www.nhc.noaa.gov/gtwo.xml", "rss", "weather", "florida", 10,
     "Tropical Weather Outlook"),
    ("NWS: предупреждения по Флориде", "https://www.weather.gov/",
     "https://api.weather.gov/alerts/active?area=FL", "nws_alerts", "weather", "florida", 10,
     "GeoJSON API; опасные события сразу идут в конвейер как срочные"),
    # Штат
    ("Florida Politics", "https://floridapolitics.com/",
     "https://floridapolitics.com/feed/", "rss", "media", "florida", 7, ""),
    ("Florida Phoenix", "https://floridaphoenix.com/",
     "https://floridaphoenix.com/feed/", "rss", "media", "florida", 8, ""),
    # Орландо
    ("ClickOrlando (News 6)", "https://www.clickorlando.com/",
     "https://www.clickorlando.com/arc/outboundfeeds/rss/?outputType=xml", "rss", "media", "orlando", 7, ""),
    ("WESH 2", "https://www.wesh.com/", "https://www.wesh.com/topstories-rss", "rss", "media", "orlando", 7, ""),
    ("WFTV 9", "https://www.wftv.com/",
     "https://www.wftv.com/arc/outboundfeeds/rss/?outputType=xml", "rss", "media", "orlando", 7, ""),
    ("FOX 35 Orlando", "https://www.fox35orlando.com/",
     "https://www.fox35orlando.com/rss/category/news", "rss", "media", "orlando", 6, ""),
    ("Orlando Sentinel", "https://www.orlandosentinel.com/",
     "https://www.orlandosentinel.com/feed/", "rss", "media", "orlando", 8, ""),
    # Тампа
    ("Tampa Bay Times", "https://www.tampabay.com/",
     "https://www.tampabay.com/arc/outboundfeeds/rss/?outputType=xml", "rss", "media", "tampa", 8, ""),
    ("FOX 13 Tampa Bay", "https://www.fox13news.com/",
     "https://www.fox13news.com/rss/category/news", "rss", "media", "tampa", 6, ""),
    ("WFLA 8", "https://www.wfla.com/", "https://www.wfla.com/feed/", "rss", "media", "tampa", 7, ""),
    # Южная Флорида
    ("WPLG Local 10", "https://www.local10.com/",
     "https://www.local10.com/arc/outboundfeeds/rss/?outputType=xml", "rss", "media", "miami", 7, ""),
    ("NBC 6 South Florida", "https://www.nbcmiami.com/",
     "https://www.nbcmiami.com/feed/", "rss", "media", "miami", 7, ""),
    ("WSVN 7", "https://wsvn.com/", "https://wsvn.com/feed/", "rss", "media", "miami", 6, ""),
    # Джексонвилл
    ("News4JAX", "https://www.news4jax.com/",
     "https://www.news4jax.com/arc/outboundfeeds/rss/?outputType=xml", "rss", "media", "jacksonville", 7, ""),
    ("First Coast News", "https://www.firstcoastnews.com/",
     "https://www.firstcoastnews.com/feeds/syndication/rss/news", "rss", "media", "jacksonville", 7, ""),
]


def seed_regions_topics(apps, schema_editor):
    Region = apps.get_model("news", "Region")
    Topic = apps.get_model("news", "Topic")
    for order, (slug, name, loc, statewide, desc) in enumerate(REGIONS):
        Region.objects.update_or_create(slug=slug, defaults={
            "name": name, "name_locative": loc, "is_statewide": statewide, "description": desc, "order": order,
        })
    for order, (slug, name, short, priority, cover) in enumerate(TOPICS):
        Topic.objects.update_or_create(slug=slug, defaults={
            "name": name, "short_name": short, "priority": priority, "cover": cover, "order": order,
        })


def seed_pages(apps, schema_editor):
    Page = apps.get_model("core", "Page")
    SiteSettings = apps.get_model("core", "SiteSettings")
    for slug, title, order, body in PAGES:
        Page.objects.get_or_create(slug=slug, defaults={"title": title, "order": order, "body": body})
    SiteSettings.objects.get_or_create(pk=1)


def seed_sources(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    Region = apps.get_model("news", "Region")
    for name, homepage, url, kind, stype, region, trust, notes in SOURCES:
        Source.objects.get_or_create(url=url, defaults={
            "name": name, "homepage": homepage, "kind": kind, "source_type": stype,
            "region": Region.objects.filter(slug=region).first(), "trust_weight": trust,
            "is_active": False, "is_verified": False,
            "notes": notes or "Кандидат: адрес не проверен. Запустите check_sources --activate",
        })


def update_privacy_owner(apps, schema_editor):
    """Добавляет владельца в политику конфиденциальности, если её не меняли вручную."""
    Page = apps.get_model("core", "Page")
    new_body = next(body for slug, _, _, body in PAGES if slug == "privacy")
    page = Page.objects.filter(slug="privacy").first()
    if page and " ".join(page.body.split()) == " ".join(PRIVACY_V1.split()):
        page.body = new_body
        page.save(update_fields=["body"])


def update_about_schedule(apps, schema_editor):
    """«Каждые несколько часов» → «дважды в день» на странице «О проекте». Меняет только эту фразу."""
    Page = apps.get_model("core", "Page")
    page = Page.objects.filter(slug="about").first()
    old, new = "Каждые несколько часов мы просматриваем", "Дважды в день, утром и вечером, мы просматриваем"
    if page and old in page.body:
        page.body = page.body.replace(old, new)
        page.save(update_fields=["body"])


def update_about_and_brand(apps, schema_editor):
    """Новая «О проекте» (если её не правили) и название «Florida RU» на всех страницах."""
    Page = apps.get_model("core", "Page")
    about = Page.objects.filter(slug="about").first()
    if about and " ".join(about.body.split()) == " ".join(ABOUT_V2.split()):
        about.body = next(body for slug, _, _, body in PAGES if slug == "about")
        about.save(update_fields=["body"])
    for page in Page.objects.filter(body__contains="«Флорида Сегодня»"):
        page.body = page.body.replace("«Флорида Сегодня»", "«Florida RU»")
        page.save(update_fields=["body"])


def publication_limit_and_author(apps, schema_editor):
    """Лимит 40 «заметок» → 8 «публикаций» (если не меняли) и скрытая заглушка автора."""
    SiteSettings = apps.get_model("core", "SiteSettings")
    Author = apps.get_model("core", "Author")
    SiteSettings.objects.filter(max_articles_per_day=40).update(max_articles_per_day=8)
    Author.objects.get_or_create(slug="redaktor", defaults={
        "name": "Имя редактора", "role": "Редактор",
        "bio": "Заполните в админке: кто вы, опыт, чем занимаетесь в редакции. Пока автор выключен, "
               "на сайте его не видно.",
        "is_active": False,
    })
