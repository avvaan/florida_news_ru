from django.conf import settings
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.urls import translate_url
from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.translation.trans_real import parse_accept_lang_header

from stats.tracking import BOT_RE

# Выбор в переключателе «UA | RU» (static/js/lang.js) — важнее настроек браузера.
LANG_COOKIE = "lang"


class CanonicalHostMiddleware:
    """Прежний домен florida-ru.com, www и служебный адрес Render — 301 на канонический домен с тем же путём.

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


def browser_prefers_uk(accept_language: str) -> bool:
    """Из русского и украинского браузер ставит украинский выше. Прочие языки не в счёт: en,uk → украинский."""
    for lang, _q in parse_accept_lang_header(accept_language or ""):
        primary = lang.split("-")[0].lower()
        if primary in ("uk", "ru"):
            return primary == "uk"
    return False


class PreferredLanguageMiddleware:
    """Русская страница, а читатель — украиноязычный: 302 на ту же страницу в /uk/.

    Язык берём из выбора в переключателе (cookie), а если его нет — из настроек браузера (Accept-Language).
    Роботов не перенаправляем: Google видит обе версии по своим адресам и связь между ними через hreflang.
    Ставится после LocaleMiddleware, чтобы язык страницы уже был известен.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ("GET", "HEAD") and translation.get_language() == settings.LANGUAGE_CODE:
            path = request.get_full_path()
            uk_url = translate_url(path, "uk")
            if uk_url != path:  # у страницы есть украинская версия
                if self._wants_uk(request):
                    response = HttpResponseRedirect(uk_url)
                else:
                    response = self.get_response(request)
                patch_vary_headers(response, ("Accept-Language", "Cookie"))
                return response
        return self.get_response(request)

    @staticmethod
    def _wants_uk(request) -> bool:
        chosen = request.COOKIES.get(LANG_COOKIE)
        if chosen in ("ru", "uk"):
            return chosen == "uk"
        if BOT_RE.search(request.META.get("HTTP_USER_AGENT", "")):
            return False
        return browser_prefers_uk(request.META.get("HTTP_ACCEPT_LANGUAGE", ""))
