"""Схемы ответов ИИ для разбора сигналов."""

from pydantic import BaseModel, Field

from pipeline.schemas import RegionSlug, TopicSlug


class SignalVerdict(BaseModel):
    id: int = Field(description="id сигнала из списка")
    interesting: bool = Field(description="true, если это новость, важная нашим читателям; реклама, мнения, "
                                          "шутки, спорт, повторы — false")
    story_id: int | None = Field(description="id сюжета из списка, если сигнал о том же событии, иначе null")
    hint_id: int | None = Field(description="id открытой подсказки, если сигнал о той же теме, иначе null")
    group: str | None = Field(description="для новой темы: короткий латинский ключ, одинаковый у сигналов "
                                          "об одном событии; иначе null")
    region: RegionSlug
    topic: TopicSlug


class NewHint(BaseModel):
    group: str = Field(description="ключ из поля group сигналов")
    title: str = Field(description="тема по-русски в одну строку, до 100 знаков")
    summary: str = Field(description="2–3 предложения по-русски своими словами: что обсуждают. Без цитат, "
                                     "без имён частных лиц, без утверждений как о доказанном факте")


class Triage(BaseModel):
    signals: list[SignalVerdict]
    new_hints: list[NewHint]


class HintMatch(BaseModel):
    hint_id: int
    story_id: int | None = Field(description="id сюжета об этом же событии или null")


class HintMatches(BaseModel):
    matches: list[HintMatch]
