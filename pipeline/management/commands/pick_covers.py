from django.core.management.base import BaseCommand

from news.models import Article
from pipeline.services import fix_repeated_covers, rechoose_covers


class Command(BaseCommand):
    help = ("ИИ подбирает обложки уже написанным заметкам по их тексту. По умолчанию — опубликованным без выбранной "
            "обложки. С --fix-repeats — только тем, чья обложка повторяет соседей в ленте (кроме выбранных вручную).")

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Перевыбрать и у заметок, где обложка уже выбрана")
        parser.add_argument("--status", default=Article.Status.PUBLISHED, choices=Article.Status.values)
        parser.add_argument("--topic", help="slug темы, например weather")
        parser.add_argument("--limit", type=int, default=50, help="Сколько заметок, новые первыми (по умолчанию 50)")
        parser.add_argument("--ids", type=int, nargs="+", help="Конкретные заметки по id")
        parser.add_argument("--fix-repeats", action="store_true",
                            help="Заменить обложки, повторяющие соседние заметки в ленте; вручную выбранные не трогать")
        parser.add_argument("--no-ai", action="store_true",
                            help="С --fix-repeats: брать другую картинку из того же набора без запросов к ИИ")

    def handle(self, *args, **opts):
        qs = Article.objects.select_related("topic", "story")
        if opts["ids"]:
            qs = qs.filter(pk__in=opts["ids"])
        else:
            qs = qs.filter(status=opts["status"])
            if not opts["all"] and not opts["fix_repeats"]:
                qs = qs.filter(cover_image="")
            if opts["topic"]:
                qs = qs.filter(topic__slug=opts["topic"])
            qs = qs.order_by("-published_at", "-created_at")[:opts["limit"]]
        if opts["fix_repeats"]:
            run = fix_repeated_covers(list(qs), use_ai=not opts["no_ai"])
        else:
            run = rechoose_covers(list(qs))
        self.stdout.write(run.log)
        style = self.style.SUCCESS if run.success else self.style.ERROR
        self.stdout.write(style(f"Готово: {run.stats}"))
