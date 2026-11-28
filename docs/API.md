# API сайта — инструкция для агента

Этот файл можно целиком отдать ИИ-агенту как описание инструмента. Машиночитаемая схема
OpenAPI — `GET /api/schema/` (с тем же ключом), интерактивная документация — `/api/docs/`.

## Доступ

- Адрес: `https://<домен сайта>/api/v1/` (например `https://tutflorida.com/api/v1/`).
- Каждый запрос с заголовком `Authorization: Token <ключ>`.
- JSON: `Content-Type: application/json`. Загрузка файлов: `multipart/form-data`.
- Лимит: 3000 запросов в час на ключ (переменная `API_RATE_LIMIT`). Превышение — `429`.
- Ошибки: `400` — в ответе поле → текст ошибки; `401` — нет ключа; `403` — ключ не сотрудника;
  `404` — нет объекта; `409` — конвейер уже работает.
- Списки постраничные: `{"count", "next", "previous", "results"}`, по 50, `?page=2`.
- Удаление — `DELETE`, ответ `204`. Частичная правка — `PATCH` (только изменённые поля).
- Регионы: `miami`, `orlando`, `tampa`, `jacksonville`, `florida` (весь штат) — `GET /regions/`. Темы: `weather`, `safety`, `laws`, `housing`, `roads`, `money`, `education`, `health`, `events`, `incidents`, `business` — `GET /topics/`.

## Фото и видео (медиатека) — `/media/`

Всё, что показывается на сайте как фото или видео, сначала попадает в медиатеку. Можно в два
шага (добавить → подключить по `id`) или в один: у заметок, событий и бизнесов есть поля
`*_url` / `*_file`, которые добавляют в медиатеку сами.

| Действие | Запрос |
|---|---|
| Фото или видео файлом | `POST /media/` multipart: `file`, необязательно `title`, `caption`, `credit`, `alt` |
| По ссылке | `POST /media/` JSON `{"source": "https://…", "caption": "…", "credit": "Фото: …"}` |
| Список / поиск | `GET /media/?kind=photo&q=пляж` |
| Поправить подпись | `PATCH /media/{id}/` `{"caption": "…"}` |
| Удалить (и файл) | `DELETE /media/{id}/` |

- Ссылка на YouTube, Vimeo, Rutube или VK → видео со встроенным плеером (`embed_url`).
- Ссылка на картинку → скачиваем, сжимаем до 2000 px (JPEG) и храним у себя.
- Ссылка на mp4/webm/mov → видеофайл (с ImageKit — копия у нас, без него — играем по ссылке).
- Фото до 20 МБ (JPG/PNG/WebP/GIF), видео до 100 МБ. Большие видео лучше выкладывать на YouTube.
- Всегда указывайте `credit` (чьё фото) — это требование к чужим материалам.

## Новости — `/articles/`

| Действие | Запрос |
|---|---|
| Список | `GET /articles/?status=published&region=miami&topic=weather&q=ураган` |
| Создать | `POST /articles/` |
| Изменить | `PATCH /articles/{id}/` |
| Опубликовать (и в Telegram, если включён) | `POST /articles/{id}/publish/` |
| Снять / отклонить | `POST /articles/{id}/reject/` |
| Отправить в Telegram | `POST /articles/{id}/telegram/` |
| Удалить | `DELETE /articles/{id}/` |

Поля: `title` (до 120), `teaser` (анонс до 300), `body` (абзацы через пустую строку), `for_you`
(«Что это значит для вас», пункт на строку), `region`, `topic`, `tags` (список строк),
`sources` (`[{"name", "url", "title"}]`), `is_urgent`, `status` (`draft` по умолчанию, `published`
— сразу на сайте), `guide` (slug гайда).

Украинская версия (`/uk/…`): `title_uk`, `teaser_uk`, `body_uk`, `for_you_uk`. Не прислали — после
публикации переведёт ИИ. Прислали — показывается как есть, ИИ её не трогает, пока не поправят русский
текст (правите русский — присылайте и украинский, иначе ИИ переведёт заново). Пустые строки — перевод снова за ИИ.

Фото и видео заметки:
- `photo` — id фото (своё фото вместо иллюстрации: на странице, в ленте, в соцсетях); `null` — убрать.
- Фото внутри текста: отдельный абзац `[[photo:<id>|Подпись]]` в `body` (id из медиатеки, подпись необязательна —
  без неё берётся `caption` фото; под фото — подпись и `credit`). В `body_uk` — те же id, подпись по-украински.
- `photo_url` / `photo_file` + `photo_caption`, `photo_credit` — добавить фото одним запросом.
- `video` — id видео, или `video_url` (например ссылка YouTube) / `video_file`. Показывается под текстом.
- `gallery` — список id фото (заменяет галерею); `gallery_urls` — ссылки, добавляются в конец.
- Без своего фото у заметки обложка-иллюстрация рубрики: `cover_image` (список — `GET /covers/`).

Пример — новость с фото и видео сразу на сайт:

```json
POST /api/v1/articles/
{
  "title": "В Майами открылся новый пляжный парк",
  "teaser": "Парк на 8 гектаров с бесплатной парковкой открылся в субботу.",
  "body": "Первый абзац.\n\nВторой абзац.",
  "region": "miami", "topic": "events", "tags": ["Майами", "парки"],
  "sources": [{"name": "Miami Herald", "url": "https://…", "title": "…"}],
  "photo_url": "https://…/park.jpg", "photo_credit": "Фото: City of Miami",
  "video_url": "https://www.youtube.com/watch?v=…",
  "status": "published"
}
```

## Афиша — `/events/`

| Действие | Запрос |
|---|---|
| Список | `GET /events/?upcoming=1&region=orlando&date_from=2026-12-01&date_to=2026-12-31&q=концерт&language=uk` |
| Добавить (сразу на сайте) | `POST /events/` |
| Изменить | `PATCH /events/{id}/` |
| Опубликовать | `POST /events/{id}/approve/` |
| Снять | `POST /events/{id}/reject/` `{"reason": "…"}` |
| Проверить заявку ИИ | `POST /events/{id}/remoderate/` (только `pending`) |
| Удалить | `DELETE /events/{id}/` |

Поля: `title`, `description` (до 2000), `starts_on` (ГГГГ-ММ-ДД), `starts_at` (ЧЧ:ММ, можно
пусто), `ends_on` (для многодневных), `venue`, `address`, `city`, `region`, `price` («от $45»,
«бесплатно»), `url` (билеты), `organizer`. Картинка: `image_url` (ссылка — скачаем), `image_file`
(файл), `image` (id из медиатеки), `image_remove: true` — убрать. `status`: `approved` по умолчанию,
`pending` — отдать на проверку ИИ. Адрес страницы события — `page_url` в ответе.

`language` — для какой версии сайта событие: `""` (по умолчанию) — обе, `"ru"` — только русская,
`"uk"` — только украинская (`/uk/…`). На другой версии события нет ни в афише, ни в sitemap, его
страница отдаёт 404. Событие для одной версии пишите сразу на её языке в обычные поля `title`,
`description`, `price` — ИИ его не переводит. Публикуйте сразу (`approved`): проверка ИИ (`pending`)
переписывает описание по-русски. Фильтр списка: `?language=uk` / `ru` / `all` (для обеих версий).

```json
{"title": "Різдвяний ярмарок", "description": "Громада запрошує на різдвяний ярмарок…",
 "starts_on": "2026-12-13", "starts_at": "11:00", "venue": "Парафіяльна зала", "city": "Орландо",
 "region": "orlando", "price": "Вхід вільний", "language": "uk"}
```

## Справочник

| Что | Запрос |
|---|---|
| Разделы (категории) | `GET/POST /directory/categories/`, `PATCH/DELETE /directory/categories/{slug}/` |
| Записи (бизнесы и ссылки) | `GET/POST /directory/listings/`, `PATCH/DELETE /directory/listings/{id}/` |
| Заявки бизнесов с сайта | `GET /directory/submissions/?status=pending` |
| Одобрить / отклонить заявку | `POST /directory/submissions/{id}/approve/` `{"category": "…", "region": "…"}`, `…/reject/` |

Раздел: `name`, `kind` (`business` — бизнесы, `links` — полезные ссылки), `description`, `slug`
(латиница; если не указать — из названия), `schema_type` (`Dentist`, `Restaurant`, …), `order`.
Запись: `category` (slug), `name`, `description`, `url`, `phone`, `address`, `city`, `region`,
`languages`, `hours`, `is_recommended`, `is_partner` (платное размещение — обязательно `true`),
`is_active`, `order`, `editor_note` (видно только редакции). Фото: `photo` (id) / `photo_url` /
`photo_file`. Фильтры: `?category=…&kind=business&city=…&q=…&active=1`.

## Гайды — `/guides/`

`GET/POST /guides/`, `PATCH/DELETE /guides/{slug}/`. Поля: `title`, `slug`, `teaser`, `body`
(разметка: `## Заголовок`, абзацы, списки «- », ссылки `[текст](url)`), `section`
(`docs`, `car`, `housing`, `hurricanes`, `money`, `health`, `kids`, `everyday`), `order`, `topics`
(slug тем), `sources` (`[{"name", "url", "title"}]`). Публикация: сначала
`PATCH {"human_reviewed": true}` (факты сверены), затем `POST /guides/{slug}/publish/`;
снять — `POST /guides/{slug}/unpublish/`.

## Объявления — `/classifieds/`

| Что | Запрос |
|---|---|
| Рубрикатор | `GET/POST /classifieds/categories/`, `PATCH/DELETE /classifieds/categories/{slug}/` |
| Объявления | `GET/POST /classifieds/ads/`, `PATCH/DELETE /classifieds/ads/{id}/` |
| Снять / вернуть / продлить | `POST /classifieds/ads/{id}/close/`, `…/restore/`, `…/renew/` |
| Отклонить (фото удаляются) | `POST /classifieds/ads/{id}/reject/` |
| Удалить одно фото | `DELETE /classifieds/ads/{id}/photos/{photo_id}/` |

Объявление: `category` (slug рубрики, не раздела), `title`, `description`, `price` (целое, $),
`price_unit` (`""`, `month`, `week`, `day`, `hour`), `city`, `zip_code`, `contact_name`, `phone`
(`+13055551234`), `has_whatsapp`, `telegram`. Фото: `add_photos` (id из медиатеки) или
`add_photo_urls` (ссылки), до 5. От API объявление сразу публикуется на 30 дней.
Фильтры: `?status=…&category=…&active=1&q=…`.

## Комментарии и отзывы — `/comments/`

`GET /comments/?status=pending&article=12&listing=5&reported=1`. Ответ от редакции:
`POST /comments/` `{"article": 12, "text": "…"}` (или `"listing": 5`; автор «Редакция»).
Опубликовать — `POST /comments/{id}/publish/`, скрыть — `POST /comments/{id}/hide/`,
правка — `PATCH`, удалить — `DELETE`.

## Остальное

| Что | Запрос |
|---|---|
| Сводка по всему сайту | `GET /stats/` |
| Теги | `GET/POST /tags/`, `PATCH/DELETE /tags/{slug}/` |
| Страницы «О проекте», «Контакты», … | `GET/POST /pages/`, `PATCH /pages/{slug}/` |
| Авторы и редакторы | `GET/POST /authors/`, `PATCH/DELETE /authors/{slug}/` (фото — multipart `photo`) |
| Реклама (баннеры) | `GET/POST /ads/`, `PATCH/DELETE /ads/{id}/` (картинка — multipart `image`, в multipart передавайте и `is_active=true`); `language`: `""` — обе версии, `ru` / `uk` — только одна; фильтр `?language=uk` |
| Источники новостей | `/sources/`, `POST /sources/{id}/check/?activate=1`, `…/fetch/`, `…/reset/` |
| Источники соцсигналов | `/signal-sources/`, `POST /signal-sources/{id}/reset/` |
| Подсказки из соцсетей | `GET /hints/?status=open`, `PATCH /hints/{id}/` `{"status": "dismissed"}` |
| Погодные предупреждения | `GET /alerts/`, `PATCH /alerts/{id}/` `{"is_hidden": true}` |
| Настройки сайта | `GET/PATCH /settings/` |
| Материал справа от главной темы | `PATCH /settings/` `{"featured_article": <id заметки>, "featured_until": "2026-12-05T23:59:00-05:00"}` (`null` — убрать) |
| Запустить сбор новостей сейчас | `POST /pipeline/run/` `{"fetch": true, "write": true}`, ход — `GET /pipeline/{id}/` |
| Обложки-иллюстрации | `GET /covers/`; ИИ подберёт: `POST /articles/{id}/pick-cover/` |

## Правила для агента

1. Перед созданием проверьте дубль: `GET /articles/?q=…`, `GET /events/?q=…`, `GET /directory/listings/?q=…`.
2. Новости пишите своими словами, со ссылкой на первоисточник в `sources`.
3. У чужих фото и видео всегда указывайте `credit`; не берите фото с водяными знаками фотостоков.
4. Платное размещение в справочнике — только с `is_partner: true`.
5. После изменения откройте `page_url` / `url` из ответа, чтобы убедиться, что всё на сайте.
