"""Заголовки, описания и разметка Schema.org для раздела «Детям».

Шаблоны:
  «Кружки по шахматам для детей в Орландо — на русском языке»   /deti/shakhmaty/orlando/
  «Детские кружки и секции в Лонгвуде — на русском языке»        /deti/longwood/
  «Кружки по шахматам для детей в Центральной Флориде — …»       /deti/shakhmaty/
"""

from __future__ import annotations

import json

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _, ngettext

from .models import CATEGORY_TITLES, Category, Club

# Страница «Как оплатить кружок из стипендии» опубликована (решение владельца 26.11.2026): открыта для всех,
# в sitemap и в ссылках раздела. False — снова видна только редакции и закрыта от поиска.
ESA_PAGE_VERIFIED = True


def where(f) -> str:
    return f.city.loc("name_locative") if f.city else _("в Центральной Флориде")


def h1(f) -> str:
    if f.category:
        return _("%(what)s для детей %(where)s") % {"what": CATEGORY_TITLES[f.category], "where": where(f)}
    return _("Детские кружки и секции %(where)s") % {"where": where(f)}


def title(f) -> str:
    return _("%(h1)s — на русском языке") % {"h1": h1(f)}


def description(f, count: int) -> str:
    what = (CATEGORY_TITLES[f.category] if f.category else _("Детские кружки и секции"))
    if count:
        lead = ngettext("%(n)s место в каталоге.", "%(n)s мест в каталоге.", count) % {"n": count}
        return (f"{what} {where(f)}: {lead} " +
                _("Язык занятий, возраст, формат, расписание и стоимость, отметка об оплате из стипендий PEP и FES."))
    return (f"{what} {where(f)}: " +
            _("каталог кружков с занятиями на русском и украинском языках. Добавьте кружок, который знаете."))


def list_url(category: str = "", city=None) -> str:
    if category and city:
        return reverse("kids:section-city", args=[category, city.slug])
    if category or city:
        return reverse("kids:section", args=[category or city.slug])
    return reverse("kids:list")


def breadcrumbs(f) -> list[tuple[str, str]]:
    crumbs = [(_("Главная"), reverse("news:home")), (_("Детям"), reverse("kids:list"))]
    if f.category:
        crumbs.append((str(Category(f.category).label), list_url(f.category)))
    if f.city:
        crumbs.append((f.city.loc("name"), list_url(f.category, f.city)))
    return crumbs


def absolute(path: str) -> str:
    return path if path.startswith("http") else f"{settings.SITE_URL}{path}"


def club_schema(club: Club, *, full: bool = False) -> dict:
    """EducationalOrganization + LocalBusiness (у очных занятий с городом). Без оценок и отзывов."""
    types = ["EducationalOrganization", "LocalBusiness"] if club.has_offline and club.city_id else \
        ["EducationalOrganization"]
    data = {"@type": types, "name": club.name, "url": absolute(club.get_absolute_url())}
    if text := club.loc("description"):
        data["description"] = text
    if club.phone:
        data["telephone"] = club.phone
    if club.email and full:
        data["email"] = club.email
    if club.has_offline and club.city_id:
        address = {"@type": "PostalAddress", "addressLocality": club.city.name_en, "addressRegion": "FL",
                   "addressCountry": "US"}
        if club.address:
            address["streetAddress"] = club.address
        data["address"] = address
        if club.point_is_exact:
            data["geo"] = {"@type": "GeoCoordinates", "latitude": club.lat, "longitude": club.lng}
    same_as = [url for url in (club.website, club.instagram, club.facebook) if url]
    if same_as:
        data["sameAs"] = same_as
    if languages := [code for code, field in (("ru", "lang_ru"), ("uk", "lang_uk"), ("en", "lang_en"))
                     if getattr(club, field)]:
        data["knowsLanguage"] = languages
    if full:
        photos = club.public_photos()
        if photos:
            data["image"] = [p.media.url for p in photos]
    return data


def club_jsonld(club: Club) -> dict:
    return {"@context": "https://schema.org", **club_schema(club, full=True)}


def itemlist_jsonld(name: str, clubs) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "numberOfItems": len(clubs),
        "itemListElement": [{"@type": "ListItem", "position": n, "url": absolute(club.get_absolute_url()),
                             "item": club_schema(club)} for n, club in enumerate(clubs, start=1)],
    }


def breadcrumbs_jsonld(crumbs: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": n, "name": str(name), "item": absolute(url)}
                            for n, (name, url) in enumerate(crumbs, start=1)],
    }


def dumps(data: dict) -> str:
    """JSON для <script type="application/ld+json">: «</» экранируем, чтобы текст не закрыл тег."""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
