import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .tracking import own_hosts, rate_limited, record_hit, referrer_origin

log = logging.getLogger(__name__)

MAX_BODY = 4096


def from_our_page(request) -> bool:
    """Сигнал шлёт наша страница: браузер ставит Origin (или Referer) нашего сайта."""
    origin = request.META.get("HTTP_ORIGIN") or referrer_origin(request.META.get("HTTP_REFERER", ""))
    host = origin.split("://", 1)[-1].split(":")[0].lower().removeprefix("www.")
    return bool(host) and host in own_hosts(request)


@csrf_exempt
@require_POST
def hit(request):
    """Сигнал «страницу открыли» из static/js/hit.js. Всегда 204, кроме превышения лимита (429)."""
    if rate_limited(request):
        return HttpResponse(status=429)
    if len(request.body) > MAX_BODY or not from_our_page(request):
        return HttpResponse(status=204)
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        return HttpResponse(status=204)  # редакция не накручивает статистику
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponse(status=204)
    if isinstance(data, dict):
        try:
            record_hit(request, data)
        except Exception as exc:  # noqa: BLE001 — статистика не должна мешать сайту
            log.warning("Статистика: %s", exc)
    return HttpResponse(status=204)
