from django.core.management.base import BaseCommand, CommandError

from core.text import make_slug
from guides.drafting import DraftError, draft_guide
from guides.models import Guide


class Command(BaseCommand):
    help = ('Написать ЧЕРНОВИК гайда по официальным источникам: draft_guide "<тема или slug>". '
            "Публикует только редактор вручную в админке.")

    def add_arguments(self, parser):
        parser.add_argument("topic", help="slug существующего гайда или тема нового")
        parser.add_argument("--domains", default="", help="Официальные сайты через запятую (для нового гайда)")

    def handle(self, *args, topic, domains, **opts):
        guide = Guide.objects.filter(slug=topic).first() or Guide.objects.filter(title__iexact=topic).first()
        if guide is None:
            slug = make_slug(topic, max_length=110)
            if not slug or Guide.objects.filter(slug=slug).exists():
                raise CommandError(f"Не удалось подобрать адрес для «{topic}» — укажите slug существующего гайда")
            guide = Guide.objects.create(title=topic[:160], slug=slug, brief=topic, official_domains=domains)
            self.stdout.write(f"Новый гайд-черновик: {guide.slug}")
        try:
            draft_guide(guide)
        except DraftError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Черновик готов: «{guide.title}», источников: {guide.sources.count()}. {guide.review_notes}"))
        self.stdout.write("Проверьте и опубликуйте в админке: Гайды → гайд → статус «опубликован».")
