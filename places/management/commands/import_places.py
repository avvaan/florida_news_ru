from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from places import importer
from places.models import Destination, DestinationSource


class Command(BaseCommand):
    help = (
        "Статьи «Что посетить» из places/content/<ru|uk>/*.md → база: создаёт и обновляет изменённые файлы. "
        "Проверяет каждый файл (объём, картинки, карточки мест) и пары ru/uk; при ошибке не импортирует ничего."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="только эти статьи (по имени файла)")
        parser.add_argument("--check", action="store_true", help="только проверить файлы, базу не трогать")
        parser.add_argument("--no-images", action="store_true", help="не требовать файлов картинок")
        parser.add_argument("--force", action="store_true", help="перезаписать, даже если файл не менялся")

    def handle(self, *args, slugs, check, no_images, force, **options):
        files = importer.content_files(slugs)
        if not files:
            if slugs:
                raise CommandError(f"Нет файлов для {', '.join(slugs)} в places/content/ru и places/content/uk")
            self.stdout.write("Нет файлов в places/content/ru и places/content/uk — нечего импортировать")
            return
        parsed, failed = {}, 0
        for path in files:
            name = f"{path.parent.name}/{path.name}"
            try:
                item = importer.parse_file(path)
                errors = importer.validate(item, check_images=not no_images)
            except (ValueError, IndexError) as exc:
                item, errors = None, [str(exc)]
            length = importer.markup.plain_length(item.body) if item else 0
            places = sum(b.kind == "place" for b in item.blocks) if item else 0
            if errors:
                failed += 1
                self.stdout.write(self.style.ERROR(f"✗ {name} ({length} зн., мест: {places})"))
                for error in errors:
                    self.stdout.write(f"    – {error}")
            else:
                self.stdout.write(f"✓ {name} ({length} зн., мест: {places})")
            if item:
                parsed[(item.path.stem, path.parent.name)] = item
        for slug in sorted({slug for slug, _ in parsed}):
            if errors := importer.validate_pair(parsed.get((slug, "ru")), parsed.get((slug, "uk"))):
                failed += 1
                self.stdout.write(self.style.ERROR(f"✗ пара {slug}"))
                for error in errors:
                    self.stdout.write(f"    – {error}")
        if failed:
            raise CommandError(f"Ошибок: {failed}" + ("" if check else " — ничего не импортировано"))
        if check:
            self.stdout.write(self.style.SUCCESS(f"Все {len(files)} файлов в порядке"))
            return
        counts = {"created": 0, "updated": 0, "skipped": 0}
        with transaction.atomic():
            for item in parsed.values():
                counts[self.sync(item, force)] += 1
        self.stdout.write(self.style.SUCCESS(
            f"Новых: {counts['created']}, обновлено: {counts['updated']}, без изменений: {counts['skipped']}"
        ))

    def sync(self, data: importer.DestinationFile, force: bool) -> str:
        item = Destination.objects.filter(slug=data.slug, lang=data.lang).first()
        if item and item.content_hash == data.content_hash and not force:
            return "skipped"
        is_new = item is None
        item = item or Destination(slug=data.slug, lang=data.lang)
        now = timezone.now()
        if item.is_published and item.body.strip() and item.body != data.body:
            item.revised_at = now
        item.title, item.teaser, item.body = data.title, data.teaser, data.body
        item.region, item.order, item.cover = data.region, data.order, data.cover
        item.cover_caption, item.checked_on = data.cover_caption, data.checked
        item.photo_credits = importer.photo_credits(data.slug)
        item.content_hash = data.content_hash
        if data.status == "published":
            item.status = Destination.Status.PUBLISHED
            item.published_at = item.published_at or now
        else:
            item.status = Destination.Status.DRAFT
        item.save()
        item.sources.all().delete()
        DestinationSource.objects.bulk_create([
            DestinationSource(destination=item, name=name[:120], url=url, title=title[:400], order=i)
            for i, (name, url, title) in enumerate(data.sources)
        ])
        return "created" if is_new else "updated"
