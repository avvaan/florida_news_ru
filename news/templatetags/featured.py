from django import template

from news import featured

register = template.Library()


@register.simple_tag
def featured_events():
    return featured.upcoming()
