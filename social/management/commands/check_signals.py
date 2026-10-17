import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand

from social.collectors import CollectorError, make_telegram_client, search_grok, search_perplexity

PING = "Главная новость Флориды за сегодня"


class Command(BaseCommand):
    help = ("Проверить ключи сервисов сигналов. Без --ping — только наличие переменных; "
            "с --ping — по одному платному тестовому запросу к Perplexity и Grok и вход в Telegram.")

    def add_arguments(self, parser):
        parser.add_argument("--ping", action="store_true")

    def handle(self, *args, **opts):
        checks = [
            ("Perplexity", settings.PERPLEXITY_API_KEY, settings.PERPLEXITY_MODEL, lambda: search_perplexity(PING)),
            ("Grok", settings.XAI_API_KEY, settings.XAI_MODEL, lambda: search_grok(PING)),
        ]
        for name, key, model, call in checks:
            if not key:
                self.stdout.write(self.style.WARNING(f"{name}: ключ не задан"))
                continue
            if not opts["ping"]:
                self.stdout.write(f"{name}: ключ задан, модель {model}")
                continue
            try:
                items = call()
                self.stdout.write(self.style.SUCCESS(f"{name}: OK, модель {model}, ссылок в ответе: {len(items)}"))
            except CollectorError as exc:
                self.stdout.write(self.style.ERROR(f"{name}: {exc}"))
        if not (settings.TG_API_ID and settings.TG_API_HASH and settings.TG_SESSION):
            self.stdout.write(self.style.WARNING("Telegram: нужны TG_API_ID, TG_API_HASH и TG_SESSION"))
        elif opts["ping"]:
            try:
                me = asyncio.run(self.telegram_me())
                self.stdout.write(self.style.SUCCESS(f"Telegram: OK, аккаунт @{me}"))
            except Exception as exc:  # noqa: BLE001 — сеть, сессия, неверные ключи
                self.stdout.write(self.style.ERROR(f"Telegram: {exc}"))
        else:
            self.stdout.write("Telegram: переменные заданы")

    async def telegram_me(self) -> str:
        client = make_telegram_client()
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise CollectorError("сессия недействительна — выполните telegram_login")
            me = await client.get_me()
            return me.username or str(me.id)
        finally:
            await client.disconnect()
