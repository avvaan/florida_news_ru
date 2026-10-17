from django.core.management.base import BaseCommand
from django.utils import timezone

from sources.fetch import check_source, make_session
from sources.models import Source


class Command(BaseCommand):
    help = (
        "Проверяет, что адреса источников реально отдают RSS/Atom (или GeoJSON для NWS). "
        "С --activate включает рабочие и выключает нерабочие."
    )

    def add_arguments(self, parser):
        parser.add_argument("--activate", action="store_true", help="Включить рабочие, выключить нерабочие")

    def handle(self, *args, **opts):
        session = make_session()
        ok_count = 0
        for source in Source.objects.order_by("source_type", "name"):
            ok, detail = check_source(source, session)
            mark = self.style.SUCCESS("OK  ") if ok else self.style.ERROR("FAIL")
            self.stdout.write(f"{mark} {source.name} — {source.url}\n      {detail}")
            source.is_verified = ok
            source.verified_at = timezone.now()
            if ok:
                ok_count += 1
                source.notes = ""
            else:
                source.last_error = detail
            if opts["activate"]:
                source.is_active = ok
                if ok:
                    source.is_broken = False
                    source.consecutive_failures = 0
            source.save()
        self.stdout.write(f"\nРабочих источников: {ok_count} из {Source.objects.count()}")
        if not opts["activate"]:
            self.stdout.write("Чтобы включить рабочие и выключить нерабочие, добавьте --activate")
