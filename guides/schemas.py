from pydantic import BaseModel, Field


class GuideDraft(BaseModel):
    title: str = Field(description="Заголовок гайда по-русски, до 90 знаков")
    teaser: str = Field(description="Анонс в одну-две строки, до 250 знаков")
    body: str = Field(description="Текст гайда: абзацы через пустую строку, подзаголовки — строки с «## »")
    used_urls: list[str] = Field(description="Ссылки из списка фактов, на которые опирается текст")


class GuideCheck(BaseModel):
    ok: bool = Field(description="true, если в гайде нет утверждений, которых нет в фактах")
    issues: list[str] = Field(description="Конкретные проблемы на русском; пустой список, если всё в порядке")
