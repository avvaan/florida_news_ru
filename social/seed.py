"""Стартовые запросы для Perplexity и Grok. Править — в админке, «Источники сигналов»."""

TOPICS = "погода и ураганы, законы и правила, происшествия, цены, школы, дороги"

QUERIES = [
    ("Майами и Южная Флорида", "miami",
     f"Главные новости и обсуждения за последние 12 часов в Майами и Южной Флориде "
     f"(Майами-Дейд, Бровард, Палм-Бич): {TOPICS}."),
    ("Орландо", "orlando", f"Главные новости и обсуждения за последние 12 часов в Орландо и Центральной Флориде: {TOPICS}."),
    ("Тампа", "tampa",
     f"Главные новости и обсуждения за последние 12 часов в районе Тампа-Бэй "
     f"(Тампа, Сент-Питерсберг, Клируотер): {TOPICS}."),
    ("Джексонвилл", "jacksonville",
     f"Главные новости и обсуждения за последние 12 часов в Джексонвилле и Северо-Восточной Флориде: {TOPICS}."),
    ("Весь штат", "florida",
     "Главные новости и обсуждения во Флориде за последние 12 часов: решения губернатора и властей штата, "
     "новые законы, погода и ураганы, крупные происшествия."),
]


def seed_signal_sources(apps, schema_editor):
    SignalSource = apps.get_model("social", "SignalSource")
    Region = apps.get_model("news", "Region")
    for kind in ("perplexity", "grok"):
        for name, region, query in QUERIES:
            SignalSource.objects.get_or_create(kind=kind, name=name, defaults={
                "query": query, "region": Region.objects.filter(slug=region).first(), "is_active": True,
            })
