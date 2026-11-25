"""Кнопка «Запустить конвейер» в админке (Запуски конвейера) и защита от двойного прохода."""
import sys
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from pipeline.models import PipelineRun

URL = "/admin/pipeline/pipelinerun/run-now/"
pytestmark = pytest.mark.django_db


def test_changelist_shows_buttons(admin_client):
    resp = admin_client.get("/admin/pipeline/pipelinerun/")
    assert resp.status_code == 200
    assert "Запустить конвейер" in resp.content.decode()


def test_button_spawns_command_with_its_run(admin_client):
    with mock.patch("pipeline.runner.subprocess.Popen") as popen:
        resp = admin_client.post(URL, {"mode": "full"}, follow=True)
    assert resp.status_code == 200
    run = PipelineRun.objects.get()
    assert run.finished_at is None and run.stats["source"].startswith("admin:")
    cmd = popen.call_args.args[0]
    assert cmd[:3] == [sys.executable, "manage.py", "run_pipeline"]
    assert cmd[3:] == ["--run-id", str(run.pk)]
    assert "Конвейер запущен" in resp.content.decode()


def test_fetch_only_mode(admin_client):
    with mock.patch("pipeline.runner.subprocess.Popen") as popen:
        admin_client.post(URL, {"mode": "fetch"})
    assert popen.call_args.args[0][-1] == "--no-write"
    assert PipelineRun.objects.get().stats["write"] is False


def test_second_click_while_running_starts_nothing(admin_client):
    PipelineRun.objects.create()
    with mock.patch("pipeline.runner.subprocess.Popen") as popen:
        resp = admin_client.post(URL, {"mode": "full"}, follow=True)
    popen.assert_not_called()
    assert PipelineRun.objects.count() == 1
    assert "уже работает" in resp.content.decode()


def test_get_does_not_start(admin_client):
    with mock.patch("pipeline.runner.subprocess.Popen") as popen:
        admin_client.get(URL)
    popen.assert_not_called()


def test_staff_without_permission_cannot_start(client, django_user_model):
    user = django_user_model.objects.create_user("editor", password="x", is_staff=True)
    client.force_login(user)
    with mock.patch("pipeline.runner.subprocess.Popen") as popen:
        resp = client.post(URL, {"mode": "full"})
    assert resp.status_code == 403
    popen.assert_not_called()


def test_command_continues_given_run():
    run = PipelineRun.objects.create(stats={"source": "admin:x"})
    with mock.patch("pipeline.management.commands.run_pipeline.run_pipeline", return_value=run) as rp:
        call_command("run_pipeline", "--run-id", str(run.pk), "--no-write")
    assert rp.call_args.kwargs == {"fetch": True, "write": False, "run": run}


def test_cron_skips_while_another_run_is_active():
    PipelineRun.objects.create(started_at=timezone.now())
    with mock.patch("pipeline.management.commands.run_pipeline.run_pipeline") as rp:
        call_command("run_pipeline")
    rp.assert_not_called()
