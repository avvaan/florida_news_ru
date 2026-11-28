from django.core.management.base import BaseCommand

from pipeline.models import PipelineRun
from pipeline.runner import active_run
from pipeline.services import run_pipeline


class Command(BaseCommand):
    help = "Полный проход: сбор фидов → склейка → отбор → заметки → проверка → публикация. Запускается дважды в день, утром и вечером."

    def add_arguments(self, parser):
        parser.add_argument("--no-fetch", action="store_true", help="Не ходить в сеть, обработать уже собранное")
        parser.add_argument("--no-write", action="store_true", help="Только сбор и склейка, без ИИ")
        parser.add_argument("--run-id", type=int, help="Продолжить уже созданную запись запуска (кнопка в админке)")

    def handle(self, *args, **opts):
        run = PipelineRun.objects.get(pk=opts["run_id"]) if opts["run_id"] else None
        if run is None and (busy := active_run()):
            # Например, cron сработал, пока идёт проход, запущенный кнопкой из админки.
            self.stdout.write(self.style.WARNING(f"Конвейер уже работает (запуск от {busy}) — пропускаю."))
            return
        run = run_pipeline(fetch=not opts["no_fetch"], write=not opts["no_write"], run=run)
        self.stdout.write(run.log)
        style = self.style.SUCCESS if run.success else self.style.ERROR
        self.stdout.write(style(f"Готово: {run.stats}"))
