from django.core.management.base import BaseCommand

from news.models import Article
from pipeline.services import rechoose_covers


class Command(BaseCommand):
    help = "ИИ подбирает обложки уже написанным заметкам по их тексту. По умолчанию — опубликованным без выбранной обложки."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Перевыбрать и у заметок, где обложка уже выбрана")
        parser.add_argument("--status", default=Article.Status.PUBLISHED, choices=Article.Status.values)
        parser.add_argument("--topic", help="slug темы, например weather")
        parser.add_argument("--limit", type=int, default=50, help="Сколько заметок, новые первыми (по умолчанию 50)")
        parser.add_argument("--ids", type=int, nargs="+", help="Конкретные заметки по id")

    def handle(self, *args, **opts):
        qs = Article.objects.select_related("topic", "story")
        if opts["ids"]:
            qs = qs.filter(pk__in=opts["ids"])
        else:
            qs = qs.filter(status=opts["status"])
            if not opts["all"]:
                qs = qs.filter(cover_image="")
            if opts["topic"]:
                qs = qs.filter(topic__slug=opts["topic"])
            qs = qs.order_by("-published_at", "-created_at")[:opts["limit"]]
        run = rechoose_covers(list(qs))
        self.stdout.write(run.log)
        style = self.style.SUCCESS if run.success else self.style.ERROR
        self.stdout.write(style(f"Готово: {run.stats}"))
