from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalHostMiddleware:
    """Служебный адрес Render (*.onrender.com) — 301 на канонический домен с тем же путём и запросом.

    Проверку здоровья Render (HEALTHCHECK_PATH) не трогаем, иначе сервис сочтут упавшим.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        if (host != settings.CANONICAL_HOST and host.endswith(settings.REDIRECT_TO_CANONICAL_SUFFIXES)
                and request.path != settings.HEALTHCHECK_PATH):
            return HttpResponsePermanentRedirect(f"{settings.SITE_URL}{request.get_full_path()}")
        return self.get_response(request)
