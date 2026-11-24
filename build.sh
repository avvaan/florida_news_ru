#!/usr/bin/env bash
# Сборка на Render: зависимости, статика, миграции.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py import_guides   # гайды из guides/content/ (только новые и изменённые файлы)
python manage.py import_places   # «Что посетить» из places/content/ (ru и uk; только новые и изменённые файлы)
# Ключ API для агента: задайте AGENT_API_TOKEN в Environment на Render — пользователь agent создастся сам.
if [ -n "${AGENT_API_TOKEN:-}" ]; then python manage.py setup_agent --quiet; fi
