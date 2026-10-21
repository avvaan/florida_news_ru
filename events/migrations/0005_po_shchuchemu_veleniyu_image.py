"""«По щучьему велению» (Musical Traditions, 19.12.2026): картинка с афиши организатора и цена целиком.

Событие пришло через форму без картинки, а цена обрезалась на 80 знаках. Картинка — кадр с афиши
организатора в Canva, лежит в static/events/. Если события нет (локальная база, тесты) — ничего не делаем.
"""

from django.db import migrations

SLUG = "po-shchuchemu-veleniyu-muzykalnyy-novogodniy-spektakl-dlya-vsey-semi-2026-12-19"


def update_event(apps, schema_editor):
    apps.get_model("events", "Event").objects.filter(slug=SLUG).update(
        price="Детский билет $35, взрослый $25, подарок $20; есть семейные пакеты",
        image_url="https://florida-ru.com/static/events/po-shchuchemu-veleniyu.jpg",
        image_status="published", image_note="Кадр с афиши организатора, добавила редакция",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0004_russian_events_2026_2027"),
    ]

    operations = [migrations.RunPython(update_event, migrations.RunPython.noop)]
