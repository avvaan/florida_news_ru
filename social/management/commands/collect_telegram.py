from social.collectors import collect_telegram

from ._base import CollectorCommand


class Command(CollectorCommand):
    help = "Сигналы из публичных Telegram-каналов (только открытые каналы, без чатов и личных сообщений)."
    flag = "signals_telegram_enabled"
    label = "Telegram"

    def collect(self, say):
        return collect_telegram(say)
