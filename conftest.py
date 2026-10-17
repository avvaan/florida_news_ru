import os

# Ничего не отправляем наружу из тестов: ИИ и Telegram мокаются, ключи — заглушки.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
