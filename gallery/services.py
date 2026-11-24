"""Как фото и видео попадают в медиатеку: файл, ссылка на файл или ссылка на видеоплощадку.

Добавляет только сотрудник (API с ключом или админка), поэтому ИИ-модерации здесь нет —
в отличие от картинок из публичных форм (core/images.py).
"""

from __future__ import annotations

import io
import ipaddress
import logging
import mimetypes
import re
import socket
import uuid
from urllib.parse import parse_qs, urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from core import images
from core.text import make_slug

from .models import MediaItem

log = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 100 * 1024 * 1024  # Cloudflare (бесплатный тариф) не пропускает запрос больше 100 МБ
PHOTO_SIDE = 2000  # так храним: хватает и для обложки 1200 px, и для ретины
VIDEO_TYPES = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov", "video/ogg": "ogv"}
VIDEO_EXT = {"mp4", "m4v", "webm", "mov", "ogv"}


class MediaError(ValueError):
    pass


# --- видеоплощадки -------------------------------------------------------------------------------

_YT_ID = re.compile(r"^[\w-]{11}$")


def parse_video_link(url: str) -> dict | None:
    """Ссылка YouTube / Vimeo / Rutube / VK → данные для плеера. None — это не видеоплощадка."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path = parsed.path.rstrip("/")
    query = parse_qs(parsed.query)

    if host in {"youtube.com", "youtube-nocookie.com", "youtu.be", "music.youtube.com"}:
        video_id = ""
        if host == "youtu.be":
            video_id = path.lstrip("/").split("/")[0]
        elif path == "/watch":
            video_id = (query.get("v") or [""])[0]
        else:
            parts = path.split("/")
            if len(parts) >= 3 and parts[1] in {"embed", "shorts", "live", "v"}:
                video_id = parts[2]
        if _YT_ID.match(video_id or ""):
            return {"provider": "youtube", "embed_url": f"https://www.youtube-nocookie.com/embed/{video_id}",
                    "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}
    if host in {"vimeo.com", "player.vimeo.com"}:
        digits = [p for p in path.split("/") if p.isdigit()]
        if digits:
            return {"provider": "vimeo", "embed_url": f"https://player.vimeo.com/video/{digits[0]}",
                    "thumbnail_url": ""}
    if host == "rutube.ru":
        match = re.search(r"/(?:video|play/embed|shorts)/([0-9a-f]{32})", path)
        if match:
            return {"provider": "rutube", "embed_url": f"https://rutube.ru/play/embed/{match.group(1)}",
                    "thumbnail_url": ""}
    if host in {"vk.com", "vkvideo.ru", "vk.ru"}:
        match = re.search(r"video(-?\d+)_(\d+)", url)
        if match:
            oid, vid = match.groups()
            return {"provider": "vk", "embed_url": f"https://vk.com/video_ext.php?oid={oid}&id={vid}&hd=2",
                    "thumbnail_url": ""}
    return None


# --- загрузка по ссылке ---------------------------------------------------------------------------

def _check_public_host(url: str) -> None:
    """Скачиваем только из интернета: не даём ходить на внутренние адреса сервера."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise MediaError("Нужна ссылка http(s)://")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise MediaError(f"Не найден сайт {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise MediaError("Ссылка ведёт на внутренний адрес — так нельзя")


def download(url: str, limit: int) -> tuple[bytes, str]:
    """Скачивает файл по ссылке. Возвращает (данные, content-type)."""
    _check_public_host(url)
    try:
        with requests.get(url, stream=True, timeout=(10, 40), allow_redirects=True,
                          headers={"User-Agent": settings.FETCH_USER_AGENT if hasattr(settings, "FETCH_USER_AGENT")
                                   else "FloridaRU/1.0"}) as response:
            response.raise_for_status()
            _check_public_host(response.url)
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > limit:
                raise MediaError(f"Файл больше {limit // (1024 * 1024)} МБ")
            chunks, total = [], 0
            for chunk in response.iter_content(64 * 1024):
                total += len(chunk)
                if total > limit:
                    raise MediaError(f"Файл больше {limit // (1024 * 1024)} МБ")
                chunks.append(chunk)
            ctype = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            return b"".join(chunks), ctype
    except requests.RequestException as exc:
        raise MediaError(f"Не удалось скачать: {type(exc).__name__}: {exc}"[:300]) from exc


# --- хранение -------------------------------------------------------------------------------------

def _store(data: bytes, filename: str, folder: str, mime: str) -> tuple[str, str, str, str]:
    """Кладёт файл в ImageKit или на диск. Возвращает (url, storage, file_id, path)."""
    if images.storage_available():
        try:
            response = requests.post(
                images.UPLOAD_URL, auth=(settings.IMAGEKIT_PRIVATE_KEY, ""), timeout=120,
                files={"file": (filename, data, mime)},
                data={"fileName": filename, "folder": f"{settings.IMAGEKIT_FOLDER}/{folder}",
                      "useUniqueFileName": "true"},
            )
            response.raise_for_status()
            body = response.json()
            return body["url"], MediaItem.Storage.IMAGEKIT, body["fileId"], ""
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise MediaError(f"ImageKit: {type(exc).__name__}: {exc}"[:500]) from exc
    path = default_storage.save(f"{folder}/{timezone.now():%Y/%m}/{filename}", ContentFile(data))
    return f"{settings.SITE_URL}{settings.MEDIA_URL}{path}", MediaItem.Storage.LOCAL, "", path


def _filename(meta: dict, ext: str) -> str:
    base = make_slug(meta.get("title") or meta.get("caption") or "", max_length=50) or "media"
    return f"{base}-{uuid.uuid4().hex[:8]}.{ext}"


def _meta(meta: dict) -> dict:
    return {key: (meta.get(key) or "")[:limit] for key, limit in
            (("title", 200), ("caption", 300), ("credit", 200), ("alt", 300))}


# --- точки входа ----------------------------------------------------------------------------------

def add_photo_bytes(data: bytes, meta: dict | None = None, source_url: str = "") -> MediaItem:
    meta = meta or {}
    if len(data) > MAX_PHOTO_BYTES:
        raise MediaError("Фото больше 20 МБ")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > images.MAX_PIXELS:
            raise MediaError("Слишком большое разрешение фото")
        img = ImageOps.exif_transpose(img)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise MediaError("Это не картинка (подойдут JPG, PNG, WebP, GIF)") from exc
    jpeg = images.to_jpeg(img, PHOTO_SIDE, quality=86)
    width, height = Image.open(io.BytesIO(jpeg)).size
    url, storage, file_id, path = _store(jpeg, _filename(meta, "jpg"), "media/photo", "image/jpeg")
    return MediaItem.objects.create(
        kind=MediaItem.Kind.PHOTO, url=url, storage=storage, file_id=file_id, path=path, source_url=source_url,
        width=width, height=height, size=len(jpeg), mime="image/jpeg", **_meta(meta),
    )


def add_video_bytes(data: bytes, mime: str, meta: dict | None = None, filename: str = "") -> MediaItem:
    meta = meta or {}
    if len(data) > MAX_VIDEO_BYTES:
        raise MediaError("Видео больше 100 МБ — загрузите его на YouTube и пришлите ссылку")
    ext = VIDEO_TYPES.get(mime) or (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
    if ext not in VIDEO_EXT:
        raise MediaError("Видео принимается в mp4, webm или mov")
    mime = mime if mime in VIDEO_TYPES else (mimetypes.guess_type(f"x.{ext}")[0] or "video/mp4")
    url, storage, file_id, path = _store(data, _filename(meta, ext), "media/video", mime)
    thumb = f"{url}/ik-thumbnail.jpg" if storage == MediaItem.Storage.IMAGEKIT else ""
    return MediaItem.objects.create(
        kind=MediaItem.Kind.VIDEO, url=url, storage=storage, file_id=file_id, path=path, thumbnail_url=thumb,
        size=len(data), mime=mime, **_meta(meta),
    )


def add_upload(upload, meta: dict | None = None) -> MediaItem:
    """Файл из multipart-запроса: фото или видео по типу файла."""
    mime = (getattr(upload, "content_type", "") or "").lower()
    name = getattr(upload, "name", "") or ""
    is_video = mime.startswith("video/") or name.rsplit(".", 1)[-1].lower() in VIDEO_EXT
    limit = MAX_VIDEO_BYTES if is_video else MAX_PHOTO_BYTES
    if upload.size > limit:
        raise MediaError(f"Файл больше {limit // (1024 * 1024)} МБ")
    upload.seek(0)
    data = upload.read()
    if is_video:
        return add_video_bytes(data, mime, meta, filename=name)
    return add_photo_bytes(data, meta)


def add_url(url: str, meta: dict | None = None, kind: str = "") -> MediaItem:
    """Ссылка: видеоплощадка → плеер; картинка → скачиваем и храним у себя; видеофайл → у себя или ссылкой."""
    meta = meta or {}
    url = url.strip()
    link = parse_video_link(url)
    if link:
        if kind == MediaItem.Kind.PHOTO:
            raise MediaError("Это ссылка на видео, а просили фото")
        return MediaItem.objects.create(kind=MediaItem.Kind.VIDEO, url=url, storage=MediaItem.Storage.EXTERNAL,
                                        source_url=url, **link, **_meta(meta))
    ext = urlparse(url).path.rsplit(".", 1)[-1].lower() if "." in urlparse(url).path else ""
    if kind == MediaItem.Kind.VIDEO or ext in VIDEO_EXT:
        mime = mimetypes.guess_type(f"x.{ext}")[0] or "video/mp4"
        if images.storage_available():
            data, ctype = download(url, MAX_VIDEO_BYTES)
            item = add_video_bytes(data, ctype if ctype.startswith("video/") else mime, meta, filename=f"x.{ext}")
            item.source_url = url[:1000]
            item.save(update_fields=["source_url"])
            return item
        # Без хранилища большой файл на диск не тянем: играем по прямой ссылке.
        _check_public_host(url)
        return MediaItem.objects.create(kind=MediaItem.Kind.VIDEO, url=url, storage=MediaItem.Storage.EXTERNAL,
                                        source_url=url, mime=mime, **_meta(meta))
    data, ctype = download(url, MAX_PHOTO_BYTES)
    if ctype.startswith("video/"):
        item = add_video_bytes(data, ctype, meta, filename=f"x.{VIDEO_TYPES.get(ctype, 'mp4')}")
        item.source_url = url[:1000]
        item.save(update_fields=["source_url"])
        return item
    return add_photo_bytes(data, meta, source_url=url[:1000])


def delete_file(item: MediaItem) -> None:
    """Удаляет сам файл из хранилища (запись удаляет вызывающий)."""
    if item.storage == MediaItem.Storage.IMAGEKIT:
        images.delete(item.file_id)
    elif item.storage == MediaItem.Storage.LOCAL and item.path:
        try:
            default_storage.delete(item.path)
        except OSError:
            log.warning("Медиатека: не удалось удалить файл %s", item.path)
