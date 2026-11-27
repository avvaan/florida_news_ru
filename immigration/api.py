"""API для сотрудников (ключ сотрудника, как весь /api/): запуск обновления базы знаний и её состояние.

    POST /api/v1/immigration/update/   — запустить `manage.py immigration_update` отдельным процессом (202);
                                          повторно, пока идёт прошлый запуск (до 30 минут), — 409
    GET  /api/v1/immigration/sources/  — источники: состояние, фрагменты, когда проверены, ошибки + итоги

Отдельный процесс, а не поток gunicorn: воркер перезапускается (--max-requests) и унёс бы незаконченное
обновление. Журнал конвейера новостей не используется — иначе плановый прогон новостей счёл бы, что занят.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

from django.conf import settings
from django.db.models import Count
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Chunk, Source

LOCK = Path("/tmp/immigration_update.lock")
LOCK_TTL = 30 * 60


def running() -> bool:
    return LOCK.exists() and time.time() - LOCK.stat().st_mtime < LOCK_TTL


class UpdateView(APIView):
    def post(self, request):
        if running():
            return Response({"detail": "Обновление базы уже идёт"}, status=status.HTTP_409_CONFLICT)
        LOCK.write_text(str(time.time()))
        log = Path("/tmp/immigration_update.log")
        with log.open("w") as out:
            proc = subprocess.Popen(  # noqa: S603 — команда целиком наша, без ввода пользователя
                [sys.executable, "manage.py", "immigration_update"], cwd=settings.BASE_DIR,
                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
            )

        def finish(p=proc):
            p.wait()
            LOCK.unlink(missing_ok=True)

        threading.Thread(target=finish, daemon=True).start()
        return Response({"detail": "Обновление базы запущено", "status_url": "/api/v1/immigration/sources/"},
                        status=status.HTTP_202_ACCEPTED)


class SourcesView(APIView):
    def get(self, request):
        rows = Source.objects.annotate(n=Count("chunks")).order_by("agency", "url")
        data = [{"url": s.url, "title": s.title, "agency": s.agency, "status": s.status, "active": s.is_active,
                 "chunks": s.n, "checked_at": s.checked_at, "changed_at": s.changed_at, "error": s.last_error}
                for s in rows]
        tail = ""
        log = Path("/tmp/immigration_update.log")
        if log.exists():
            tail = "\n".join(log.read_text(errors="ignore").splitlines()[-5:])
        return Response({
            "running": running(),
            "sources_ok": sum(1 for r in data if r["status"] == Source.Status.OK and r["active"]),
            "sources_failed": sum(1 for r in data if r["status"] != Source.Status.OK),
            "chunks": Chunk.objects.filter(source__is_active=True).count(),
            "last_run_tail": tail,
            "sources": data,
        })
