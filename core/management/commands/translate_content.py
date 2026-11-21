from decimal import Decimal

from django.core.management.base import BaseCommand

from core.translation import pending, translate_pending


class Command(BaseCommand):
    help = ("Перевод контента на украинский (поля *_uk): рубрики, заметки, афиша, справочник, гайды, страницы. "
            "Переводит только новое и то, что поменяли после перевода.")

    def add_arguments(self, parser):
        parser.add_argument("--model", action="append", dest="models",
                            help="Только эти модели: article, event, listing, region, topic, page… (можно несколько)")
        parser.add_argument("--limit", type=int, help="Не больше стольких записей за запуск")
        parser.add_argument("--budget", type=Decimal, help="Дневной бюджет на перевод, $ (по умолчанию AI_TRANSLATE_BUDGET_PER_DAY)")
        parser.add_argument("--dry-run", action="store_true", help="Только показать, сколько ждёт перевода")

    def handle(self, *args, **opts):
        models_ = [m.lower() for m in opts["models"] or []] or None
        if opts["dry_run"]:
            for target, objs in pending(models_):
                self.stdout.write(f"{target.model._meta.verbose_name_plural}: {len(objs)}")
            return
        translate_pending(self.stdout.write, models_=models_, limit=opts["limit"], budget=opts["budget"])
