import json

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from core.seed import SITE_OWNER

register = template.Library()


@register.filter
def absolute(path: str) -> str:
    if path.startswith("http"):
        return path
    return f"{settings.SITE_URL}{path}"


@register.simple_tag
def cover(article, size: str = "") -> str:
    """URL обложки: size="" — 1200px webp, "640" — 640px webp, "jpg" — 1200px jpeg."""
    base = article.cover if hasattr(article, "cover") else str(article)
    if size == "640":
        return static(f"{base}-640.webp")
    if size == "jpg":
        return static(f"{base}.jpg")
    return static(f"{base}.webp")


@register.filter
def guide_image(guide, number) -> str:
    """Базовый путь иллюстрации гайда в static/ без расширения (1 — обложка, 2, 3 … — в тексте)."""
    return guide.image(int(number))


@register.filter
def plural_ru(n, forms: str) -> str:
    """{{ n|plural_ru:"минута,минуты,минут" }}"""
    one, few, many = forms.split(",")
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@register.filter
def reading_minutes(article) -> int:
    return max(1, round(article.word_count / 180))


@register.filter
def ago(value) -> str:
    """«12 минут назад», «3 часа назад», иначе дата."""
    if not value:
        return ""
    delta = timezone.now() - value
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "только что"
    if minutes < 60:
        return f"{minutes} {plural_ru(minutes, 'минуту,минуты,минут')} назад"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} {plural_ru(hours, 'час,часа,часов')} назад"
    local = timezone.localtime(value)
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
    return f"{local.day} {months[local.month - 1]}, {local:%H:%M}"


def _jsonld(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


def publisher() -> dict:
    """Издание и его издатель — для NewsArticle, Article и страницы «О проекте»."""
    return {
        "@type": "NewsMediaOrganization",
        "@id": f"{settings.SITE_URL}/#organization",
        "name": settings.SITE_NAME,
        "url": f"{settings.SITE_URL}/",
        "logo": {"@type": "ImageObject", "url": f"{settings.SITE_URL}{static('img/logo-512.png')}"},
        "publishingPrinciples": f"{settings.SITE_URL}{reverse('core-about')}",
        "correctionsPolicy": f"{settings.SITE_URL}{reverse('core-corrections')}",
        "parentOrganization": {
            "@type": "Organization", "name": SITE_OWNER,
            "address": {"@type": "PostalAddress", "addressRegion": "FL", "addressCountry": "US"},
        },
    }


def editorial_author() -> dict:
    return {"@type": "Organization", "name": f"Редакция {settings.SITE_NAME}",
            "url": f"{settings.SITE_URL}{reverse('core-about')}"}


@register.simple_tag
def organization_jsonld() -> str:
    return _jsonld({"@context": "https://schema.org", **publisher()})


@register.simple_tag
def article_jsonld(article) -> str:
    url = f"{settings.SITE_URL}{article.get_absolute_url()}"
    published = article.published_at or article.created_at
    data = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "headline": article.title[:110],
        "description": article.teaser,
        "image": [f"{settings.SITE_URL}{static(article.cover + '.jpg')}"],
        "datePublished": published.isoformat(),
        "dateModified": (article.revised_at or published).isoformat(),
        "inLanguage": "ru",
        "author": editorial_author(),
        "publisher": publisher(),
        "isBasedOn": [s.url for s in article.sources.all()],
        "keywords": [t.name for t in article.tags.all()],
    }
    if article.topic:
        data["articleSection"] = article.topic.name
    if article.region:
        data["contentLocation"] = {"@type": "Place", "name": f"{article.region.name}, Florida"}
    return _jsonld(data)


@register.simple_tag
def guide_jsonld(guide) -> str:
    url = f"{settings.SITE_URL}{guide.get_absolute_url()}"
    published = guide.published_at or guide.created_at
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "headline": guide.title[:110],
        "description": guide.teaser,
        "datePublished": published.isoformat(),
        "dateModified": (guide.revised_at or published).isoformat(),
        "inLanguage": "ru",
        "author": editorial_author(),
        "publisher": publisher(),
        "citation": [s.url for s in guide.sources.all()],
        "wordCount": guide.word_count,
        "about": [t.name for t in guide.topics.all()],
        "spatialCoverage": {"@type": "State", "name": "Florida", "addressCountry": "US"},
    }
    if guide.section:
        data["articleSection"] = guide.get_section_display()
    if images := guide.image_paths:
        data["image"] = [f"{settings.SITE_URL}{static(path + '.jpg')}" for path in images]
    return _jsonld(data)


@register.simple_tag
def guide_faq_jsonld(guide) -> str:
    """FAQPage из раздела «Вопросы и ответы» гайда; пусто, если вопросов нет."""
    if not (faq := guide.faq):
        return ""
    return _jsonld({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq
        ],
    })


@register.simple_tag
def breadcrumbs_jsonld(*pairs) -> str:
    """{% breadcrumbs_jsonld "Главная" "/" "Гайды" "/guides/" guide.title guide.get_absolute_url %}"""
    names, urls = pairs[0::2], pairs[1::2]
    return _jsonld({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": n, "name": str(name), "item": absolute(str(url))}
            for n, (name, url) in enumerate(zip(names, urls), start=1)
        ],
    })


@register.simple_tag
def website_jsonld() -> str:
    return _jsonld({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": f"{settings.SITE_URL}/#website",
        "name": settings.SITE_NAME,
        "alternateName": "Флорида по-русски",
        "url": f"{settings.SITE_URL}/",
        "inLanguage": "ru",
        "publisher": {"@id": f"{settings.SITE_URL}/#organization"},
    })


@register.simple_tag
def collection_jsonld(name, description, url, items) -> str:
    """CollectionPage со списком ссылок: гайды, заметки региона, рубрики или тега."""
    return _jsonld({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": str(name),
        "description": str(description),
        "url": absolute(str(url)),
        "inLanguage": "ru",
        "isPartOf": {"@id": f"{settings.SITE_URL}/#website"},
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "position": n, "url": absolute(item.get_absolute_url()), "name": item.title}
                for n, item in enumerate(items, start=1)
            ],
        },
    })


@register.simple_tag
def person_jsonld(author) -> str:
    data = {
        "@context": "https://schema.org", "@type": "Person", "name": author.name,
        "url": f"{settings.SITE_URL}{author.get_absolute_url()}",
        "worksFor": {"@id": f"{settings.SITE_URL}/#organization", "name": settings.SITE_NAME},
    }
    if author.role:
        data["jobTitle"] = author.role
    if author.photo:
        data["image"] = f"{settings.SITE_URL}{author.photo.url}"
    return _jsonld(data)
