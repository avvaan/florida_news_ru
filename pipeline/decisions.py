"""Решение «опубликовать сразу или отправить на проверку»."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

PUBLISH = "publish"
REVIEW = "review"


@dataclass
class Decision:
    action: str
    reason: str

    @property
    def publish(self) -> bool:
        return self.action == PUBLISH


def decide(*, score: int, is_urgent: bool, is_sensitive: bool, has_official_source: bool,
           verified_ok: bool, verifier_confidence: float, issues: list[str],
           insufficient_facts: bool, auto_publish_enabled: bool, auto_publish_min_score: int,
           min_confidence: Decimal | float, publish_without_review: bool = False,
           has_trusted_source: bool = True) -> Decision:
    # Правило сильнее любых настроек: без записи от СМИ или официального источника не публикуем
    # (одного поста из соцсетей недостаточно).
    if not has_trusted_source:
        return Decision(REVIEW, "Нет подтверждения от СМИ или официального источника")
    decision = _decide(
        score=score, is_urgent=is_urgent, is_sensitive=is_sensitive, has_official_source=has_official_source,
        verified_ok=verified_ok, verifier_confidence=verifier_confidence, issues=issues,
        insufficient_facts=insufficient_facts, auto_publish_enabled=auto_publish_enabled,
        auto_publish_min_score=auto_publish_min_score, min_confidence=min_confidence,
    )
    if publish_without_review and not decision.publish:
        return Decision(PUBLISH, f"Опубликовано без проверки. Обычно ушло бы в очередь: {decision.reason}")
    return decision


def _decide(*, score, is_urgent, is_sensitive, has_official_source, verified_ok, verifier_confidence,
            issues, insufficient_facts, auto_publish_enabled, auto_publish_min_score, min_confidence) -> Decision:
    if is_sensitive:
        return Decision(REVIEW, "Чувствительная тема (криминал, частные лица, дети или обвинения)")
    if insufficient_facts:
        return Decision(REVIEW, "Автор сообщил, что фактов в источниках мало")
    if not verified_ok or issues:
        details = "; ".join(issues[:3]) or "проверка не подтвердила заметку"
        return Decision(REVIEW, f"Проверка сомневается: {details}")
    if verifier_confidence < float(min_confidence):
        return Decision(REVIEW, f"Низкая уверенность проверки ({verifier_confidence:.2f})")
    if not auto_publish_enabled:
        return Decision(REVIEW, "Автопубликация выключена в настройках")
    if is_urgent and has_official_source:
        return Decision(PUBLISH, "Срочно, официальный источник, проверка пройдена")
    if score >= auto_publish_min_score:
        return Decision(PUBLISH, f"Важность {score} ≥ {auto_publish_min_score}, проверка пройдена")
    return Decision(REVIEW, f"Важность {score} ниже порога автопубликации ({auto_publish_min_score})")
