"""ИИ-перевод контента на украинский: заполняет поля <поле>_uk у моделей Translatable (см. core/i18n.py).

Что переводим — TARGETS: рубрики и регионы целиком, из остального — только то, что видно на сайте.
Короткие записи идут пачками (одна модель — один запрос на 20 записей), длинные — по одной.
Перевод считается актуальным, пока uk_hash совпадает с хешем русских полей; поправили оригинал —
запись переведётся заново при следующем проходе.

Длинные поля (гайды) переводятся кусками по абзацам, чтобы ответ модели не обрезался.

Запуск: run_pipeline (после новых заметок) и команда `python manage.py translate_content`.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from django.conf import settings
from django.db import models
from pydantic import BaseModel, Field, create_model

from .i18n import Translatable

log = logging.getLogger(__name__)

BATCH_SIZE = 20
BATCH_CHARS = 8_000        # пачка коротких записей — не больше стольких знаков оригинала
SINGLE_MAX_TOKENS = 16_000
CHUNK_CHARS = 3_000       # поле длиннее — переводится кусками по абзацам
# На длинных кусках модель иногда зацикливается и упирается в max_tokens; такой кусок делим пополам.
SPLIT_DEPTH = 3

SYSTEM = """Ты — редактор-переводчик русскоязычного новостного сайта TutFlorida о жизни во Флориде (США).
Переводишь материалы сайта с русского на украинский для украиноязычной версии сайта.

Правила:
- Современная литературная украинская мова, без суржика и калек с русского; тон и стиль оригинала, новостной язык.
- Смысл, факты, цифры, суммы, даты, время, адреса, телефоны, ссылки — без изменений. Ничего не добавляй и не сокращай.
- Сохраняй разметку один в один: пустые строки между абзацами, «## » и «### » в начале строк, списки «- » и «1. »,
  врезки «> », таблицы «| … |», **жирный**, [текст](ссылка), [[img:2|подпись]] (подпись переведи), HTML-теги.
- Английские названия (законы, ведомства, программы, компании, улицы) оставляй как в оригинале; русские названия
  американских мест пиши по-украински: Майами → Маямі, Джексонвилл → Джексонвілл, Южная Флорида → Південна Флорида,
  Тампа, Орландо, Флорида — без изменений. Кавычки — «ялинки», как в оригинале.
- Если текст говорит о языке самого сайта («по-русски», «на русском»), в переводе пиши «українською».
  Факты о других (русскоязычная община, бизнес говорит по-русски) переводи точно: «російськомовна громада», «російською».
- Пустое поле оставляй пустым.
"""


@dataclass
class Target:
    model: type[Translatable]
    queryset: Callable[[], models.QuerySet]
    note: str = ""  # подсказка переводчику о том, что это за записи


def _targets() -> list[Target]:
    from core.models import Author, Page
    from classifieds.models import Category as AdCategory
    from directory.models import Category, Listing
    from events.models import Event
    from guides.models import Guide
    from news.models import Article, Region, Tag, Topic

    return [
        Target(Region, lambda: Region.objects.all(),
               "регионы Флориды: name — название, name_locative — «где?» для заголовков (в Майами → у Маямі)"),
        Target(Topic, lambda: Topic.objects.all(), "рубрики новостей: name, short_name — короткое для меню"),
        Target(AdCategory, lambda: AdCategory.objects.all(),
               "рубрики доски объявлений; price_label — подпись к цене («Цена», «Зарплата», «Аренда»)"),
        Target(Category, lambda: Category.objects.all(), "разделы справочника бизнесов и полезных ссылок"),
        Target(Page, lambda: Page.objects.all(), "служебные страницы сайта; body может содержать простой HTML"),
        Target(Author, lambda: Author.objects.filter(is_active=True), "автор: role — должность, bio — о себе"),
        Target(Article, lambda: Article.objects.published().order_by("-published_at"),
               "новостные заметки: title — заголовок (до 120 знаков), teaser — анонс, body — текст, "
               "for_you — пункты «что это значит для вас», по одному на строку"),
        Target(Event, lambda: Event.objects.upcoming(), "афиша событий: title, description, price — цена («Бесплатно», «$20»)"),
        Target(Guide, lambda: Guide.objects.published(),
               "гайды для приезжих во Флориду в облегчённом Markdown: title, teaser — анонс, body — текст"),
        Target(Listing, lambda: Listing.objects.active(),
               "справочник бизнесов: description — описание, hours — часы работы, languages — языки обслуживания"),
        Target(Tag, lambda: Tag.objects.filter(article__status="published").distinct(), "теги заметок"),
    ]


def _label(model) -> str:
    return model._meta.label_lower


def pending(model_labels: list[str] | None = None) -> list[tuple[Target, list[Translatable]]]:
    """Записи без перевода или с устаревшим переводом, по моделям в порядке TARGETS."""
    result = []
    for target in _targets():
        if model_labels and _label(target.model) not in model_labels and target.model.__name__.lower() not in model_labels:
            continue
        todo = [obj for obj in target.queryset() if obj.uk_outdated and any(getattr(obj, f) for f in obj.TRANSLATED)]
        if todo:
            result.append((target, todo))
    return result


def _schema(model: type[Translatable], *, batch: bool) -> type[BaseModel]:
    fields = {name: (str, Field(default="")) for name in model.TRANSLATED}
    item = create_model(f"{model.__name__}Uk", id=(int, ...), **fields)
    if not batch:
        return item
    return create_model(f"{model.__name__}UkBatch", items=(list[item], ...))


def _payload(obj: Translatable) -> dict:
    return {"id": obj.pk, **{name: getattr(obj, name) or "" for name in obj.TRANSLATED}}


def _length(obj: Translatable) -> int:
    return sum(len(str(getattr(obj, name) or "")) for name in obj.TRANSLATED)


def _batches(objs: list[Translatable]):
    batch, size = [], 0
    for obj in objs:
        n = _length(obj)
        if batch and (len(batch) >= BATCH_SIZE or size + n > BATCH_CHARS):
            yield batch
            batch, size = [], 0
        batch.append(obj)
        size += n
    if batch:
        yield batch


def _limit(model: type[Translatable], name: str) -> int | None:
    return getattr(model._meta.get_field(f"{name}_uk"), "max_length", None)


def _apply(obj: Translatable, data: dict) -> bool:
    """Записывает перевод; False — если ИИ вернул пустой перевод непустого поля."""
    for name in obj.TRANSLATED:
        source, value = getattr(obj, name) or "", (data.get(name) or "").strip()
        if source.strip() and not value:
            return False
        if (limit := _limit(type(obj), name)) and len(value) > limit:
            value = value[:limit].rstrip()
        setattr(obj, f"{name}_uk", value)
    obj.uk_hash = obj.source_hash()
    obj.save(update_fields=[*(f"{n}_uk" for n in obj.TRANSLATED), "uk_hash"])
    return True


def _ask(model: type[Translatable], payload, note: str, out_chars: int, *, fields=None, many=False):
    import json

    from pipeline.ai import ask
    from pipeline.models import AICall

    hint = f"Записи: {note}.\n" if note else ""
    shape = '{"items": [{"id": …, поля…}, …]}' if many else '{"id": …, поля…}'
    user = (hint + f"Переведи на украинский поля каждой записи, id не меняй. Ответ — JSON {shape}.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=1))
    schema = _schema(model, batch=many) if fields is None else create_model(
        f"{model.__name__}UkPart", id=(int, ...), **{n: (str, Field(default="")) for n in fields})
    return ask(purpose=AICall.Purpose.TRANSLATE, model=settings.AI_TRANSLATOR_MODEL, system=SYSTEM, user=user,
               output=schema, max_tokens=min(SINGLE_MAX_TOKENS, max(1500, int(out_chars * 1.2))))


def _chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Длинный текст — кусками по абзацам, по возможности с границей на подзаголовке «## »."""
    parts, current = [], []
    for para in text.replace("\r\n", "\n").split("\n\n"):
        length = sum(len(p) + 2 for p in current)
        if current and (length + len(para) > size or (para.startswith("## ") and length > size // 2)):
            parts.append("\n\n".join(current))
            current = []
        current.append(para)
    if current:
        parts.append("\n\n".join(current))
    return parts


def _translate_long(target: Target, obj: Translatable) -> dict:
    """Запись с длинным полем (гайд, большая заметка): короткие поля одним запросом, длинные — кусками."""
    short = [n for n in obj.TRANSLATED if len(str(getattr(obj, n) or "")) <= CHUNK_CHARS]
    data = {}
    if short:
        payload = {"id": obj.pk, **{n: getattr(obj, n) or "" for n in short}}
        data.update(_ask(target.model, payload, target.note, sum(len(v) for v in map(str, payload.values())),
                         fields=short).model_dump())
    for name in obj.TRANSLATED:
        if name in short:
            continue
        pieces = [_translate_piece(target, obj, name, piece) for piece in _chunks(getattr(obj, name))]
        data[name] = "\n\n".join(pieces)
    return data


def _translate_piece(target: Target, obj: Translatable, name: str, piece: str, depth: int = 0) -> str:
    """Один кусок длинного поля. Ответ обрезан (модель зациклилась) — делим кусок по абзацам пополам."""
    from pipeline.ai import AIError

    try:
        result = _ask(target.model, {"id": obj.pk, name: piece}, target.note, len(piece), fields=[name])
        return getattr(result, name).strip()
    except AIError as exc:
        split = _halves(piece)
        if "обрезан" not in str(exc) or depth >= SPLIT_DEPTH or split is None:
            raise
        (first, second), sep = split
        log.info("Перевод %s #%s: кусок %s знаков обрезан, делю пополам", _label(target.model), obj.pk, len(piece))
        return sep.join(_translate_piece(target, obj, name, half, depth + 1) for half in (first, second))


def _halves(text: str) -> tuple[tuple[str, str], str] | None:
    """Делит текст примерно пополам: по абзацам, иначе по строкам, иначе по предложениям."""
    import re

    for parts, sep in ((text.split("\n\n"), "\n\n"), (text.split("\n"), "\n"),
                       (re.split(r"(?<=[.!?…])\s+", text), " ")):
        if len(parts) < 2:
            continue
        acc = 0
        for i, part in enumerate(parts[:-1]):
            acc += len(part) + len(sep)
            if acc >= len(text) / 2:
                break
        return (sep.join(parts[: i + 1]), sep.join(parts[i + 1:])), sep
    return None


def translate_objects(target: Target, objs: list[Translatable]) -> int:
    """Переводит записи одной модели; возвращает число переведённых."""
    done = 0
    long_ = [o for o in objs if any(len(str(getattr(o, n) or "")) > CHUNK_CHARS for n in o.TRANSLATED)]
    for obj in long_:
        done += _apply(obj, _translate_long(target, obj))
    for batch in _batches([o for o in objs if o not in long_]):
        many = len(batch) > 1
        source = [_payload(o) for o in batch]
        result = _ask(target.model, source if many else source[0], target.note, sum(map(_length, batch)), many=many)
        by_id = {o.pk: o for o in batch}
        for item in (result.items if many else [result]):
            if (obj := by_id.get(item.id)) and _apply(obj, item.model_dump()):
                done += 1
    return done


def spent_today() -> Decimal:
    from pipeline.models import AICall

    return AICall.objects.today().filter(purpose=AICall.Purpose.TRANSLATE).total_cost()


def translate_pending(say=print, *, models_: list[str] | None = None, limit: int | None = None,
                      budget: Decimal | None = None) -> int:
    """Проход по всему, что ждёт перевода. Останавливается по limit записей или дневному бюджету на перевод."""
    from pipeline.ai import AIError

    budget = Decimal(settings.AI_TRANSLATE_BUDGET_PER_DAY) if budget is None else budget
    total = 0
    for target, objs in pending(models_):
        if limit is not None:
            objs = objs[: max(0, limit - total)]
        if not objs:
            break
        if spent_today() >= budget:
            say(f"Перевод: дневной бюджет ${budget} исчерпан, продолжу в следующий раз")
            break
        for chunk in _batches(objs):
            if spent_today() >= budget:
                break
            try:
                total += translate_objects(target, chunk)
            except AIError as exc:
                say(f"Перевод {target.model._meta.verbose_name_plural}: сбой — {exc}")
                log.warning("Сбой перевода %s: %s", _label(target.model), exc)
    say(f"Перевод на украинский: переведено записей {total}, потрачено сегодня ${spent_today()}")
    return total


def spawn_translation(*, models_: tuple[str, ...] = ("article",), limit: int = 20) -> bool:
    """Перевести только что опубликованное в фоне, отдельным процессом `manage.py translate_content`.

    Конвейер переводит в конце своего прохода, а заметку, опубликованную руками из админки или API,
    читатели /uk/ увидели бы по-русски до следующего прохода. Перевод идёт от новых к старым, так что
    свежая заметка попадает в первые `limit`. Сбой запуска не мешает публикации — подхватит конвейер.
    """
    cmd = [sys.executable, "manage.py", "translate_content", "--limit", str(limit)]
    for name in models_:
        cmd += ["--model", name]
    try:
        proc = subprocess.Popen(  # noqa: S603 — команда целиком наша
            cmd, cwd=settings.BASE_DIR, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as exc:
        log.warning("Не удалось запустить фоновый перевод: %s", exc)
        return False
    import threading

    threading.Thread(target=proc.wait, daemon=True).start()  # не копим зомби-процессы
    return True
