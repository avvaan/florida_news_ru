"""Обёртка над ИИ-провайдером: структурированные ответы, кэш промптов и учёт стоимости.

Провайдер выбирается настройкой AI_PROVIDER:
- "deepseek" (по умолчанию): OpenAI-совместимый API DeepSeek, режим JSON-ответа;
  кэш префикса промпта у DeepSeek автоматический.
- "anthropic": Anthropic API со structured outputs и cache_control.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import TypeVar

from django.conf import settings
from pydantic import BaseModel, ValidationError

from .models import AICall

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MILLION = Decimal(1_000_000)
# Если модели нет в таблице цен, считаем по заведомо высокой цене, чтобы лимит бюджета не занижался.
FALLBACK_PRICE = {"input": "3.00", "output": "15.00", "cache_read": "0.30", "cache_write": "3.75"}


class AIError(RuntimeError):
    pass


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  cache_read: int = 0, cache_write: int = 0) -> Decimal:
    """Стоимость вызова в долларах. input_tokens — токены входа без попаданий в кэш."""
    price = settings.AI_PRICING.get(model)
    if price is None:
        log.warning("Нет цены для модели %s — считаю по запасной", model)
        price = FALLBACK_PRICE
    cost = (
        Decimal(input_tokens) * Decimal(price["input"])
        + Decimal(cache_read) * Decimal(price.get("cache_read", price["input"]))
        + Decimal(cache_write) * Decimal(price.get("cache_write", price["input"]))
        + Decimal(output_tokens) * Decimal(price["output"])
    ) / MILLION + Decimal(price.get("request", "0"))
    return cost.quantize(Decimal("0.000001"))


# --- Клиенты -----------------------------------------------------------------

_clients: dict[str, object] = {}


def get_client(provider: str | None = None):
    provider = provider or settings.AI_PROVIDER
    if provider not in _clients:
        if provider == "deepseek":
            import openai

            if not settings.DEEPSEEK_API_KEY:
                raise AIError("DEEPSEEK_API_KEY не задан")
            _clients[provider] = openai.OpenAI(
                api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL,
                max_retries=3, timeout=180,
            )
        elif provider == "anthropic":
            import anthropic

            if not settings.ANTHROPIC_API_KEY:
                raise AIError("ANTHROPIC_API_KEY не задан")
            _clients[provider] = anthropic.Anthropic(
                api_key=settings.ANTHROPIC_API_KEY, max_retries=3, timeout=120,
            )
        else:
            raise AIError(f"Неизвестный AI_PROVIDER: {provider}")
    return _clients[provider]


def ask(*, purpose: str, model: str, system: str, user: str, output: type[T],
        max_tokens: int = 2000, story=None, effort: str | None = None, provider: str | None = None) -> T:
    """Один запрос со структурированным ответом. Каждый вызов логируется в AICall.

    provider — провайдер для этого вызова (по умолчанию AI_PROVIDER): так проверка дублей идёт
    в Claude Haiku, даже если основной конвейер работает на DeepSeek.
    """
    if (provider or settings.AI_PROVIDER) == "anthropic":
        return _ask_anthropic(purpose=purpose, model=model, system=system, user=user, output=output,
                              max_tokens=max_tokens, story=story, effort=effort)
    return _ask_deepseek(purpose=purpose, model=model, system=system, user=user, output=output,
                         max_tokens=max_tokens, story=story)


def _finish(call: AICall, parsed, raise_error: bool = True):
    """Считает стоимость, сохраняет лог вызова и возвращает разобранный ответ."""
    call.cost_usd = estimate_cost(
        call.model, call.input_tokens, call.output_tokens, call.cache_read_tokens, call.cache_write_tokens
    )
    if parsed is None and call.success:
        call.success = False
        call.error = "Не удалось разобрать структурированный ответ"
    call.save()
    if not call.success and raise_error:
        raise AIError(call.error)
    return parsed


# --- DeepSeek ----------------------------------------------------------------

def json_instruction(output: type[BaseModel]) -> str:
    schema = json.dumps(output.model_json_schema(), ensure_ascii=False)
    return (
        "\n\nФормат ответа: только один JSON-объект строго по этой JSON-схеме, "
        f"без пояснений и без markdown.\nJSON-схема: {schema}"
    )


def _ask_deepseek(*, purpose, model, system, user, output, max_tokens, story):
    # Схема дописывается в конец системного промпта: префикс промпта не меняется
    # между вызовами одной задачи, и DeepSeek берёт его из кэша (дешевле в ~10 раз).
    messages = [
        {"role": "system", "content": system + json_instruction(output)},
        {"role": "user", "content": user},
    ]
    # Один повтор, если модель вернула пустой или битый JSON (у DeepSeek такое бывает).
    call, parsed, retryable = _deepseek_once(purpose, model, messages, output, max_tokens, story)
    if not call.success and retryable:
        _finish(call, None, raise_error=False)
        log.info("Повтор запроса к DeepSeek после ошибки: %s", call.error)
        call, parsed, _ = _deepseek_once(purpose, model, messages, output, max_tokens, story)
    return _finish(call, parsed)


def _deepseek_once(purpose, model, messages, output, max_tokens, story):
    """Возвращает (AICall, parsed | None, можно ли повторить)."""
    import openai

    call = AICall(purpose=purpose, model=model, story=story)
    try:
        response = get_client("deepseek").chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
    except openai.APIError as exc:
        call.success = False
        call.error = f"{type(exc).__name__}: {exc}"[:2000]
        call.save()
        raise AIError(call.error) from exc

    usage = response.usage
    hit = getattr(usage, "prompt_cache_hit_tokens", None) or 0
    miss = getattr(usage, "prompt_cache_miss_tokens", None)
    call.input_tokens = miss if miss is not None else max((usage.prompt_tokens or 0) - hit, 0)
    call.cache_read_tokens = hit
    call.output_tokens = usage.completion_tokens or 0
    call.request_id = getattr(response, "id", "") or ""

    choice = response.choices[0]
    if choice.finish_reason == "length":
        call.success, call.error = False, "Ответ обрезан по max_tokens"
        return call, None, False
    if choice.finish_reason == "content_filter":
        call.success, call.error = False, "Ответ заблокирован фильтром содержимого"
        return call, None, False
    try:
        return call, output.model_validate_json((choice.message.content or "").strip()), False
    except ValidationError as exc:
        call.success, call.error = False, f"Некорректный JSON: {exc.errors()[:2]}"[:2000]
        return call, None, True


# --- Anthropic ---------------------------------------------------------------

# Модели Anthropic, которые не принимают output_config.effort.
_EFFORT_UNSUPPORTED_PREFIXES = ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-3")


def _ask_anthropic(*, purpose, model, system, user, output, max_tokens, story, effort):
    import anthropic

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_format=output,
    )
    if effort and not model.startswith(_EFFORT_UNSUPPORTED_PREFIXES):
        kwargs["output_config"] = {"effort": effort}

    call = AICall(purpose=purpose, model=model, story=story)
    try:
        response = get_client("anthropic").messages.parse(**kwargs)
    except anthropic.APIError as exc:
        call.success = False
        call.error = f"{type(exc).__name__}: {exc}"[:2000]
        call.save()
        raise AIError(call.error) from exc

    usage = response.usage
    call.input_tokens = usage.input_tokens or 0
    call.output_tokens = usage.output_tokens or 0
    call.cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0
    call.cache_write_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0
    call.request_id = getattr(response, "_request_id", "") or ""
    if response.stop_reason == "refusal":
        call.success = False
        call.error = "Модель отказалась отвечать (refusal)"
    elif response.stop_reason == "max_tokens":
        call.success = False
        call.error = "Ответ обрезан по max_tokens"
    return _finish(call, response.parsed_output)
