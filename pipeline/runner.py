"""Фоновые задачи из API и админки: проход конвейера или подбор обложек длится минуты, а HTTP-запрос — секунды."""

import logging
import subprocess
import sys
import threading
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from news.models import Article

from .models import PipelineRun
from .services import rechoose_covers, run_pipeline

log = logging.getLogger(__name__)

# Незавершённый запуск старше этого срока считаем зависшим и не мешающим новому.
# Обычный проход идёт 5–20 минут, но с большим хвостом переводов бывает и 1,5–2 часа.
STALE_AFTER = timedelta(hours=2)


class AlreadyRunning(Exception):
    def __init__(self, run):
        self.run = run


def active_run():
    since = timezone.now() - STALE_AFTER
    return PipelineRun.objects.filter(finished_at__isnull=True, started_at__gte=since).first()


def _start(stats: dict, job) -> PipelineRun:
    if run := active_run():
        raise AlreadyRunning(run)
    run = PipelineRun.objects.create(stats=stats)
    threading.Thread(target=_worker, args=(run.pk, job), daemon=True).start()
    return run


def _worker(run_pk: int, job):
    try:
        job(PipelineRun.objects.get(pk=run_pk))
    except Exception:  # noqa: BLE001 — задача сама пишет сбой в журнал запуска
        log.exception("Фоновая задача упала")
    finally:
        close_old_connections()


def start_pipeline(*, fetch: bool, write: bool, source: str = "api") -> PipelineRun:
    return _start({"source": source}, lambda run: run_pipeline(fetch=fetch, write=write, run=run))


def spawn_pipeline(*, write: bool = True, source: str = "admin") -> PipelineRun:
    """Проход конвейера отдельным процессом `manage.py run_pipeline`, как из cron.

    Поток внутри gunicorn не годится для кнопки в админке: воркер перезапускается
    (--max-requests) и уносит с собой незаконченный проход. Отдельный процесс живёт сам;
    запись запуска создаётся здесь же, чтобы второе нажатие сразу видело «уже работает».
    """
    if run := active_run():
        raise AlreadyRunning(run)
    run = PipelineRun.objects.create(stats={"source": source, "write": write})
    cmd = [sys.executable, "manage.py", "run_pipeline", "--run-id", str(run.pk)]
    if not write:
        cmd.append("--no-write")
    try:
        proc = subprocess.Popen(  # noqa: S603 — команда целиком наша, без ввода пользователя
            cmd, cwd=settings.BASE_DIR, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as exc:
        run.finished_at, run.success = timezone.now(), False
        run.log = f"Не удалось запустить процесс: {exc}"
        run.save(update_fields=["finished_at", "success", "log"])
        raise
    # Забираем код выхода, чтобы не копились зомби-процессы.
    threading.Thread(target=proc.wait, daemon=True).start()
    return run


def start_covers(article_ids: list[int], *, source: str = "api") -> PipelineRun:
    """Подбор обложек ИИ для заметок по списку id, в том же порядке."""
    def job(run):
        by_id = Article.objects.select_related("topic", "story").in_bulk(article_ids)
        rechoose_covers([by_id[pk] for pk in article_ids if pk in by_id], run=run)
    return _start({"source": source, "task": "covers", "articles": len(article_ids)}, job)
