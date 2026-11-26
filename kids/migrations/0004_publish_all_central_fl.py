"""Все найденные детские кружки Центральной Флориды (на любом языке) — по решению владельца, 26.11.2026.

Данные — kids/data/research_2026_11_all_central_fl.csv: поиск 26.11.2026 по поисковым выдержкам (сами сайты из
облачной сессии открыть не удалось). Описания — по-русски, по фактам из выдержек; язык занятий, возраст,
цены и расписание — только если они были в выдержке, иначе «не указано». Дата проверки пустая: на карточке
«Ещё не проверено редакцией».

Статус берётся из колонки status: черновиками остались записи, о которых источник говорит «закрыто»,
«скоро откроется» или «статус уточнить», и записи с ненадёжным источником (см. editor_note).
Кружки, которые уже есть в каталоге (тот же сайт или то же название в том же городе), не трогаем.
"""

import csv
from pathlib import Path

from django.db import migrations

FILE = Path(__file__).resolve().parent.parent / "data" / "research_2026_11_all_central_fl.csv"
NOTE = "26.11.2026: добавлено по решению владельца без ручной сверки источников."

LANGS = {"русский": "lang_ru", "украинский": "lang_uk", "английский": "lang_en", "двуязычный": "lang_bilingual"}
FORMATS = {"очно": "offline", "онлайн": "online", "оба": "both"}
ESA = {"принимает": "yes", "не принимает": "no"}
PROGRAMS = {"PEP": "esa_pep", "FES-UA": "esa_fes_ua", "FES-EO": "esa_fes_eo", "FTC": "esa_ftc"}
TEXT = ["description", "address", "schedule_text", "price_text", "esa_note", "phone", "email", "website", "instagram",
        "facebook", "telegram", "whatsapp", "source_url"]
CATEGORIES = {"matematika", "shakhmaty", "tantsy", "gimnastika", "plavanie", "muzyka", "risovanie", "yazyki",
              "robototekhnika", "edinoborstva", "komandnyy-sport", "podgotovka-k-shkole", "drugoe"}


def norm_url(url: str) -> str:
    return url.strip().lower().split("://", 1)[-1].removeprefix("www.").split("?", 1)[0].rstrip("/")


def split(value: str) -> list[str]:
    return [p.strip() for p in value.replace(",", ";").split(";") if p.strip()]


def age(value: str):
    value = value.strip()
    return int(value) if value.isdigit() and int(value) <= 18 else None


def publish(apps, schema_editor):
    from core.text import make_slug

    City = apps.get_model("kids", "City")
    Club = apps.get_model("kids", "Club")
    cities = {c.name_en.lower(): c for c in City.objects.all()}
    known_sites = {(norm_url(c.website), c.city_id) for c in Club.objects.exclude(website="")}
    known_names = {(c.name.lower(), c.city_id) for c in Club.objects.all()}

    with open(FILE, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row = {k: (v or "").strip() for k, v in row.items()}
        city = cities.get(row["city"].lower()) if row["city"] else None
        fmt = FORMATS.get(row["format"], "offline")
        if row["category"] not in CATEGORIES or not row["name"] or not row["description"]:
            continue
        if city is None and fmt != "online":
            continue
        city_id = city.pk if city else None
        if (row["name"].lower(), city_id) in known_names or (
                row["website"] and (norm_url(row["website"]), city_id) in known_sites):
            continue
        values = {name: row[name] for name in TEXT}
        a_min, a_max = age(row["age_min"]), age(row["age_max"])
        if a_min is not None and a_max is not None and a_min > a_max:
            a_min = a_max = None
        langs, programs = set(split(row["teaching_language"])), {p.upper() for p in split(row["esa_programs"])}
        values.update(
            name=row["name"], category=row["category"], city=city, format=fmt,
            esa_status=ESA.get(row["esa"], "unknown"), age_min=a_min, age_max=a_max,
            status="published" if row["status"] == "published" else "draft", origin="import",
            editor_note=f"{row['editor_note']}\n{NOTE}".strip(),
            **{field: label in langs for label, field in LANGS.items()},
            **{field: code in programs for code, field in PROGRAMS.items()},
        )
        base = make_slug(f"{row['name']} {city.name_en if city else ''}", 100) or "kruzhok"
        slug, n = base, 2
        while Club.objects.filter(slug=slug).exists():
            slug, n = f"{base}-{n}", n + 1
        Club.objects.create(slug=slug, **values)
        known_names.add((row["name"].lower(), city_id))
        if row["website"]:
            known_sites.add((norm_url(row["website"]), city_id))


class Migration(migrations.Migration):
    dependencies = [("kids", "0003_publish_first_clubs")]

    operations = [migrations.RunPython(publish, migrations.RunPython.noop)]
