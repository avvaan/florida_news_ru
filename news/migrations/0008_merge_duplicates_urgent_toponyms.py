"""Аудит 10.2026: объединить дубли (301 на первую заметку), срок «Срочно» для старых заметок, топонимы."""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone

from pipeline.toponyms import fix_text

# (оставляем — первая по времени публикации, дубль → 301 на неё)
DUPLICATES = [
    ("v-parke-uinter-gardena-alligator-ubil-71-letnego-rybaka",
     "vo-floride-71-letniy-muzhchina-pogib-pri-napadenii-alligatora"),
    ("florida-prosit-federalnuyu-pomoshch-posle-uragana-isaias",
     "florida-prosit-belyy-dom-o-statuse-krupnogo-bedstviya-posle-uragana-isaias"),
    ("livni-v-brauarde-preduprezhdenie-o-vnezapnykh-navodneniyakh",
     "v-severnoy-chasti-brovarda-obyavleno-preduprezhdenie-o-vnezapnom-navodnenii"),
]


def merge_duplicates(apps, schema_editor):
    Article = apps.get_model("news", "Article")
    ArticleSource = apps.get_model("news", "ArticleSource")
    now = timezone.now()
    for keep_slug, dup_slug in DUPLICATES:
        keep = Article.objects.filter(slug=keep_slug).first()
        dup = Article.objects.filter(slug=dup_slug).first()
        if not keep or not dup or dup.status == "merged":
            continue
        known = set(ArticleSource.objects.filter(article=keep).values_list("url", flat=True))
        order = ArticleSource.objects.filter(article=keep).count()
        for src in ArticleSource.objects.filter(article=dup).order_by("order"):
            if src.url not in known:
                ArticleSource.objects.create(article=keep, source_id=src.source_id, name=src.name, url=src.url,
                                             title=src.title, order=order)
                known.add(src.url)
                order += 1
        keep.tags.add(*dup.tags.all())
        keep.revised_at = now
        keep.save(update_fields=["revised_at"])
        dup.status, dup.merged_into = "merged", keep
        dup.save(update_fields=["status", "merged_into"])


def backfill_urgent_expiry(apps, schema_editor):
    Article = apps.get_model("news", "Article")
    for article in Article.objects.filter(is_urgent=True, expires_at__isnull=True).exclude(published_at=None):
        article.expires_at = article.published_at + timedelta(hours=6)
        article.save(update_fields=["expires_at"])


def fix_toponyms(apps, schema_editor):
    Article = apps.get_model("news", "Article")
    for article in Article.objects.all():
        fields = {name: fix_text(getattr(article, name)) for name in ("title", "teaser", "body", "for_you")}
        if any(getattr(article, name) != value for name, value in fields.items()):
            for name, value in fields.items():
                setattr(article, name, value)
            article.save(update_fields=list(fields))  # slug не меняем: адреса остаются прежними


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0007_urgent_expiry_merged"),
    ]

    operations = [
        migrations.RunPython(merge_duplicates, migrations.RunPython.noop),
        migrations.RunPython(backfill_urgent_expiry, migrations.RunPython.noop),
        migrations.RunPython(fix_toponyms, migrations.RunPython.noop),
    ]
