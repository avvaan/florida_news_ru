#!/bin/sh
# Старт веб-контейнера (ENTRYPOINT в Dockerfile).
# С MIGRATE_ON_START=1 (docker-compose.yml) сначала — то же, что делал build.sh
# на Render: миграции и импорт гайдов из guides/content/ (только новые и
# изменённые файлы). Потом команда — gunicorn, если не задана другая.
set -e

if [ "${MIGRATE_ON_START:-0}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py import_guides
fi

exec "$@"
