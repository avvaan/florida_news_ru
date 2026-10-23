"""Прод-хранилище статики не роняет страницу, если файла нет в манифесте (окно выкладки на Render)."""

import json

from core.storage import ForgivingManifestStorage


def test_missing_manifest_entry_falls_back_to_plain_url(tmp_path):
    (tmp_path / "staticfiles.json").write_text(json.dumps({
        "version": "1.1", "paths": {"covers/weather.webp": "covers/weather.abc123.webp"}, "hash": "x",
    }))
    storage = ForgivingManifestStorage(location=str(tmp_path), base_url="/static/")
    assert storage.url("covers/weather.webp") == "/static/covers/weather.abc123.webp"
    assert storage.url("covers/business-640.webp") == "/static/covers/business-640.webp"  # раньше — ValueError → 500
