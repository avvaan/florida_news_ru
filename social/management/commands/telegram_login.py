import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = ("Один раз войти в Telegram-аккаунт для чтения публичных каналов и получить строку TG_SESSION. "
            "Спросит номер телефона, код из Telegram и пароль двухэтапной проверки, если он есть.")

    def handle(self, *args, **opts):
        if not (settings.TG_API_ID and settings.TG_API_HASH):
            raise CommandError("Сначала задайте TG_API_ID и TG_API_HASH (https://my.telegram.org → API development tools)")
        session = asyncio.run(self.login())
        self.stdout.write(self.style.SUCCESS("\nГотово. Добавьте в переменные окружения Render:"))
        self.stdout.write(f"TG_SESSION={session}")
        self.stdout.write(self.style.WARNING(
            "Эта строка даёт полный доступ к аккаунту: храните её только в переменных окружения, никому не пересылайте."))

    async def login(self) -> str:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(), int(settings.TG_API_ID), settings.TG_API_HASH)
        await client.start()  # спрашивает телефон, код и пароль в терминале
        me = await client.get_me()
        self.stdout.write(f"Вошли как {me.first_name or ''} (@{me.username or '—'})")
        session = client.session.save()
        await client.disconnect()
        return session
