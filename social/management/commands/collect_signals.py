from django.core.management.base import BaseCommand

from pipeline.services import RunLog
from social.services import run_social


class Command(BaseCommand):
    help = ("Весь этап «Сигналы из соцсетей»: включённые сборщики → разбор → подтверждение подсказок. "
            "Обычно запускается сам внутри run_pipeline.")

    def handle(self, *args, **opts):
        say = RunLog()
        stats = run_social(say)
        if say.lines:
            self.stdout.write(say.text())
        self.stdout.write(self.style.SUCCESS(f"Готово: {stats}"))
