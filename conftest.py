import os

# Ничего не отправляем наружу из тестов: ИИ и Telegram мокаются, ключи — заглушки.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")


import pytest


@pytest.fixture(autouse=True)
def _no_article_downloads(monkeypatch):
    """Конвейер читает полные тексты статей-источников — в тестах сеть не трогаем."""
    monkeypatch.setattr("pipeline.services.full_texts", lambda items, **kw: {})


@pytest.fixture(autouse=True)
def _no_translation_in_pipeline(request, monkeypatch):
    """Перевод на украинский в конвейере ходит в ИИ — в чужих тестах выключен (свои — tests/test_i18n.py)."""
    if "translation" not in request.keywords:
        monkeypatch.setattr("core.translation.translate_pending", lambda say=print, **kw: 0)
        monkeypatch.setattr("core.translation.spawn_translation", lambda **kw: True)


@pytest.fixture(autouse=True)
def _russian_by_default():
    """Запрос к /uk/… оставляет украинский активным в потоке — каждый тест начинаем с русского."""
    from django.utils import translation

    translation.activate("ru")
    yield
    translation.activate("ru")
