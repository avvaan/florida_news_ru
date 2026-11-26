"""Импорт кружков из CSV. Колонки — поля модели (см. COLUMNS), несколько значений — через «;».

Повторный запуск того же файла ничего не дублирует: запись ищется по slug, а если его нет — по сайту
(без www, протокола и слеша в конце). Пустая ячейка не стирает уже заполненное поле. Новые записи —
черновики, если в колонке status не сказано иное. Никакого скачивания с сайтов: только то, что в файле.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator
from django.db import transaction

from core.text import make_slug

from .models import ESA_PROGRAMS, LANGUAGES, MAX_AGE, Category, City, Club, Esa, Format

TEXT = ["name", "description", "address", "schedule_text", "price_text", "esa_note", "phone", "telegram", "whatsapp",
        "editor_note"]
URLS = ["website", "instagram", "facebook", "source_url"]
COLUMNS = ["name", "slug", "description", "category", "age_min", "age_max", "teaching_language", "city", "address",
           "lat", "lng", "format", "schedule_text", "price_text", "esa", "esa_programs", "esa_note", "phone", "email",
           "website", "instagram", "facebook", "telegram", "whatsapp", "source_url", "last_verified_at", "status",
           "is_featured", "editor_note"]

LANGUAGE_ALIASES = {
    "ru": "ru", "русский": "ru", "рус": "ru", "russian": "ru",
    "uk": "uk", "ua": "uk", "украинский": "uk", "укр": "uk", "ukrainian": "uk",
    "en": "en", "английский": "en", "англ": "en", "english": "en",
    "bilingual": "bilingual", "двуязычный": "bilingual", "двуязычно": "bilingual",
}
FORMAT_ALIASES = {"offline": Format.OFFLINE, "очно": Format.OFFLINE, "online": Format.ONLINE, "онлайн": Format.ONLINE,
                  "both": Format.BOTH, "оба": Format.BOTH, "очно и онлайн": Format.BOTH}
ESA_ALIASES = {"yes": Esa.YES, "принимает": Esa.YES, "да": Esa.YES, "no": Esa.NO, "не принимает": Esa.NO,
               "нет": Esa.NO, "unknown": Esa.UNKNOWN, "не указано": Esa.UNKNOWN}
STATUS_ALIASES = {"draft": Club.Status.DRAFT, "черновик": Club.Status.DRAFT, "published": Club.Status.PUBLISHED,
                  "опубликован": Club.Status.PUBLISHED, "archived": Club.Status.ARCHIVED,
                  "в архиве": Club.Status.ARCHIVED}
BOOL_TRUE = {"1", "true", "yes", "да"}


class RowError(Exception):
    pass


@dataclass
class Report:
    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    unchanged: list = field(default_factory=list)
    errors: list = field(default_factory=list)  # (номер строки, текст)

    def summary(self) -> str:
        return (f"создано: {len(self.created)}, обновлено: {len(self.updated)}, без изменений: {len(self.unchanged)}, "
                f"ошибок: {len(self.errors)}")


def normalize_url(url: str) -> str:
    value = url.strip().lower().split("://", 1)[-1].removeprefix("www.").split("#", 1)[0].split("?", 1)[0]
    return value.rstrip("/")


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.replace(",", ";").split(";") if part.strip()]


def _choice(value: str, aliases: dict, what: str):
    key = value.strip().lower()
    if key not in aliases:
        raise RowError(f"{what}: непонятное значение «{value}»")
    return aliases[key]


def _category(value: str) -> str:
    key = value.strip().lower()
    for code, label in Category.choices:
        if key in (code, str(label).lower()):
            return code
    raise RowError(f"category: нет направления «{value}»")


def _city(value: str) -> City:
    key = value.strip().lower()
    for city in City.objects.all():
        if key in (city.slug, city.name.lower(), city.name_en.lower()):
            return city
    raise RowError(f"city: город «{value}» не найден — добавьте его в админке (Детям → Города)")


def _age(value: str, column: str) -> int:
    if not value.strip().isdigit() or int(value) > MAX_AGE:
        raise RowError(f"{column}: возраст должен быть числом от 0 до {MAX_AGE}")
    return int(value)


def _float(value: str, column: str) -> float:
    try:
        return float(value.replace(",", "."))
    except ValueError as exc:
        raise RowError(f"{column}: не число «{value}»") from exc


def _date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise RowError(f"last_verified_at: дата «{value}» — нужен формат ГГГГ-ММ-ДД или ДД.ММ.ГГГГ")


def parse_row(row: dict) -> dict:
    """Строка CSV → значения полей модели. Пустые ячейки в результат не попадают."""
    if None in row:  # в строке больше ячеек, чем колонок (лишняя запятая без кавычек)
        raise RowError("в строке больше ячеек, чем колонок в заголовке — проверьте кавычки")
    row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
    values: dict = {}
    for name in TEXT:
        if row.get(name):
            values[name] = row[name]
    for name in URLS:
        if url := row.get(name):
            try:
                URLValidator()(url)
            except ValidationError as exc:
                raise RowError(f"{name}: неверная ссылка «{url}»") from exc
            values[name] = url
    if email := row.get("email"):
        try:
            EmailValidator()(email)
        except ValidationError as exc:
            raise RowError(f"email: неверный адрес «{email}»") from exc
        values["email"] = email
    if row.get("slug"):
        values["slug"] = make_slug(row["slug"], 120)
    if row.get("category"):
        values["category"] = _category(row["category"])
    for column in ("age_min", "age_max"):
        if row.get(column):
            values[column] = _age(row[column], column)
    if "age_min" in values and "age_max" in values and values["age_min"] > values["age_max"]:
        raise RowError("age_max меньше age_min")
    if row.get("teaching_language"):
        codes = {_choice(v, LANGUAGE_ALIASES, "teaching_language") for v in _split(row["teaching_language"])}
        for code, name, _label in LANGUAGES:
            values[name] = code in codes
    if row.get("city"):
        values["city"] = _city(row["city"])
    for column in ("lat", "lng"):
        if row.get(column):
            values[column] = _float(row[column], column)
    if row.get("format"):
        values["format"] = _choice(row["format"], FORMAT_ALIASES, "format")
    if row.get("esa"):
        values["esa_status"] = _choice(row["esa"], ESA_ALIASES, "esa")
    if row.get("esa_programs"):
        codes = {p.lower() for p in _split(row["esa_programs"])}
        known = {code for code, _name, _label in ESA_PROGRAMS}
        if unknown := codes - known:
            raise RowError(f"esa_programs: неизвестные программы {', '.join(sorted(unknown))} (PEP, FES-UA, FES-EO, FTC)")
        for code, name, _label in ESA_PROGRAMS:
            values[name] = code in codes
    if row.get("last_verified_at"):
        values["last_verified_at"] = _date(row["last_verified_at"])
    if row.get("status"):
        values["status"] = _choice(row["status"], STATUS_ALIASES, "status")
    if row.get("is_featured"):
        values["is_featured"] = row["is_featured"].lower() in BOOL_TRUE
    return values


def find_existing(values: dict) -> Club | None:
    if slug := values.get("slug"):
        if club := Club.objects.filter(slug=slug).first():
            return club
    if website := values.get("website"):
        target = normalize_url(website)
        for club in Club.objects.exclude(website=""):
            if normalize_url(club.website) == target:
                return club
    if (name := values.get("name")) and not values.get("slug") and not values.get("website"):
        # без slug и сайта — то же название в том же городе (или тоже без города)
        return Club.objects.filter(name__iexact=name, city=values.get("city")).first()
    return None


def import_rows(rows, *, dry_run: bool = False) -> Report:
    report = Report()
    with transaction.atomic():
        for line, row in enumerate(rows, start=2):  # строка 1 — заголовки
            if not any(str(v or "").strip() for v in row.values()):
                continue
            try:
                values = parse_row(row)
                club = find_existing(values)
                if club is None:
                    if not values.get("name") or not values.get("category"):
                        raise RowError("для новой записи нужны name и category")
                    values.setdefault("status", Club.Status.DRAFT)
                    club = Club(origin=Club.Origin.IMPORT, **values)
                    _validate(club)
                    club.save()
                    report.created.append(club)
                    continue
                if "website" in values and normalize_url(values["website"]) == normalize_url(club.website):
                    values.pop("website")  # тот же сайт в другом написании (http/www/слеш) — не трогаем
                changed = {name: value for name, value in values.items() if getattr(club, name) != value}
                if not changed:
                    report.unchanged.append(club)
                    continue
                for name, value in changed.items():
                    setattr(club, name, value)
                _validate(club)
                club.save()
                report.updated.append(club)
            except RowError as exc:
                report.errors.append((line, f"{(row.get('name') or '').strip() or '—'}: {exc}"))
        if dry_run:
            transaction.set_rollback(True)
    return report


def _validate(club: Club) -> None:
    try:
        club.clean()
    except ValidationError as exc:
        raise RowError("; ".join(m for msgs in exc.message_dict.values() for m in msgs)) from exc


def import_csv(source, *, dry_run: bool = False) -> Report:
    """source — путь к файлу или открытый текстовый файл. Разделитель «,» или «;» определяется сам."""
    if hasattr(source, "read"):
        text = source.read()
    else:
        with open(source, encoding="utf-8-sig", newline="") as fh:
            text = fh.read()
    text = text.lstrip("﻿")
    header = text.split("\n", 1)[0]
    delimiter = ";" if header.count(";") > header.count(",") else ","  # Excel в русской локали сохраняет с «;»
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    unknown = set(reader.fieldnames or []) - set(COLUMNS)
    if unknown:
        raise ValueError(f"Неизвестные колонки: {', '.join(sorted(unknown))}. Допустимые: {', '.join(COLUMNS)}")
    return import_rows(reader, dry_run=dry_run)
