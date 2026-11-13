import os

# Ничего не отправляем наружу из тестов: ИИ и Telegram мокаются, ключи — заглушки.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")


import pytest


@pytest.fixture(autouse=True)
def _no_article_downloads(monkeypatch):
    """Конвейер читает полные тексты статей-источников — в тестах сеть не трогаем."""
    monkeypatch.setattr("pipeline.services.full_texts", lambda items, **kw: {})
