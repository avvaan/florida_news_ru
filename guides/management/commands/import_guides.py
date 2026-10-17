from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from guides import importer
from guides.models import Guide, GuideSource
from news.models import Topic


class Command(BaseCommand):
    help = (
        "Гайды из guides/content/*.md → база: создаёт и обновляет изменённые файлы. "
        "Пост в Telegram не отправляет (опубликовать в канал — действием в админке)."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="только эти гайды (по имени файла)")
        parser.add_argument("--check", action="store_true", help="только проверить файлы, базу не трогать")
        parser.add_argument("--no-images", action="store_true", help="не требовать картинок (черновая проверка)")
        parser.add_argument("--force", action="store_true", help="перезаписать, даже если файл не менялся")

    def handle(self, *args, slugs, check, no_images, force, **options):
        files = importer.content_files(slugs)
        if not files:
            raise CommandError("Нет файлов в guides/content/")
        parsed, failed = [], 0
        for path in files:
            try:
                guide = importer.parse_file(path)
                errors = importer.validate(guide, check_images=not no_images)
            except (ValueError, IndexError) as exc:
                guide, errors = None, [str(exc)]
            length = importer.markup.plain_length(guide.body) if guide else 0
            if errors:
                failed += 1
                self.stdout.write(self.style.ERROR(f"✗ {path.name} ({length} зн.)"))
                for error in errors:
                    self.stdout.write(f"    – {error}")
            else:
                self.stdout.write(f"✓ {path.name} ({length} зн.)")
                parsed.append(guide)
        if check:
            if failed:
                raise CommandError(f"Ошибки в {failed} из {len(files)} файлов")
            return
        if failed:
            raise CommandError(f"Ошибки в {failed} из {len(files)} файлов — ничего не импортировано")
        created = updated = skipped = 0
        with transaction.atomic():
            for data in parsed:
                result = self.sync(data, force)
                created += result == "created"
                updated += result == "updated"
                skipped += result == "skipped"
        self.stdout.write(self.style.SUCCESS(f"Новых: {created}, обновлено: {updated}, без изменений: {skipped}"))

    def sync(self, data: importer.GuideFile, force: bool) -> str:
        guide = Guide.objects.filter(slug=data.slug).first()
        if guide and guide.content_hash == data.content_hash and not force:
            return "skipped"
        is_new = guide is None
        guide = guide or Guide(slug=data.slug)
        now = timezone.now()
        if guide.is_published and guide.body.strip() and guide.body != data.body:
            guide.revised_at = now
        guide.title, guide.teaser, guide.body = data.title, data.teaser, data.body
        guide.section, guide.order, guide.cover = data.section, data.order, data.cover
        guide.content_hash = data.content_hash
        guide.official_domains = guide.official_domains or ", ".join(
            sorted({url.split("/")[2].removeprefix("www.") for _, url, _ in data.sources})
        )[:500]
        if data.status == "published":
            guide.status = Guide.Status.PUBLISHED
            guide.published_at = guide.published_at or now
        else:
            guide.status = Guide.Status.DRAFT
        guide.save()
        guide.topics.set(Topic.objects.filter(slug__in=data.topics))
        guide.sources.all().delete()
        GuideSource.objects.bulk_create([
            GuideSource(guide=guide, name=name[:120], url=url, title=title[:400], order=i)
            for i, (name, url, title) in enumerate(data.sources)
        ])
        return "created" if is_new else "updated"
