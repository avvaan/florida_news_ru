import json

from django.db import migrations, models


def mark_manual_covers(apps, schema_editor):
    """Отмечаем обложки, выбранные людьми: у заметок без сюжета (созданы в админке или через API)
    и у тех, где обложку меняли в админке. Остальные выбрал ИИ — их можно перевыбирать."""
    Article = apps.get_model("news", "Article")
    LogEntry = apps.get_model("admin", "LogEntry")
    picked = Article.objects.exclude(cover_image="")
    ids = set(picked.filter(story__isnull=True).values_list("pk", flat=True))
    entries = LogEntry.objects.filter(content_type__app_label="news",
                                      content_type__model__in=["article", "reviewarticle"])
    for object_id, message in entries.values_list("object_id", "change_message"):
        try:
            changes = json.loads(message or "[]")
        except ValueError:
            continue
        fields = [f for change in changes if isinstance(change, dict)
                  for f in (change.get("changed") or {}).get("fields", [])]
        if "обложка" in fields and str(object_id).isdigit():
            ids.add(int(object_id))
    picked.filter(pk__in=ids).update(cover_manual=True)


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0011_safety_short_name"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="cover_manual",
            field=models.BooleanField(
                default=False, verbose_name="обложка выбрана вручную",
                help_text="Ставится сам, когда обложку меняют в админке или через API. Такую обложку не меняют "
                          "ни при публикации, ни при замене повторов (pick_covers --fix-repeats)",
            ),
        ),
        migrations.RunPython(mark_manual_covers, migrations.RunPython.noop),
    ]
