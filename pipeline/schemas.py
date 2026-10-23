"""Схемы структурированных ответов ИИ."""

from typing import Literal

from pydantic import BaseModel, Field

TopicSlug = Literal[
    "weather", "safety", "roads", "laws", "money", "housing", "events", "incidents", "education", "health",
    "business", "other",
]
BusinessKind = Literal["stocks", "deals", "other"]
RegionSlug = Literal["miami", "orlando", "tampa", "jacksonville", "florida", "outside"]


class Classification(BaseModel):
    score: int = Field(description="Важность для русскоязычных жителей Флориды, 0–10")
    topic: TopicSlug
    region: RegionSlug
    is_urgent: bool = Field(description="Ураган, эвакуация, прямая опасность для жизни или имущества")
    is_sensitive: bool = Field(description="Криминал, имена частных лиц, дети, обвинения, суды")
    reason: str = Field(description="Одна короткая фраза: почему такая оценка")
    business_kind: BusinessKind | None = Field(
        default=None,
        description="Только для topic=business: stocks — акции компании на бирже, deals — сделка, other — другое",
    )
    same_as_article_id: int | None = Field(
        default=None,
        description="id заметки из списка «Уже опубликовано», если сюжет о том же событии и не приносит "
                    "существенно новых фактов; иначе null",
    )


class Draft(BaseModel):
    title: str = Field(description="Заголовок на русском, до 80 знаков")
    teaser: str = Field(description="Одна строка-анонс для Telegram, до 200 знаков")
    body: str = Field(description="Текст заметки 80–150 слов, абзацы через пустую строку")
    tags: list[str] = Field(description="2–4 коротких тега на русском")
    insufficient_facts: bool = Field(
        description="true, если по данным источников нельзя написать заметку без домыслов"
    )
    cover: str = Field(description="id обложки из списка «Обложки на выбор», лучше всего подходящей по смыслу")
    for_you: list[str] = Field(
        default_factory=list,
        description="«Что это значит для вас»: 0–4 коротких пункта, что новость меняет для читателя. "
                    "Пустой список, если практического смысла нет",
    )
    guide: str = Field(default="", description="slug гайда из списка «Гайды», если он по теме заметки, иначе пусто")


class Verification(BaseModel):
    ok: bool = Field(description="true, если заметка не противоречит источникам и ничего не выдумано")
    confidence: float = Field(description="Уверенность 0.0–1.0")
    issues: list[str] = Field(description="Конкретные проблемы: выдуманные факты, искажённые цифры, обвинения без ссылки на полицию")
    source_conflicts: list[str] = Field(
        default_factory=list,
        description="Противоречия МЕЖДУ источниками: разное место, число пострадавших или погибших, имена, "
                    "даты, время, суммы. Каждое — одной строкой «что: источник А говорит X, источник Б — Y». "
                    "Пусто, если источник один или они согласны",
    )


class DuplicateCheck(BaseModel):
    same_story: bool = Field(description="true, если новая заметка о том же событии, что одна из опубликованных")
    article_id: int | None = Field(default=None, description="id той опубликованной заметки; null, если дубля нет")
    reason: str = Field(description="Одна короткая фраза: почему это то же событие или другое")
    new_facts: list[str] = Field(
        default_factory=list,
        description="Если это то же событие: существенно новые факты из новой заметки, которых нет в опубликованной "
                    "(0–3 коротких предложения на русском). Пусто, если нового нет",
    )


class CoverChoice(BaseModel):
    cover: str = Field(description="id обложки из списка «Обложки на выбор», лучше всего подходящей по смыслу")
