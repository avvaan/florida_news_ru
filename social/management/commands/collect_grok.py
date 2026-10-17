from social.collectors import collect_search
from social.models import SignalSource

from ._base import CollectorCommand


class Command(CollectorCommand):
    help = "Сигналы из X через Grok (xAI): активные запросы из «Источников сигналов»."
    flag = "signals_grok_enabled"
    label = "Grok"

    def collect(self, say):
        return collect_search(SignalSource.Kind.GROK, say)
