from django.core.management.base import BaseCommand

from pipeline.services import run_pipeline


class Command(BaseCommand):
    help = "Полный проход: сбор фидов → склейка → отбор → заметки → проверка → публикация. Запускать раз в 2–3 часа."

    def add_arguments(self, parser):
        parser.add_argument("--no-fetch", action="store_true", help="Не ходить в сеть, обработать уже собранное")
        parser.add_argument("--no-write", action="store_true", help="Только сбор и склейка, без ИИ")

    def handle(self, *args, **opts):
        run = run_pipeline(fetch=not opts["no_fetch"], write=not opts["no_write"])
        self.stdout.write(run.log)
        style = self.style.SUCCESS if run.success else self.style.ERROR
        self.stdout.write(style(f"Готово: {run.stats}"))
