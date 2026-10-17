"""Запуск конвейера из API в фоне: проход длится минуты, а HTTP-запрос — секунды."""

import logging
import threading
from datetime import timedelta

from django.db import close_old_connections
from django.utils import timezone

from pipeline.models import PipelineRun
from pipeline.services import run_pipeline

log = logging.getLogger(__name__)

# Незавершённый запуск старше этого срока считаем зависшим и не мешающим новому.
STALE_AFTER = timedelta(minutes=30)


class AlreadyRunning(Exception):
    def __init__(self, run):
        self.run = run


def active_run():
    since = timezone.now() - STALE_AFTER
    return PipelineRun.objects.filter(finished_at__isnull=True, started_at__gte=since).first()


def start_pipeline(*, fetch: bool, write: bool) -> PipelineRun:
    if run := active_run():
        raise AlreadyRunning(run)
    run = PipelineRun.objects.create(stats={"source": "api"})
    threading.Thread(target=_worker, args=(run.pk, fetch, write), daemon=True).start()
    return run


def _worker(run_pk: int, fetch: bool, write: bool):
    try:
        run_pipeline(fetch=fetch, write=write, run=PipelineRun.objects.get(pk=run_pk))
    except Exception:  # noqa: BLE001 — run_pipeline сам пишет сбой в журнал запуска
        log.exception("Фоновый запуск конвейера упал")
    finally:
        close_old_connections()
