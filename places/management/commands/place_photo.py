"""Картинка для статьи «Что посетить»: исходник (файл или https-ссылка) → три файла в static/places/.

    python manage.py place_photo everglades 3 ~/photo.jpg --stock-id 6593219 --title "Kayaking in Everglades"

Кадрирует под 16:9 (--focus-y / --focus-x — где центр кадра, 0…1), сохраняет <slug>-<N>.webp 1200×675 и
<slug>-<N>-640.webp (у обложки ещё <slug>-1.jpg для соцсетей) и записывает авторство в
places/content/photos/<slug>.json.
"""

import io
import json
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageOps

from places import importer

SIZE = (1200, 675)
SMALL = (640, 360)


def crop_16x9(img: Image.Image, focus_x: float, focus_y: float) -> Image.Image:
    width, height = img.size
    target = SIZE[0] / SIZE[1]
    if width / height > target:  # шире 16:9 — режем по бокам
        new_w = round(height * target)
        left = min(max(round(focus_x * width - new_w / 2), 0), width - new_w)
        return img.crop((left, 0, left + new_w, height))
    new_h = round(width / target)
    top = min(max(round(focus_y * height - new_h / 2), 0), height - new_h)
    return img.crop((0, top, width, top + new_h))


class Command(BaseCommand):
    help = "Готовит картинку статьи «Что посетить»: 16:9, webp 1200 и 640, jpg 1200, запись об авторстве"

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("number", type=int, help="1 — обложка, 2, 3 … — картинки в тексте")
        parser.add_argument("source", help="путь к файлу или https-ссылка")
        parser.add_argument("--credit", default="Freepik", help="чьё фото (подпись «Фото: …»)")
        parser.add_argument("--stock-id", type=int, help="номер фото на стоке")
        parser.add_argument("--title", default="", help="название фото на стоке")
        parser.add_argument("--source-url", default="", help="страница фото (для фото не со стока: NPS, NASA …)")
        parser.add_argument("--focus-x", type=float, default=0.5)
        parser.add_argument("--focus-y", type=float, default=0.5)

    def handle(self, slug, number, source, credit, stock_id, title, source_url, focus_x, focus_y, **options):
        if number < 1:
            raise CommandError("номер картинки — с 1")
        if source.startswith("https://"):
            response = requests.get(source, timeout=120)
            response.raise_for_status()
            data = io.BytesIO(response.content)
        else:
            path = Path(source).expanduser()
            if not path.exists():
                raise CommandError(f"нет файла {path}")
            data = path.open("rb")
        with Image.open(data) as raw:
            raw.draft("RGB", (SIZE[0] * 2, SIZE[1] * 2))
            img = ImageOps.exif_transpose(raw).convert("RGB")
        if img.width < SIZE[0] or img.height < SIZE[1] * 0.9:
            self.stderr.write(self.style.WARNING(f"исходник маленький ({img.width}×{img.height}) — будет мыльно"))
        img = crop_16x9(img, focus_x, focus_y)
        big = img.resize(SIZE, Image.LANCZOS)
        small = img.resize(SMALL, Image.LANCZOS)
        out = Path(settings.BASE_DIR) / "static" / "places"
        out.mkdir(parents=True, exist_ok=True)
        base = out / f"{slug}-{number}"
        files = [Path(f"{base}.webp"), Path(f"{base}-640.webp")]
        big.save(files[0], "WEBP", quality=74, method=6)
        small.save(files[1], "WEBP", quality=74, method=6)
        if number == 1:  # JPEG нужен только обложке: og:image и превью в мессенджерах
            files.append(Path(f"{base}.jpg"))
            big.save(files[2], "JPEG", quality=80, optimize=True, progressive=True)

        photos_file = importer.photos_path(slug)
        photos_file.parent.mkdir(parents=True, exist_ok=True)
        photos = importer.load_photos(slug)
        photos[str(number)] = {"credit": credit, "stock_id": stock_id, "title": title}
        if source_url:
            photos[str(number)]["source_url"] = source_url
        photos = dict(sorted(photos.items(), key=lambda kv: int(kv[0])))
        photos_file.write_text(json.dumps(photos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sizes = ", ".join(f"{p.name} {p.stat().st_size // 1024} КБ" for p in files)
        self.stdout.write(self.style.SUCCESS(f"✓ {sizes}"))
