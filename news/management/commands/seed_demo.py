"""Демо-заметки для локального просмотра дизайна. Только при DJANGO_DEBUG=1.

Все тексты выдуманы и помечены тегом «демо»; ссылки ведут на главные страницы СМИ.
Удаление: python manage.py seed_demo --clear
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ads.models import AdBanner
from news.models import Article, ArticleSource, Region, Tag, Topic
from sources.models import WeatherAlert

DEMO = [
    # minutes ago, region, topic, urgent, score, title, teaser, body, sources
    (25, "tampa", "weather", True, 10,
     "Тропический шторм идёт к Тампе: в трёх округах объявили эвакуацию",
     "Эвакуация зоны A в округах Хиллсборо, Пинеллас и Паско. Убежища открываются с 14:00.",
     "Национальный центр по ураганам (NHC) повысил уровень угрозы для побережья залива Тампа. "
     "Власти округов Хиллсборо (Hillsborough), Пинеллас (Pinellas) и Паско (Pasco) объявили обязательную "
     "эвакуацию зоны A.\n\nКасается жителей прибрежных районов и мобильных домов. Проверить свою зону можно "
     "по адресу на сайте округа.\n\nЧто делать: заправьте машину, запаситесь водой на три дня, зарядите телефоны. "
     "Если живёте в зоне A — уезжайте заранее, мосты могут закрыть при ветре сильнее 40 миль в час.",
     [("National Hurricane Center", "https://www.nhc.noaa.gov/"), ("Tampa Bay Times", "https://www.tampabay.com/")]),
    (70, "florida", "laws", False, 8,
     "С 1 января меняются правила продления водительских прав",
     "FLHSMV переводит продление прав для водителей старше 80 лет на новую схему с проверкой зрения.",
     "Департамент безопасности дорожного движения Флориды (FLHSMV) сообщил об изменениях в порядке "
     "продления водительских удостоверений.\n\nКасается водителей старше 80 лет: при каждом продлении "
     "нужно будет пройти проверку зрения — в офисе или у своего врача.\n\nСрок действия прав не меняется. "
     "Подробности и список документов — на сайте FLHSMV.",
     [("Florida Politics", "https://floridapolitics.com/")]),
    (130, "miami", "housing", False, 8,
     "В Майами-Дейд стартует программа помощи с укреплением крыш",
     "Владельцы домов могут получить до $10 000 на защиту от ураганов — и скидку на страховку.",
     "Округ Майами-Дейд (Miami-Dade County) начинает приём заявок на программу My Safe Florida Home.\n\n"
     "Касается владельцев односемейных домов с основным проживанием. Сначала проводится бесплатная "
     "инспекция, затем можно получить грант на ставни, укрепление крыши или двери гаража.\n\n"
     "Такие работы обычно дают скидку на страховку жилья. Количество грантов ограничено.",
     [("WPLG Local 10", "https://www.local10.com/"), ("NBC 6 South Florida", "https://www.nbcmiami.com/")]),
    (190, "orlando", "roads", False, 7,
     "На I-4 в Орландо на выходных закроют съезды к центру",
     "Ночные закрытия с пятницы по воскресенье, с 22:00 до 6:00. Объезд — по Colonial Drive.",
     "Департамент транспорта Флориды (FDOT) предупредил о ночных закрытиях на межштатной трассе I-4 "
     "в районе центра Орландо.\n\nСъезды на Anderson Street и South Street будут закрыты с 22:00 до 6:00 "
     "в ночь на субботу и на воскресенье.\n\nЕсли едете ночью в аэропорт или из него — заложите "
     "лишние 15–20 минут.",
     [("ClickOrlando (News 6)", "https://www.clickorlando.com/")]),
    (260, "florida", "money", False, 7,
     "Налоговые каникулы на товары для подготовки к урагану: что входит",
     "Генераторы, фонари, батарейки и брезент можно купить без налога с продаж.",
     "Во Флориде действуют налоговые каникулы (sales tax holiday) на товары для подготовки к сезону ураганов.\n\n"
     "Без налога продаются фонари, батарейки, переносные радиоприёмники, брезент, а также генераторы "
     "в пределах установленного лимита цены.\n\nПолный список товаров и лимиты — на сайте Департамента "
     "доходов Флориды (Florida Department of Revenue).",
     [("Florida Phoenix", "https://floridaphoenix.com/")]),
    (330, "jacksonville", "safety", False, 7,
     "В части Джексонвилла действует предписание кипятить воду",
     "Предписание касается районов к востоку от реки Сент-Джонс. Отмена — после двух чистых анализов.",
     "Коммунальная компания JEA объявила предписание кипятить воду (boil water notice) для части клиентов "
     "после аварии на водопроводе.\n\nКасается районов к востоку от реки Сент-Джонс. Воду для питья и "
     "готовки нужно кипятить минимум минуту.\n\nОтменят предписание после двух подряд чистых анализов — "
     "обычно это занимает 48 часов.",
     [("News4JAX", "https://www.news4jax.com/"), ("First Coast News", "https://www.firstcoastnews.com/")]),
    (420, "miami", "events", False, 6,
     "В Санни-Айлс-Бич пройдёт бесплатный фестиваль на пляже",
     "Музыка, фудтраки и детская зона в субботу с 11:00 до 19:00. Парковка платная.",
     "Город Санни-Айлс-Бич (Sunny Isles Beach) проводит ежегодный пляжный фестиваль в парке Heritage Park.\n\n"
     "Вход свободный. Будут живая музыка, фудтраки и детская зона.\n\nПарковка у парка ограничена, "
     "город советует приезжать на бесплатном шаттле.",
     [("WSVN 7", "https://wsvn.com/")]),
    (500, "tampa", "education", False, 6,
     "Школы округа Хиллсборо переносят начало занятий в старших классах",
     "Со следующего учебного года уроки в старшей школе начнутся на 30 минут позже.",
     "Школьный совет округа Хиллсборо утвердил новое расписание.\n\nКасается учеников старших классов: "
     "занятия будут начинаться на 30 минут позже, расписание школьных автобусов тоже изменится.\n\n"
     "Новые маршруты автобусов опубликуют летом на сайте школьного округа.",
     [("FOX 13 Tampa Bay", "https://www.fox13news.com/")]),
    (620, "florida", "health", False, 6,
     "Минздрав Флориды предупреждает о комарах после дождей",
     "В нескольких округах ввели режим повышенного внимания из-за вирусов, которые переносят комары.",
     "Департамент здравоохранения Флориды (Florida Department of Health) объявил режим повышенного "
     "внимания в нескольких округах.\n\nСоветы простые: уберите стоячую воду во дворе, пользуйтесь "
     "репеллентом и закрывайте кожу на закате.\n\nПри температуре и сыпи после укусов обратитесь к врачу.",
     [("Florida Phoenix", "https://floridaphoenix.com/")]),
    (760, "orlando", "events", False, 5,
     "В Орландо открывается новая линия SunRail до аэропорта: даты пока нет",
     "Власти подтвердили проект, но срок запуска пока не назван.",
     "Власти Центральной Флориды подтвердили планы продлить пригородную линию SunRail до международного "
     "аэропорта Орландо.\n\nСрок запуска и цена билета пока не объявлены. Мы обновим заметку, когда "
     "появятся подробности.",
     [("WESH 2", "https://www.wesh.com/")]),
    (900, "miami", "incidents", False, 6,
     "Полиция Майами-Бич усиливает патрули на выходных",
     "По данным полиции, на набережной будет больше патрулей и временные ограничения парковки.",
     "Полиция Майами-Бич (Miami Beach Police) сообщила, что на выходных усилит патрулирование в районе "
     "Ocean Drive.\n\nПо данным полиции, часть парковок будет закрыта, а на въездах возможны проверки.\n\n"
     "Если едете на пляж — закладывайте больше времени и пользуйтесь общественным транспортом.",
     [("NBC 6 South Florida", "https://www.nbcmiami.com/")]),
    (1100, "florida", "housing", False, 7,
     "Ещё одна страховая компания получила разрешение работать во Флориде",
     "Регулятор одобрил выход новой компании на рынок страхования жилья.",
     "Управление страхового регулирования Флориды (Office of Insurance Regulation) одобрило выход "
     "новой компании на рынок страхования жилья.\n\nДля владельцев домов это означает чуть больше выбора "
     "при продлении полиса.\n\nСравнивайте предложения у нескольких агентов и проверяйте рейтинг компании.",
     [("Florida Politics", "https://floridapolitics.com/")]),
]


class Command(BaseCommand):
    help = "Создать демо-заметки для просмотра дизайна (только DJANGO_DEBUG=1)."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Удалить демо-данные")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo работает только при DJANGO_DEBUG=1")
        demo_tag, _ = Tag.objects.get_or_create(name="демо", defaults={"slug": "demo"})
        Article.objects.filter(tags=demo_tag).delete()
        WeatherAlert.objects.filter(external_id__startswith="demo-").delete()
        AdBanner.objects.filter(advertiser__startswith="Демо").delete()
        if opts["clear"]:
            demo_tag.delete()
            self.stdout.write("Демо-данные удалены")
            return

        now = timezone.now()
        for minutes, region, topic, urgent, score, title, teaser, body, sources in DEMO:
            article = Article.objects.create(
                title=title, teaser=teaser, body=body, is_urgent=urgent, score=score,
                region=Region.objects.get(slug=region), topic=Topic.objects.get(slug=topic),
                status=Article.Status.PUBLISHED, published_at=now - timedelta(minutes=minutes),
            )
            article.tags.add(demo_tag)
            for i, (name, url) in enumerate(sources):
                ArticleSource.objects.create(article=article, name=name, url=url, order=i)

        review = Article.objects.create(
            title="Суд в Орландо рассмотрит иск против управляющей компании",
            teaser="Демо-заметка в очереди «На проверку»: чувствительная тема.",
            body="Текст демо-заметки для проверки очереди модерации.",
            region=Region.objects.get(slug="orlando"), topic=Topic.objects.get(slug="incidents"),
            is_sensitive=True, score=6, status=Article.Status.REVIEW,
            review_reason="Чувствительная тема (криминал, частные лица, дети или обвинения)",
        )
        review.tags.add(demo_tag)

        WeatherAlert.objects.create(
            external_id="demo-1", event="Tropical Storm Warning", event_ru="Предупреждение о тропическом шторме",
            area="Hillsborough; Pinellas; Pasco; Manatee", severity="Severe",
            expires=now + timedelta(hours=30), url="https://www.weather.gov/",
        )
        WeatherAlert.objects.create(
            external_id="demo-2", event="Storm Surge Watch", event_ru="Угроза штормового нагона",
            area="Coastal Hillsborough; Coastal Pinellas; Coastal Sarasota", severity="Extreme",
            expires=now + timedelta(hours=40), url="https://www.weather.gov/",
        )
        WeatherAlert.objects.create(
            external_id="demo-3", event="Flood Watch", event_ru="Угроза наводнения",
            area="Polk; Osceola; Orange", severity="Moderate",
            expires=now + timedelta(hours=20), url="https://www.weather.gov/",
        )
        AdBanner.objects.create(
            advertiser="Демо: страховое агентство", slot=AdBanner.Slot.SIDEBAR,
            headline="Страховка дома и авто на русском языке. Бесплатный расчёт за 15 минут →",
            url="https://example.com/",
        )
        AdBanner.objects.create(
            advertiser="Демо: автосервис в Майами", slot=AdBanner.Slot.INFEED,
            headline="Ремонт и техосмотр, мастера говорят по-русски. Запись онлайн →", url="https://example.com/",
        )
        AdBanner.objects.create(
            advertiser="Демо: юридическая фирма", slot=AdBanner.Slot.TOP,
            headline="Иммиграционный юрист во Флориде — первая консультация бесплатно →", url="https://example.com/",
        )
        self.stdout.write(self.style.SUCCESS(f"Создано демо-заметок: {len(DEMO) + 1}"))
