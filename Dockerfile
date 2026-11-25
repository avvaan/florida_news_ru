# Образ сайта для домашнего сервера mimi (docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Сначала зависимости: правка кода их не переустанавливает.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Статика собирается в образ (WhiteNoise, хешированные имена). База не нужна;
# ключ — одноразовый, только для сборки.
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

# Код принадлежит root и только читается пользователем сайта.
# media/ (картинки рекламы, фото авторов) — том, в который пишет app.
RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app \
    && mkdir -p /app/media && chown app:app /app/media
USER app

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--threads", "4", "--timeout", "60", \
     "--max-requests", "1000", "--max-requests-jitter", "100", \
     "--worker-tmp-dir", "/dev/shm"]
