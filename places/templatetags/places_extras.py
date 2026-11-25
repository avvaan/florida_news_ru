import re

from django import template
from django.conf import settings
from django.templatetags.static import static

from news.templatetags.news_extras import _jsonld, absolute, editorial_author, publisher

register = template.Library()


@register.filter
def place_image(item, number) -> str:
    """Базовый путь картинки статьи в static/ без расширения (1 — обложка)."""
    return item.image(int(number))


@register.filter
def place_credit(item, number) -> str:
    return item.credit(int(number))


@register.filter
def tel(phone: str) -> str:
    """«+1 (305) 242-7700» → «+13052427700» для ссылки tel:."""
    digits = re.sub(r"[^\d+]", "", phone or "")
    return digits if digits.startswith("+") else f"+1{digits}" if len(digits) == 10 else digits


@register.simple_tag
def destination_jsonld(item) -> str:
    url = absolute(item.get_absolute_url())
    published = item.published_at or item.created_at
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "headline": item.title[:110],
        "description": item.teaser,
        "datePublished": published.isoformat(),
        "dateModified": (item.revised_at or published).isoformat(),
        "inLanguage": item.lang,
        "author": editorial_author(),
        "publisher": publisher(),
        "citation": [s.url for s in item.sources.all()],
        "wordCount": item.word_count,
        "spatialCoverage": {"@type": "State", "name": "Florida", "addressCountry": "US"},
        "about": [
            {"@type": "TouristAttraction", "name": b.place["name"], "url": b.place["url"],
             "address": {"@type": "PostalAddress", "streetAddress": b.place["address"], "addressRegion": "FL",
                         "addressCountry": "US"}}
            for b in item.places
        ],
    }
    if item.region_name:
        data["articleSection"] = item.region_name
    if images := item.image_files:
        data["image"] = [f"{settings.SITE_URL}{static(path)}" for path in images]
    return _jsonld(data)


@register.simple_tag
def destinations_collection_jsonld(name, description, url, items, lang) -> str:
    return _jsonld({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": str(name),
        "description": str(description),
        "url": absolute(str(url)),
        "inLanguage": lang,
        "isPartOf": {"@id": f"{settings.SITE_URL}/#website"},
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "position": n, "url": absolute(d.get_absolute_url()), "name": d.title}
                for n, d in enumerate(items, start=1)
            ],
        },
    })
