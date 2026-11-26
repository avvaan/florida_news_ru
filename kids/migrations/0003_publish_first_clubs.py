"""Первые кружки каталога: публикуются по решению владельца (26.11.2026).

Данные — kids/data/from_directory_central_fl.csv (3 записи из справочника /links/deti/) и
kids/data/research_2026_11_central_fl.csv (ресёрч 26.11.2026 по поисковым выдержкам: сами сайты из облачной
сессии открыть не удалось). У записей ресёрча дата проверки остаётся пустой — на карточке «Ещё не проверено
редакцией». Bilingual Bridges остаётся черновиком: нет города и не известен формат занятий.

Повторный запуск ничего не дублирует: запись ищется по сайту (без протокола, www и слеша) или по названию.
"""

import csv
from datetime import date
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data"
FILES = [("from_directory_central_fl.csv", True), ("research_2026_11_central_fl.csv", False)]
KEEP_DRAFT = {"Bilingual Bridges"}
NOTE = "26.11.2026: опубликовано по решению владельца без ручной сверки источников."

LANGS = {"русский": "lang_ru", "украинский": "lang_uk", "английский": "lang_en", "двуязычный": "lang_bilingual"}
FORMATS = {"очно": "offline", "онлайн": "online", "оба": "both"}
ESA = {"принимает": "yes", "не принимает": "no"}
PROGRAMS = {"PEP": "esa_pep", "FES-UA": "esa_fes_ua", "FES-EO": "esa_fes_eo", "FTC": "esa_ftc"}
TEXT = ["description", "address", "schedule_text", "price_text", "esa_note", "phone", "email", "website", "instagram",
        "facebook", "telegram", "whatsapp", "source_url"]


def norm_url(url: str) -> str:
    return url.strip().lower().split("://", 1)[-1].removeprefix("www.").split("?", 1)[0].rstrip("/")


def split(value: str) -> list[str]:
    return [p.strip() for p in value.split(";") if p.strip()]


def publish(apps, schema_editor):
    from core.text import make_slug

    City = apps.get_model("kids", "City")
    Club = apps.get_model("kids", "Club")
    cities = {c.name_en.lower(): c for c in City.objects.all()}

    for filename, keep_verified in FILES:
        with open(DATA / filename, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            name = row["name"].strip()
            city = cities.get(row["city"].strip().lower()) if row["city"].strip() else None
            values = {name_: row[name_].strip() for name_ in TEXT}
            values.update(
                name=name, category=row["category"].strip(), city=city,
                format=FORMATS.get(row["format"].strip(), "offline"),
                esa_status=ESA.get(row["esa"].strip(), "unknown"),
                age_min=int(row["age_min"]) if row["age_min"].strip() else None,
                age_max=int(row["age_max"]) if row["age_max"].strip() else None,
                last_verified_at=(date.fromisoformat(row["last_verified_at"])
                                  if keep_verified and row["last_verified_at"].strip() else None),
                status="draft" if name in KEEP_DRAFT or (city is None and row["format"].strip() != "онлайн")
                else "published",
                origin="import",
                editor_note=f"{row['editor_note'].strip()}\n{NOTE}".strip(),
            )
            langs = set(split(row["teaching_language"]))
            values.update({field: label in langs for label, field in LANGS.items()})
            programs = set(split(row["esa_programs"]))
            values.update({field: code in programs for code, field in PROGRAMS.items()})

            club = None
            if values["website"]:
                club = next((c for c in Club.objects.exclude(website="")
                             if norm_url(c.website) == norm_url(values["website"])), None)
            club = club or Club.objects.filter(name__iexact=name).first()
            if club is None:
                base = make_slug(f"{name} {city.name_en if city else ''}", 100) or "kruzhok"
                slug, n = base, 2
                while Club.objects.filter(slug=slug).exists():
                    slug, n = f"{base}-{n}", n + 1
                Club.objects.create(slug=slug, **values)
            else:
                for key, value in values.items():
                    setattr(club, key, value)
                club.save()


class Migration(migrations.Migration):
    dependencies = [("kids", "0002_seed_cities_privacy")]

    operations = [migrations.RunPython(publish, migrations.RunPython.noop)]
