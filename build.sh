#!/usr/bin/env bash
# Сборка на Render: зависимости, статика, миграции.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py import_guides   # гайды из guides/content/ (только новые и изменённые файлы)
