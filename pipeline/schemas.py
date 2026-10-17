"""Схемы структурированных ответов ИИ."""

from typing import Literal

from pydantic import BaseModel, Field

TopicSlug = Literal[
    "weather", "safety", "roads", "laws", "money", "housing", "events", "incidents", "education", "health", "other"
]
RegionSlug = Literal["miami", "orlando", "tampa", "jacksonville", "florida", "outside"]


class Classification(BaseModel):
    score: int = Field(description="Важность для русскоязычных жителей Флориды, 0–10")
    topic: TopicSlug
    region: RegionSlug
    is_urgent: bool = Field(description="Ураган, эвакуация, прямая опасность для жизни или имущества")
    is_sensitive: bool = Field(description="Криминал, имена частных лиц, дети, обвинения, суды")
    reason: str = Field(description="Одна короткая фраза: почему такая оценка")


class Draft(BaseModel):
    title: str = Field(description="Заголовок на русском, до 80 знаков")
    teaser: str = Field(description="Одна строка-анонс для Telegram, до 200 знаков")
    body: str = Field(description="Текст заметки 80–150 слов, абзацы через пустую строку")
    tags: list[str] = Field(description="2–4 коротких тега на русском")
    insufficient_facts: bool = Field(
        description="true, если по данным источников нельзя написать заметку без домыслов"
    )
    cover: str = Field(description="id обложки из списка «Обложки на выбор», лучше всего подходящей по смыслу")


class Verification(BaseModel):
    ok: bool = Field(description="true, если заметка не противоречит источникам и ничего не выдумано")
    confidence: float = Field(description="Уверенность 0.0–1.0")
    issues: list[str] = Field(description="Конкретные проблемы: выдуманные факты, искажённые цифры, обвинения без ссылки на полицию")
