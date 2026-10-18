import json

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

from news import featured

register = template.Library()


@register.simple_tag
def featured_events():
    return featured.upcoming()


@register.simple_tag
def event_jsonld(event):
    """Разметка schema.org/Event — фестиваль может попасть в блок событий Google."""
    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event.title,
        "description": event.teaser,
        "startDate": event.start_dt.isoformat(),
        "endDate": event.end_dt.isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "image": [f"{settings.SITE_URL}{static(event.image_static + '.jpg')}"],
        "url": event.url,
        "location": {
            "@type": "Place",
            "name": event.venue,
            "address": {
                "@type": "PostalAddress", "streetAddress": event.address, "addressLocality": "Casselberry",
                "addressRegion": "FL", "postalCode": "32707", "addressCountry": "US",
            },
        },
        "offers": {"@type": "Offer", "url": event.tickets_url, "availability": "https://schema.org/InStock"},
        "organizer": {"@type": "Organization", "name": "Миссия Святой Нины", "url": event.url},
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')
