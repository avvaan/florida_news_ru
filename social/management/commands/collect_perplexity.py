from social.collectors import collect_search
from social.models import SignalSource

from ._base import CollectorCommand


class Command(CollectorCommand):
    help = "Сигналы из Perplexity: активные запросы из «Источников сигналов»."
    flag = "signals_perplexity_enabled"
    label = "Perplexity"

    def collect(self, say):
        return collect_search(SignalSource.Kind.PERPLEXITY, say)
