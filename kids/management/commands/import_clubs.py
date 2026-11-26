from django.core.management.base import BaseCommand, CommandError

from kids.importer import COLUMNS, import_csv


class Command(BaseCommand):
    help = ("Импорт детских кружков из CSV (колонки — поля модели: " + ", ".join(COLUMNS) + "). "
            "Повторный запуск не создаёт дублей; новые записи — черновики.")

    def add_arguments(self, parser):
        parser.add_argument("path", help="CSV в UTF-8, разделитель «,» или «;»")
        parser.add_argument("--dry-run", action="store_true", help="Проверить файл, ничего не сохраняя")

    def handle(self, path, dry_run=False, **options):
        try:
            report = import_csv(path, dry_run=dry_run)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        for club in report.created:
            self.stdout.write(f"+ {club.name} [{club.get_status_display()}]")
        for club in report.updated:
            self.stdout.write(f"~ {club.name}")
        for line, message in report.errors:
            self.stderr.write(f"! строка {line}: {message}")
        prefix = "Проверка (ничего не сохранено) — " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(prefix + report.summary()))
