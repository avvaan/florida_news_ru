"""Проверка здоровья веб-контейнера: GET /healthz так, как его шлёт туннель.

docker-compose.yml запускает ``python deploy/healthcheck.py`` внутри контейнера;
код выхода 0 — здоров (HTTP 200), 1 — нет.

Запрос несёт первый хост из DJANGO_ALLOWED_HOSTS и ``X-Forwarded-Proto: https``,
как каждый запрос от Cloudflare: без них при DJANGO_DEBUG=0 был бы 400 (чужой
хост) или 301 (на HTTPS). Редиректы не выполняются: 301 здесь — уже сбой.
"""
import http.client
import os
import sys
import urllib.request

URL = 'http://127.0.0.1:8000/healthz'


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def site_host():
    hosts = [h.strip().lstrip('.') for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')]
    return next((h for h in hosts if h and h != '*'), 'localhost')


def main():
    opener = urllib.request.build_opener(RefuseRedirects, urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        URL, headers={'Host': site_host(), 'X-Forwarded-Proto': 'https'},
    )
    try:
        with opener.open(request, timeout=5) as response:
            status = response.status
    except (OSError, http.client.HTTPException) as error:
        print(f'unhealthy: {URL}: {error}', file=sys.stderr)
        return 1
    if status != 200:
        print(f'unhealthy: {URL} answered {status}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
