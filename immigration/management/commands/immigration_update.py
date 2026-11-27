from django.core.management.base import BaseCommand

from immigration.knowledge import update_all
from immigration.privacy import purge_expired


class Command(BaseCommand):
    help = ("Обновить базу знаний иммиграционного помощника: официальные страницы (только из списка "
            "immigration/sources.py), Federal Register за 90 дней, Visa Bulletin, наши гайды и новости. "
            "Заодно удаляет переписку старше срока хранения. Раз в неделю по cron.")

    def add_arguments(self, parser):
        parser.add_argument("--only", default="", help="Только адреса, содержащие эту строку (проверка одного адреса)")
        parser.add_argument("--no-official", action="store_true", help="Без официальных сайтов (только наши материалы)")
        parser.add_argument("--no-ours", action="store_true", help="Без наших гайдов и новостей")

    def handle(self, only="", no_official=False, no_ours=False, **options):
        report = update_all(only=only, official=not no_official, ours=not no_ours)
        for o in report.outcomes:
            mark = "✓" if o.status == "ok" else "✗"
            changed = " (изменилась)" if o.changed else ""
            self.stdout.write(f"{mark} {o.status:9} {o.chunks:4} фр.  {o.url}{changed} {o.note}")
        deleted = purge_expired()
        self.stdout.write(self.style.SUCCESS(f"{report.summary()}; удалено старой переписки: {deleted}"))
