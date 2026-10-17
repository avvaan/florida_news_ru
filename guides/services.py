import logging

from django.utils import timezone

from pipeline.telegram import post_guide

from .models import Guide

log = logging.getLogger(__name__)


def publish_guide(guide: Guide) -> str:
    """Публикация — только вручную, редактором. Отдельный пост в Telegram, если он включён."""
    guide.status = Guide.Status.PUBLISHED
    guide.published_at = guide.published_at or timezone.now()
    guide.save(update_fields=["status", "published_at", "updated_at"])
    try:
        return post_guide(guide)
    except Exception as exc:  # noqa: BLE001 — сбой Telegram не отменяет публикацию на сайте
        log.warning("Telegram для гайда «%s»: %s", guide.title, exc)
        return f"ошибка Telegram — {exc}"


def unpublish_guide(guide: Guide) -> None:
    guide.status = Guide.Status.DRAFT
    guide.save(update_fields=["status", "updated_at"])
