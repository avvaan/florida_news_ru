from django.core.management.base import BaseCommand

from pipeline.clustering import cluster_items
from sources.fetch import fetch_all
from sources.models import Source


class Command(BaseCommand):
    help = "Собрать новые записи из активных источников (без ИИ) и склеить их в сюжеты."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=int, action="append", help="id источника (можно несколько)")
        parser.add_argument("--include-broken", action="store_true", help="Опросить и сломанные источники")

    def handle(self, *args, **opts):
        qs = Source.objects.filter(is_active=True)
        if opts["source"]:
            qs = Source.objects.filter(pk__in=opts["source"])
        for r in fetch_all(qs, include_broken=opts["include_broken"]):
            if r.error:
                self.stdout.write(self.style.ERROR(f"✗ {r.source.name}: {r.error[:200]}"))
            elif r.not_modified:
                self.stdout.write(f"· {r.source.name}: без изменений (304)")
            else:
                extra = f", предупреждений {r.alerts}" if r.alerts else ""
                self.stdout.write(self.style.SUCCESS(
                    f"✓ {r.source.name}: новых {r.created}, уже было {r.skipped}{extra}"
                ))
        stats = cluster_items()
        self.stdout.write(f"Сюжеты: новых {stats['new_stories']}, присоединено {stats['attached']}")
