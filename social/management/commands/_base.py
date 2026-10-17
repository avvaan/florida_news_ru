from django.core.management.base import BaseCommand

from core.models import SiteSettings
from pipeline.services import RunLog


class CollectorCommand(BaseCommand):
    """Общая часть сборщиков: проверка флага в настройках и печать журнала."""

    flag = ""
    label = ""

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Собрать, даже если сборщик выключен в настройках")

    def collect(self, say) -> dict:
        raise NotImplementedError

    def handle(self, *args, **opts):
        if not opts["force"] and not getattr(SiteSettings.load(), self.flag):
            self.stdout.write(self.style.WARNING(f"{self.label}: выключено в настройках сайта (или --force)"))
            return
        say = RunLog()
        stats = self.collect(say)
        if say.lines:
            self.stdout.write(say.text())
        self.stdout.write(self.style.SUCCESS(f"{self.label}: новых сигналов {stats['created']}, ошибок {stats['failed']}"))
