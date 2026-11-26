"""Фильтры каталога и правило индексации.

Направление и город — часть адреса (/deti/shakhmaty/orlando/), остальные фильтры — в строке запроса
(?age=6&lang=uk&esa=any&format=online). Страница открыта для поиска, только если в ней не меньше
MIN_INDEXABLE опубликованных кружков и нет фильтров из строки запроса: тонкие и бесконечные вариации
страниц тянут сайт вниз.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from .models import ESA_PROGRAMS, LANGUAGES, MAX_AGE, Category, City, Club, Esa, Format

MIN_INDEXABLE = 3

LANG_FIELDS = {code: name for code, name, _label in LANGUAGES}
ESA_FIELDS = {code: name for code, name, _label in ESA_PROGRAMS}
FORMAT_CHOICES = ("offline", "online")


@dataclass
class Filters:
    category: str = ""
    city: City | None = None
    age: int | None = None
    lang: str = ""
    esa: str = ""  # "any" — принимает хоть какую-то стипендию; "pep", "fes-ua"… — конкретную программу
    format: str = ""
    errors: list = field(default_factory=list)

    @property
    def extra(self) -> dict:
        """Фильтры из строки запроса (без направления и города)."""
        out = {}
        if self.age is not None:
            out["age"] = str(self.age)
        if self.lang:
            out["lang"] = self.lang
        if self.esa:
            out["esa"] = self.esa
        if self.format:
            out["format"] = self.format
        return out

    @property
    def has_extra(self) -> bool:
        return bool(self.extra)

    @property
    def is_empty(self) -> bool:
        return not (self.category or self.city or self.has_extra)


def parse_extra(params, filters: Filters | None = None) -> Filters:
    """Разбирает фильтры из строки запроса. Неверные значения молча отбрасываются."""
    f = filters or Filters()
    age = (params.get("age") or "").strip()
    if age.isdigit() and 0 <= int(age) <= MAX_AGE:
        f.age = int(age)
    lang = params.get("lang") or ""
    if lang in LANG_FIELDS:
        f.lang = lang
    esa = params.get("esa") or ""
    if esa == "any" or esa in ESA_FIELDS:
        f.esa = esa
    fmt = params.get("format") or ""
    if fmt in FORMAT_CHOICES:
        f.format = fmt
    return f


def resolve_path(first: str | None, second: str | None) -> Filters | None:
    """/deti/<first>/<second>/ → направление и город. None — такой страницы нет (404)."""
    f = Filters()
    if first is None:
        return f
    if first in Category.values:
        f.category = first
        if second is not None:
            f.city = City.objects.active().filter(slug=second).first()
            if f.city is None:
                return None
        return f
    if second is not None:  # город всегда второй: /deti/<направление>/<город>/
        return None
    f.city = City.objects.active().filter(slug=first).first()
    return f if f.city else None


def apply(queryset: QuerySet, f: Filters) -> QuerySet:
    qs = queryset
    if f.category:
        qs = qs.filter(category=f.category)
    if f.city:
        qs = qs.filter(city=f.city)
    if f.age is not None:
        # Неуказанная граница не ограничивает; кружки без возраста идут в конце (см. order).
        qs = qs.filter((Q(age_min__isnull=True) | Q(age_min__lte=f.age)) &
                       (Q(age_max__isnull=True) | Q(age_max__gte=f.age)))
    if f.lang:
        qs = qs.filter(**{LANG_FIELDS[f.lang]: True})
    if f.esa:
        qs = qs.filter(esa_status=Esa.YES)
        if f.esa != "any":
            qs = qs.filter(**{ESA_FIELDS[f.esa]: True})
    if f.format == "online":
        qs = qs.filter(format__in=[Format.ONLINE, Format.BOTH])
    elif f.format == "offline":
        qs = qs.filter(format__in=[Format.OFFLINE, Format.BOTH])
    return qs


def order(queryset: QuerySet, f: Filters) -> QuerySet:
    qs = queryset.ordered()
    if f.age is not None:
        known = Case(When(age_min__isnull=True, age_max__isnull=True, then=Value(1)), default=Value(0),
                     output_field=IntegerField())
        qs = qs.annotate(_age_unknown=known).order_by("_age_unknown", *qs.query.order_by)
    return qs


def find(f: Filters) -> QuerySet:
    return order(apply(Club.objects.published().select_related("city"), f), f)


def is_indexable(count: int, f: Filters) -> bool:
    """Правило для тонких страниц: ≥ MIN_INDEXABLE опубликованных кружков и никаких фильтров в строке запроса."""
    return count >= MIN_INDEXABLE and not f.has_extra
