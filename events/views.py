from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from core.i18n import only_language
from directory.views import ip_hash
from news import featured
from news.models import EVENTS, Article

from . import moderation
from .forms import EventForm
from .models import Event


def event_list(request):
    upcoming = list(Event.objects.upcoming().for_language().select_related("region"))
    regions = sorted({e.region for e in upcoming if e.region}, key=lambda r: r.order)
    has_other = any(e.region is None for e in upcoming)
    current = request.GET.get("region", "")
    if current == "other":
        events = [e for e in upcoming if e.region is None]
    elif current:
        events = [e for e in upcoming if e.region and e.region.slug == current]
    else:
        # Без фильтра фестивали от редакции стоят сверху крупными карточками — в сетке их не дублируем.
        events = [e for e in upcoming if e.slug not in featured.slugs()]
    news = list(Article.objects.published().filter(topic__slug=EVENTS).select_related("region", "topic")[:6]) \
        if not current else []
    return render(request, "events/list.html", {
        "events": events, "total": len(upcoming), "current_region": current, "has_other": has_other, "news": news,
        "regions": regions if len(regions) + has_other > 1 else [],
    })


def event_detail(request, slug):
    event = get_object_or_404(Event.objects.published().for_language().select_related("region"), slug=slug)
    only_language(request, event.language, "events:list")  # другой версии нет — переключатель ведёт в афишу
    others = list(Event.objects.upcoming().for_language().exclude(pk=event.pk).select_related("region")[:20])
    more = sorted(others, key=lambda e: e.region_id != event.region_id)[:4]  # сначала из того же региона
    return render(request, "events/detail.html", {"event": event, "more": more})


def _detail_language(slug) -> str:
    return Event.objects.filter(slug=slug).values_list("language", flat=True).first() or ""


# Для core.middleware.PreferredLanguageMiddleware: не уводить на /uk/… событие только для русской версии.
event_detail.page_language = _detail_language


@never_cache
def submit(request):
    form = EventForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("company"):  # бот заполнил скрытое поле — делаем вид, что всё хорошо
            return render(request, "events/submit_done.html", {"event": None})
        key = ip_hash(request)
        if Event.objects.since(24).filter(ip_hash=key).count() >= moderation.MAX_PER_IP_PER_DAY:
            form.add_error(None, _("С этого адреса уже отправлено несколько заявок за сутки. Попробуйте завтра."))
        else:
            event = form.save(commit=False)
            event.ip_hash = key
            event.slug = event.make_unique_slug()
            if form.image_bytes:
                event.image_data = form.image_bytes
                event.image_status = Event.ImageStatus.PENDING
            event.save()
            moderation.start_moderation(event)
            return redirect("events:submission", token=event.token)
    return render(request, "events/submit.html", {"form": form})


@never_cache
def submission_status(request, token):
    event = get_object_or_404(Event, token=token)
    return render(request, "events/submit_done.html", {"event": event})
