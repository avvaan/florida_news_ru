"""Обёртка над Anthropic API: структурированные ответы, prompt caching и учёт стоимости."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TypeVar

import anthropic
from django.conf import settings
from pydantic import BaseModel

from .models import AICall

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MILLION = Decimal(1_000_000)


class AIError(RuntimeError):
    pass


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  cache_read: int = 0, cache_write: int = 0) -> Decimal:
    price_in, price_out = settings.AI_PRICING.get(model, (Decimal("3.00"), Decimal("15.00")))
    cost = (
        Decimal(input_tokens) * price_in
        + Decimal(cache_write) * price_in * Decimal("1.25")
        + Decimal(cache_read) * price_in * Decimal("0.1")
        + Decimal(output_tokens) * price_out
    ) / MILLION
    return cost.quantize(Decimal("0.000001"))


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise AIError("ANTHROPIC_API_KEY не задан")
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=3, timeout=120)
    return _client


# Модели, которые принимают output_config.effort.
_EFFORT_UNSUPPORTED_PREFIXES = ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-3")


def ask(*, purpose: str, model: str, system: str, user: str, output: type[T],
        max_tokens: int = 2000, story=None, effort: str | None = None) -> T:
    """Один запрос со структурированным ответом. Каждый вызов логируется в AICall.

    Системный промпт помечен cache_control: при повторных вызовах в течение 5 минут
    он читается из кэша (если длиннее минимального порога модели).
    """
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
        response = get_client().messages.parse(**kwargs)
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
    call.cost_usd = estimate_cost(
        model, call.input_tokens, call.output_tokens, call.cache_read_tokens, call.cache_write_tokens
    )
    call.request_id = getattr(response, "_request_id", "") or ""

    if response.stop_reason == "refusal":
        call.success = False
        call.error = "Модель отказалась отвечать (refusal)"
    elif response.stop_reason == "max_tokens":
        call.success = False
        call.error = "Ответ обрезан по max_tokens"
    parsed = response.parsed_output
    if parsed is None and call.success:
        call.success = False
        call.error = "Не удалось разобрать структурированный ответ"
    call.save()
    if not call.success:
        raise AIError(call.error)
    return parsed
