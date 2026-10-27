from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from stats.models import DailyStat, Hit, Source
from stats.tracking import is_ip, own_hosts, reclassify


class Command(BaseCommand):
    help = ("Заново применяет правила «бот / человек» и «откуда пришли» к сохранённым просмотрам "
            "и печатает сводку по дням: старый серверный счётчик против новых данных (люди / боты).")

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=11, help="Сколько последних дней показать в сводке")
        parser.add_argument("--dry-run", action="store_true", help="Ничего не менять, только посчитать")

    def handle(self, *args, days, dry_run, **opts):
        hosts = own_hosts()
        changed = []
        for hit in Hit.objects.iterator(chunk_size=2000):
            if reclassify(hit, hosts):
                changed.append(hit)
        if changed and not dry_run:
            Hit.objects.bulk_update(changed, ["is_bot", "bot_reason", "source"], batch_size=1000)
        verb = "изменилось бы" if dry_run else "изменено"
        self.stdout.write(f"Просмотров: {Hit.objects.count()}, {verb} по новым правилам: {len(changed)}\n")
        self.report(days)

    def report(self, days):
        today = timezone.localdate()
        start = today - timedelta(days=days - 1)
        legacy = {s.date: s for s in DailyStat.objects.filter(date__gte=start)}
        entries = {}
        for day, label, visits in Source.objects.filter(date__gte=start).values_list("date", "source", "visits"):
            row = entries.setdefault(day, {"all": 0, "direct": 0, "ip": 0})
            row["all"] += visits
            row["direct"] += visits if label == Source.DIRECT else 0
            row["ip"] += visits if is_ip(label) else 0
        hits = {}
        for row in (Hit.objects.filter(date__gte=start).values("date", "is_bot")
                    .annotate(views=Count("id"), visitors=Count("visitor", distinct=True))):
            hits[(row["date"], row["is_bot"])] = row

        self.stdout.write("Старый счётчик (сервер, с ботами)                 | Новый: люди        | боты")
        self.stdout.write("день        просм.  посет.  на посет.  прямые  из IP | просм.  посет.     | просм.")
        totals = dict.fromkeys(("old_views", "old_visitors", "views", "visitors", "bots"), 0)
        for n in range(days):
            day = start + timedelta(days=n)
            old, src = legacy.get(day), entries.get(day, {"all": 0, "direct": 0, "ip": 0})
            human, bot = hits.get((day, False), {}), hits.get((day, True), {})
            old_views, old_visitors = (old.views, old.visitors) if old else (0, 0)
            per = f"{old_views / old_visitors:.2f}" if old_visitors else "—"
            direct = f"{src['direct'] / src['all'] * 100:.0f}%" if src["all"] else "—"
            self.stdout.write(
                f"{day:%Y-%m-%d}  {old_views:6}  {old_visitors:6}  {per:>9}  {direct:>6}  {src['ip']:5} | "
                f"{human.get('views', 0):6}  {human.get('visitors', 0):6}     | {bot.get('views', 0):6}"
            )
            totals["old_views"] += old_views
            totals["old_visitors"] += old_visitors
            totals["views"] += human.get("views", 0)
            totals["visitors"] += human.get("visitors", 0)
            totals["bots"] += bot.get("views", 0)
        self.stdout.write(
            f"Итого: старый счётчик {totals['old_views']} просмотров / {totals['old_visitors']} посетителей; "
            f"новый — люди {totals['views']} / {totals['visitors']}, боты {totals['bots']} просмотров."
        )
        old_days = [d for d in legacy if not any((d, b) in hits for b in (False, True))]
        if old_days:
            self.stdout.write(
                f"Дни только со старым счётчиком ({len(old_days)}): он хранил лишь дневные суммы, без User-Agent "
                "и адресов, поэтому задним числом отделить в них ботов нельзя — в панели они бледные и в итоги "
                "«только люди» не входят."
            )
