"""Источники раздела «Бизнес: акции и сделки».

Деловые издания Флориды через ленты Bing News с поиском по сайту — так же, как пресс-релизы IRS
(у бизнес-журналов нет открытого RSS по регионам). Ссылки-переходники Bing сборщик раскрывает в
прямые адреса изданий. Адреса не проверены из среды разработки, поэтому, как и другие кандидаты,
создаются выключенными: `python manage.py check_sources --activate` включит рабочие.
"""

from urllib.parse import quote_plus

from django.db import migrations

BING = "https://www.bing.com/news/search?q={}&format=rss"

# name, homepage, поисковый запрос, регион, вес доверия, заметка
SOURCES = [
    ("South Florida Business Journal", "https://www.bizjournals.com/southflorida/", "site:bizjournals.com/southflorida",
     "miami", 7, "Деловые новости Южной Флориды: сделки, компании, недвижимость. Часть статей платная"),
    ("Tampa Bay Business Journal", "https://www.bizjournals.com/tampabay/", "site:bizjournals.com/tampabay",
     "tampa", 7, "Деловые новости Тампа-Бэй. Часть статей платная"),
    ("Orlando Business Journal", "https://www.bizjournals.com/orlando/", "site:bizjournals.com/orlando",
     "orlando", 7, "Деловые новости Центральной Флориды. Часть статей платная"),
    ("Jacksonville Business Journal", "https://www.bizjournals.com/jacksonville/", "site:bizjournals.com/jacksonville",
     "jacksonville", 7, "Деловые новости Северо-Восточной Флориды. Часть статей платная"),
    ("The Real Deal Miami", "https://therealdeal.com/miami/", "site:therealdeal.com/miami",
     "miami", 7, "Сделки с недвижимостью Южной Флориды"),
    ("Florida Trend", "https://www.floridatrend.com/", "site:floridatrend.com",
     "florida", 7, "Деловой журнал штата"),
    ("Акции компаний Флориды (Reuters)", "https://www.reuters.com/business/",
     '(NextEra OR Lennar OR "Carnival" OR "Royal Caribbean" OR "Darden" OR "Raymond James" OR Jabil OR Chewy '
     'OR AutoNation OR "Norwegian Cruise" OR "Fidelity National" OR "Roper Technologies") site:reuters.com',
     "florida", 8, "Отчёты и движения акций крупных компаний со штаб-квартирой во Флориде"),
]


def add_business_sources(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    Region = apps.get_model("news", "Region")
    for name, homepage, query, region, trust, notes in SOURCES:
        Source.objects.get_or_create(url=BING.format(quote_plus(query)), defaults={
            "name": name, "homepage": homepage, "kind": "rss", "source_type": "media",
            "region": Region.objects.filter(slug=region).first(), "trust_weight": trust,
            "is_active": False, "is_verified": False,
            "notes": f"Бизнес (через Bing News). {notes}. Кандидат: запустите check_sources --activate",
        })


class Migration(migrations.Migration):

    dependencies = [
        ("sources", "0003_irs_newsroom"),
    ]

    operations = [migrations.RunPython(add_business_sources, migrations.RunPython.noop)]
