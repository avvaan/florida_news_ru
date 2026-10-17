# Флорида Сегодня — новости Флориды по-русски

Сайт и Telegram-канал с короткими новостями Флориды на русском для русско- и украиноязычных
жителей Майами, Орландо, Тампы и Джексонвилла. Дважды в день, утром и вечером, система сама собирает новости
из местных СМИ и официальных источников, отбирает важное, пишет **собственную** заметку на 80–150
слов со ссылкой на первоисточник, проверяет её и публикует на сайте и в Telegram.

Стек: Python 3.12, Django 5, PostgreSQL (локально — SQLite), серверные шаблоны и чистый CSS,
ИИ DeepSeek (Anthropic можно включить настройкой), Telegram Bot API. Без Celery: фоновые задачи — management-команды по расписанию.

---

## Как это работает

```
дважды в день (7:07 и 18:07 по Флориде): python manage.py run_pipeline
 1. Сбор        fetch_sources: RSS/Atom + NWS alerts API. ETag/Last-Modified, robots.txt,
                честный User-Agent. Храним только заголовок, ссылку, дату и короткое описание.
 2. Склейка     одна история из разных СМИ → один «сюжет» (похожесть заголовков, окно 48 ч).
 3. Отбор       DeepSeek Flash: важность 0–10, тема, регион, «срочно», «чувствительно».
 4. Написание   DeepSeek Pro: заметка 80–150 слов, заголовок до 80 знаков, анонс для Telegram, теги.
 5. Проверка    DeepSeek Flash сверяет заметку с данными источников.
 6. Публикация  по умолчанию ВСЁ написанное публикуется сразу (настройка «публиковать всё
                без проверки»). Если её выключить: авто — срочное от официальных источников
                и заметки с важностью ≥ порога и чистой проверкой; чувствительное и
                сомнительное — в «На проверку».
                Сайт + пост в Telegram (🚨 для срочного).
 7. Лимиты      «заметок в день» и «$ на ИИ в день»: при превышении пишем только срочное.
                Каждый вызов ИИ логируется с токенами и стоимостью.
```

Решение «авто или на проверку» — в `pipeline/decisions.py`, всё остальное — в `pipeline/services.py`.

### Структура проекта

| Папка | Что внутри |
|---|---|
| `config/` | настройки, URL |
| `core/` | настройки сайта (пороги, лимиты, Telegram), статические страницы, стартовые данные (`seed.py`) |
| `sources/` | источники (`Source`), записи фидов, погодные предупреждения, сбор (`fetch.py`) |
| `news/` | регионы, темы, сюжеты, заметки, страницы сайта, sitemap, JSON-LD |
| `pipeline/` | ИИ (`ai.py`, `prompts.py`, `schemas.py`), склейка, лимиты, решения, Telegram, конвейер |
| `ads/` | рекламные блоки |
| `templates/`, `static/` | шаблоны, CSS, шрифты, иллюстрации рубрик |
| `tests/` | pytest, фикстуры фидов, всё без сети |

### Команды

| Команда | Что делает |
|---|---|
| `python manage.py run_pipeline` | полный проход (это и ставим в расписание) |
| `python manage.py run_pipeline --no-write` | только сбор и склейка, без ИИ |
| `python manage.py run_pipeline --no-fetch` | обработать уже собранное, без сети |
| `python manage.py fetch_sources` | только сбор (можно `--source ID`) |
| `python manage.py pick_covers` | ИИ подбирает обложки старым заметкам по тексту (опубликованным без выбранной обложки; `--all`, `--topic weather`, `--limit 50`, `--ids 12 15`) |
| `python manage.py check_ai` (`--ping`) | проверить ключ DeepSeek и названия моделей (с `--ping` — тестовый запрос) |
| `python manage.py check_sources --activate` | проверить все фиды, включить рабочие, выключить нерабочие |
| `python manage.py seed_demo` / `--clear` | демо-заметки для просмотра дизайна (только `DJANGO_DEBUG=1`) |

---

## ⚠️ Источники: что проверено, а что нет

В промпте требовалось проверить каждый фид. **Из среды разработки это сделать не удалось:**
сеть песочницы закрыта для новостных сайтов (прокси отвечает 403), поэтому ни один адрес не
открылся. Я не стал выдавать непроверенные адреса за рабочие:

- В базу добавлены **18 кандидатов** (`core/seed.py`): NHC (2 фида), NWS alerts API, Florida Politics,
  Florida Phoenix, ClickOrlando, WESH 2, WFTV 9, FOX 35, Orlando Sentinel, Tampa Bay Times, FOX 13,
  WFLA 8, WPLG Local 10, NBC 6, WSVN 7, News4JAX, First Coast News. Адреса взяты по типовым шаблонам
  платформ этих СМИ (Arc XP, WordPress, Hearst, TEGNA, Fox).
- **Все они созданы выключенными** (`is_active=False`, «фид проверен» снят).
- Первым делом после деплоя запустите:
  ```bash
  python manage.py check_sources --activate
  ```
  Команда откроет каждый адрес, включит те, что реально отдают RSS/Atom (или GeoJSON для NWS),
  а у остальных запишет причину ошибки. Нерабочий адрес можно поправить в админке
  (Источники → адрес фида) и проверить действием «Проверить фид».
- **Нет кандидатов** (адрес не нашёлся, добавьте вручную, если появится фид): Miami Herald,
  Bay News 9, flgov.com (пресс-релизы губернатора), FLHSMV, Florida Department of Revenue, FDEM.
  У многих госсайтов нет RSS — тогда их новости придут через СМИ.

Если фид падает 3 раза подряд, источник помечается «сломан» и пропускается, общий сбор не падает.
Снять отметку — действие «Сбросить ошибки» в админке.

---

## Запуск локально

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # впишите DEEPSEEK_API_KEY (остальное можно оставить)
python manage.py check_ai       # ключ рабочий? модели из настроек существуют?
python manage.py migrate        # создаст регионы, темы, страницы и источники-кандидаты
python manage.py createsuperuser
python manage.py runserver      # http://localhost:8000, админка — /admin/
```

Посмотреть дизайн с контентом, без ИИ и без сети:

```bash
DEMO_MODE=1 python manage.py seed_demo && DEMO_MODE=1 python manage.py runserver
# убрать демо: python manage.py seed_demo --clear
```

Тесты (без сети, ИИ и Telegram замоканы):

```bash
pytest          # 52 теста: фиды, склейка, решения, Telegram, лимиты, конвейер, страницы, админка
```

---

## Работа редактора (≈10 минут в день)

Админка: `/admin/`.

0. По умолчанию включено **«публиковать всё без проверки»** (Настройки): заметки сразу идут на сайт и в
   Telegram, очередь не нужна. Если бы заметка в обычном режиме попала на проверку, причина видна
   в её карточке → «Проверка ИИ». Чтобы вернуть ручную проверку чувствительных тем — снимите галочку.
1. **📝 На проверку**: очередь заметок, которые не опубликовались сами (только при выключенной галочке). Для каждой видно,
   почему она здесь, вердикт проверки и исходные заголовки. Текст можно поправить. Внизу кнопки
   **«✅ Опубликовать»** и **«❌ Отклонить»**. В списке те же действия работают сразу для нескольких заметок.
2. **Заметки**: все заметки. Опубликованную можно поправить или снять.
3. **Источники**: включение/выключение, вес доверия, состояние («ок» / «не проверен» / «сломан»).
4. **Рекламные блоки**: картинка или текст, ссылка, место (под шапкой / сбоку / в ленте),
   город, даты показа.
5. **Настройки**: пороги (заметка — от 6, автопубликация — от 7), минимальная уверенность
   проверки, максимум заметок в день, бюджет на ИИ в день, Telegram, AdSense (по умолчанию выключен).
6. **Расходы на ИИ**: сумма за сегодня и месяц, разбивка по задачам, каждый вызов с токенами.
7. **Запуски конвейера**: журнал каждого прохода.

---

## API для удалённого управления

REST API на Django REST Framework. Всё, что есть в админке, доступно удалённо: из скрипта, Postman,
мобильного приложения или ИИ-агента.

- **Документация и «песочница»:** `https://ваш-домен/api/docs/` (Swagger, открывается после входа
  в админку или с токеном), схема OpenAPI — `/api/schema/`.
- **Доступ:** только сотрудники (`is_staff`). Создать ключ — в Shell на Render:
  ```bash
  python manage.py drf_create_token <логин>      # выведет ключ из 40 символов
  ```
  или в админке: «Токены» → «Добавить». Ключ передаётся в заголовке `Authorization: Token <ключ>`.
  Отозвать — удалить токен в админке. Лимит — 600 запросов в час.

| Что | Запрос |
|---|---|
| Сводка: заметки, расходы на ИИ, лимиты, источники, последний запуск | `GET /api/v1/stats/` |
| Заметки (фильтры `status`, `region`, `topic`, `urgent`, `q`) | `GET /api/v1/articles/` |
| Создать / изменить / удалить заметку | `POST /api/v1/articles/`, `PATCH`/`DELETE /api/v1/articles/{id}/` |
| Опубликовать / снять / отправить в Telegram | `POST /api/v1/articles/{id}/publish/`, `…/reject/`, `…/telegram/` |
| Сменить обложку вручную (`""` — по очереди из рубрики) | `PATCH /api/v1/articles/{id}/` с `{"cover_image": "covers/weather-2"}` |
| ИИ подбирает обложку одной заметке / пачке в фоне | `POST /api/v1/articles/{id}/pick-cover/`, `POST /api/v1/articles/pick-covers/` |
| Источники, проверка фида, сбор, сброс ошибок | `/api/v1/sources/`, `POST …/{id}/check/?activate=1`, `…/fetch/`, `…/reset/` |
| Настройки (пороги, лимиты, Telegram, автопубликация) | `GET`/`PATCH /api/v1/settings/` |
| Запустить конвейер сейчас (в фоне) и следить за ним | `POST /api/v1/pipeline/run/`, `GET /api/v1/pipeline/{id}/` |
| Реклама (картинка — multipart, поле `image`) | `/api/v1/ads/` |
| Страницы «О проекте», «Контакты», политика… | `/api/v1/pages/{slug}/` |
| Погодные предупреждения (скрыть — `is_hidden`) | `/api/v1/alerts/` |
| Обложки с описаниями, регионы, темы | `GET /api/v1/covers/`, `/api/v1/regions/`, `/api/v1/topics/` |

Примеры:

```bash
TOKEN=ваш_ключ; SITE=https://ваш-домен
# сводка
curl -H "Authorization: Token $TOKEN" $SITE/api/v1/stats/
# заметки на проверке
curl -H "Authorization: Token $TOKEN" "$SITE/api/v1/articles/?status=review"
# поправить заголовок и опубликовать
curl -X PATCH -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
     -d '{"title": "Новый заголовок"}' $SITE/api/v1/articles/42/
curl -X POST -H "Authorization: Token $TOKEN" $SITE/api/v1/articles/42/publish/
# снизить дневной бюджет на ИИ
curl -X PATCH -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
     -d '{"ai_budget_per_day_usd": "1.00"}' $SITE/api/v1/settings/
# запустить конвейер без ожидания cron
curl -X POST -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
     -d '{"fetch": true, "write": true}' $SITE/api/v1/pipeline/run/
# ИИ подбирает обложки 100 последним опубликованным заметкам без выбранной обложки
curl -X POST -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
     -d '{"only_empty": true, "limit": 100}' $SITE/api/v1/articles/pick-covers/
```

Конвейер из API работает в фоне внутри веб-сервиса; одновременно идёт только один запуск
(повторный вызов вернёт `409` с текущим запуском). Плановые запуски по-прежнему делает cron.
Подбор обложек пачкой идёт так же — как отдельный запуск в журнале (`stats.task = "covers"`):
один дешёвый запрос к `AI_CLASSIFIER_MODEL` на заметку, доли цента; при исчерпанном дневном
лимите на ИИ подбор останавливается.

---

## Telegram: бот и канал

1. В Telegram откройте **@BotFather** → `/newbot` → получите токен `123456:ABC…`.
2. Создайте канал (можно сначала закрытый, тестовый).
3. Канал → Управление → Администраторы → добавьте бота с правом «Публикация сообщений».
4. ID канала: для публичного — `@имя_канала`. Для закрытого перешлите любой пост канала боту
   **@userinfobot** или **@getidsbot** и возьмите число вида `-100…`.
5. Пропишите `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `TELEGRAM_CHANNEL_URL`.
6. **Отправка выключена, пока вы не поставите галочку** в админке: Настройки → «отправлять в Telegram».
   До этого посты только пишутся в лог (dry-run), и их видно в карточке заметки → «Telegram».
   Начните с тестового канала.

Формат поста: 🚨 (для срочного) + **заголовок**, анонс, 📍 город, ссылка «Читать на сайте →».

---

## Деплой на Render (основной вариант)

В репозитории есть `render.yaml` (Blueprint): веб-сервис, PostgreSQL и cron-задача.

1. Залейте репозиторий на GitHub.
2. Render → **New → Blueprint** (не «Web Service»: Blueprint сам возьмёт команды сборки и запуска
   из `render.yaml`) → выберите репозиторий и ветку `main`. Render создаст:
   - `florida-web`: сайт (gunicorn, статика через WhiteNoise, сборка `build.sh` с миграциями);
   - `florida-db`: PostgreSQL;
   - `florida-pipeline`: cron `7 11,22 * * *` (11:07 и 22:07 UTC = 7:07 и 18:07 во Флориде летним временем,
     зимой на час раньше) → `python manage.py run_pipeline`. Чаще или в другое время — поменяйте `schedule`
     в `render.yaml` или в настройках cron-сервиса на Render. Внепланово — `POST /api/v1/pipeline/run/`.
3. Заполните переменные (группа `florida-shared`): `SITE_URL` (например `https://florida-web.onrender.com`,
   потом — ваш домен), `DJANGO_ALLOWED_HOSTS` (домен без https), `DJANGO_CSRF_TRUSTED_ORIGINS`
   (`https://домен`), `DEEPSEEK_API_KEY`, `TELEGRAM_*`. `DJANGO_SECRET_KEY` сгенерируется сам.
4. После первого деплоя: Shell веб-сервиса →
   ```bash
   python manage.py createsuperuser
   python manage.py check_ai                     # проверит ключ DeepSeek и названия моделей
   python manage.py check_sources --activate
   python manage.py run_pipeline --no-write      # проверить сбор без расходов на ИИ
   ```
5. Картинки рекламы: на Render диск временный. Либо подключите Render Disk к веб-сервису
   (`MEDIA_ROOT=/var/data/media`, `SERVE_MEDIA=1`), либо используйте текстовые рекламные блоки.
6. Свой домен: Render → Settings → Custom Domains, затем обновите `SITE_URL`, `DJANGO_ALLOWED_HOSTS`,
   `DJANGO_CSRF_TRUSTED_ORIGINS`. Отправьте `https://домен/sitemap.xml` и `/news-sitemap.xml`
   в Google Search Console.

Ориентировочно: веб Starter $7 + Postgres basic от $6 + cron (от $1) ≈ **$14/мес** плюс ИИ.

## Деплой на PythonAnywhere (запасной вариант)

1. Аккаунт Hacker ($5/мес) или выше: на бесплатном тарифе внешний доступ только к белому списку сайтов.
2. Bash-консоль: `git clone …`, `mkvirtualenv --python=python3.12 florida`, `pip install -r requirements.txt`.
3. Web → Add a new web app → Manual configuration → Python 3.12. В WSGI-файле:
   ```python
   import os, sys
   sys.path.insert(0, "/home/ВАШ_ЛОГИН/florida_news_ru")
   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
   Virtualenv: `/home/ВАШ_ЛОГИН/.virtualenvs/florida`. Static files: `/static/` → `…/florida_news_ru/staticfiles`,
   `/media/` → `…/florida_news_ru/media`.
4. Создайте `.env` рядом с `manage.py` (как `.env.example`, `DJANGO_DEBUG=0`), затем
   `python manage.py collectstatic && python manage.py migrate && python manage.py createsuperuser`.
   База: SQLite подойдёт на старте, или MySQL/Postgres PythonAnywhere через `DATABASE_URL`.
5. Tasks → Scheduled task: на тарифе Hacker доступна одна ежедневная задача, для запуска дважды в день
   нужен тариф с несколькими задачами (или две задачи — на 11:07 и 22:07 UTC). Команда:
   `cd ~/florida_news_ru && ~/.virtualenvs/florida/bin/python manage.py run_pipeline`.

---

## Переменные окружения

| Переменная | Обязательна | Назначение |
|---|---|---|
| `DJANGO_SECRET_KEY` | на проде | секретный ключ Django |
| `DJANGO_DEBUG` | — | `1` локально, `0` на проде |
| `DJANGO_ALLOWED_HOSTS` | на проде | домены через запятую |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | на проде | `https://домен` |
| `SITE_URL` | да | публичный адрес: ссылки в Telegram, sitemap, canonical, Open Graph |
| `DATABASE_URL` | на проде | PostgreSQL (Render подставляет сам) |
| `AI_PROVIDER` | — | `deepseek` (по умолчанию) или `anthropic` |
| `DEEPSEEK_API_KEY` | да | ключ DeepSeek (platform.deepseek.com → API keys) |
| `DEEPSEEK_BASE_URL` | — | по умолчанию `https://api.deepseek.com` |
| `ANTHROPIC_API_KEY` | — | только если `AI_PROVIDER=anthropic` |
| `AI_CLASSIFIER_MODEL` | — | модель отбора, по умолчанию `deepseek-flash` |
| `AI_VERIFIER_MODEL` | — | модель проверки, по умолчанию как у отбора |
| `AI_WRITER_MODEL` | — | модель-автор, по умолчанию `deepseek-v4-pro` |
| `AI_PRICING_JSON` | — | поправить цены моделей для учёта расходов, см. `.env.example` |
| `AI_WRITER_EFFORT` | — | только для Anthropic: `low` / `medium` / `high` |
| `TELEGRAM_BOT_TOKEN` | для Telegram | токен бота |
| `TELEGRAM_CHANNEL_ID` | для Telegram | `@канал` или `-100…` |
| `TELEGRAM_CHANNEL_URL` | — | ссылка для кнопок «Подписаться» (можно задать и в админке) |
| `MEDIA_ROOT`, `SERVE_MEDIA` | — | хранение и раздача картинок рекламы |
| `DEMO_MODE` | — | плашка «демо-данные» |
| `FETCH_USER_AGENT` | — | User-Agent сборщика |

---

## Сколько стоит ИИ (DeepSeek)

**Названия моделей и тарифы DeepSeek в 2026 году часто менялись**, а официальная документация
из среды разработки была недоступна. По умолчанию стоят `deepseek-flash` (отбор и проверка) и
`deepseek-v4-pro` (написание). Первым делом запустите `python manage.py check_ai`: команда покажет,
какие модели реально есть на вашем ключе, и подсветит отсутствующие. Нужные названия задаются
через `AI_CLASSIFIER_MODEL`, `AI_VERIFIER_MODEL`, `AI_WRITER_MODEL`, цены — в `config/settings.py`
(`AI_PRICING`) или через `AI_PRICING_JSON`. В таблице цен — **пиковые** тарифы, поэтому учёт расходов
в админке скорее завышен.

Оценка для 20–40 заметок в день (Flash ≈ $0,30 / $1,20, Pro ≈ $1,32 / $3,96 за млн токенов
вход/выход, вход из кэша ≈ в 10 раз дешевле). Отбор проходят все новые сюжеты, а не только опубликованные.

| Этап | За вызов | В день |
|---|---|---|
| Отбор (Flash), ~150–300 сюжетов × ~1,5 тыс. токенов на вход (большая часть из кэша) и ~100 на выход | ≈ $0,00025 | $0,04–0,08 |
| Написание (Pro), ~1,7 тыс. на вход и до ~1 тыс. на выход | ≈ $0,005 | $0,10–0,20 |
| Проверка (Flash), ~2 тыс. на вход и ~150 на выход | ≈ $0,0005 | $0,01–0,02 |
| **Итого** | | **≈ $0,15–0,30 в день → $5–9 в месяц** |

- Кэш промптов у DeepSeek автоматический: системный промпт с JSON-схемой стоит в начале запроса
  и при повторах берётся из кэша. Это видно в «Расходы на ИИ» → «прочитано из кэша».
- Ответы просим в режиме JSON и проверяем по схеме. Если DeepSeek вернул пустой или битый JSON,
  запрос повторяется один раз, а неудача записывается в лог расходов.
- Бюджет по умолчанию — $3 в день, с DeepSeek его можно смело снизить до $1 (Настройки).
- Вернуться на Anthropic: `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, модели `claude-*`.

## Дизайн

- Направление «Флоридский портал»: классическая сетка новостного сайта (полоса «Срочно», блок
  «Погода и ураганы», главная тема и «Самое важное за сутки», лента, сайдбар), регионы оформлены как
  зелёные указатели флоридских хайвеев. Оранжевый цвет используется только для срочного.
- Обложки (`static/covers/`): у каждой рубрики свой набор из 4–7 картинок — иллюстрации, сгенерированные
  в **Higgsfield** (Recraft V4.1) в одной палитре и стиле флоридских туристических плакатов, вперемешку
  с лицензионными стоковыми фото **Freepik / Magnific** (тариф Premium). Заметке достаётся обложка из
  набора её рубрики по номеру заметки — соседние заметки получают разные картинки. Под стоковым фото
  подпись «Фото: Freepik (иллюстративное)». Фото из чужих статей не используются.
- **Обложку по смыслу выбирает ИИ:** при написании заметки DeepSeek получает список подходящих обложек
  с описаниями (рубрика, ураган для срочной погоды и ЧП, общие виды Флориды; недавно использованные
  помечены) и выбирает одну. Описания — в `news/covers.py` (`CATALOG`). В админке у заметки есть
  выпадающий список обложек с превью; пусто — обложка из набора рубрики по очереди.
  Старым заметкам обложку по тексту подбирает действие «🖼 Подобрать обложку ИИ» в списке заметок
  админки, команда `pick_covers` или API (`pick-cover`, `pick-covers`).
- Добавить обложку: положите в `static/covers/` три файла — `<рубрика>-<N>.webp` (1200×675),
  `<рубрика>-<N>-640.webp` и `<рубрика>-<N>.jpg` (для фото — `<рубрика>-photo-<N>…`), набор обновится сам.
- Шрифты Golos Text и Unbounded (кириллица) раздаются с самого сайта, лицензия OFL в `static/fonts/`.
- Подробности системы — в `DESIGN.md`, продуктовые принципы — в `PRODUCT.md`.

## SEO

Латинские slug из транслитерации заголовка, `NewsArticle` JSON-LD, `sitemap.xml`, отдельный
Google News sitemap `/news-sitemap.xml` (последние 48 часов), Open Graph и Twitter cards,
canonical, `robots.txt`, RSS `/rss/`. Страницы без JS, шрифты с предзагрузкой, картинки в WebP с lazy-load.
