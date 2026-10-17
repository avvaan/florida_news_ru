---
name: Florida RU
description: Русскоязычная первая полоса Флориды, где иерархию задаёт срочность, а таблички регионов выглядят как указатели флоридских хайвеев.
colors:
  ink: "#0f2433"
  ink-2: "#33495a"
  muted: "#566a78"
  paper: "#ffffff"
  mist: "#eaf5f3"
  line: "#d5e0e4"
  gulf: "#0b7a75"
  gulf-deep: "#07524f"
  shallow: "#7fd1c7"
  storm: "#c2410c"
  storm-deep: "#9a3412"
  sun: "#ffc93c"
  sun-soft: "#fff4d1"
typography:
  display:
    fontFamily: "Unbounded, Golos Text, system-ui, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Golos Text, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.75rem, 4.2vw, 2.75rem)"
    fontWeight: 800
    lineHeight: 1.08
    letterSpacing: "-0.028em"
  title:
    fontFamily: "Golos Text, system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.012em"
  body:
    fontFamily: "Golos Text, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
  body-story:
    fontFamily: "Golos Text, system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: "Unbounded, Golos Text, system-ui, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.07em"
rounded:
  flag: "3px"
  sm: "4px"
  sign: "7px"
  md: "8px"
  lg: "12px"
  pill: "999px"
spacing:
  gutter: "clamp(16px, 3vw, 32px)"
  wrap: "1240px"
  sidebar: "320px"
  section: "40px"
  column-gap: "56px"
components:
  button-primary:
    backgroundColor: "{colors.gulf}"
    textColor: "{colors.paper}"
    rounded: "{rounded.pill}"
    padding: "0.65em 1.1em"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.gulf-deep}"
  button-sun:
    backgroundColor: "{colors.sun}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0.65em 1.1em"
    height: "44px"
  button-sun-hover:
    backgroundColor: "#ffd866"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.gulf-deep}"
    rounded: "{rounded.pill}"
    padding: "0.65em 1.1em"
  sign:
    backgroundColor: "{colors.gulf}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sign}"
    padding: "0.55em 1.05em"
    height: "44px"
  sign-current:
    backgroundColor: "{colors.sun}"
    textColor: "{colors.ink}"
  chip:
    backgroundColor: "{colors.mist}"
    textColor: "{colors.gulf-deep}"
    rounded: "{rounded.pill}"
    padding: "6px 12px"
    height: "36px"
  flag-urgent:
    backgroundColor: "{colors.storm}"
    textColor: "{colors.paper}"
    rounded: "{rounded.flag}"
    padding: "0.28em 0.5em 0.24em"
  panel-weather:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.lg}"
    padding: "clamp(18px, 3vw, 28px)"
  card-telegram:
    backgroundColor: "{colors.gulf-deep}"
    textColor: "{colors.paper}"
    rounded: "{rounded.lg}"
    padding: "24px"
---

# Design System: Florida RU

## Overview

**Creative North Star: "Первая полоса у съезда с хайвея"**

Классическая новостная первая полоса на белой бумаге, но с материалом самой Флориды: регионы — зелёные таблички хайвеев с белой внутренней рамкой, срочное — оранжевая «штормовая» полоса, предупреждения — солнечно-жёлтые. Иерархию задаёт срочность, а не только свежесть: полоса «Срочно» и блок «Погода и ураганы» стоят над главной темой дня.

Плотность — газетная: лента строками с миниатюрой, дайджест нумерованным списком, разделение линиями `--line` и толстой чернильной чертой под заголовками секций, а не карточками с тенями. Изображения — только собственные плоские иллюстрации в стиле флоридских туристических плакатов середины века (Recraft V4.1, палитра `#0F2433 #0B7A75 #7FD1C7 #F26B1D #FFC93C #CFE9F2 #FFFFFF`), несколько на рубрику: `static/covers/<topic>[-N].webp` (1200×675), `-640.webp`, `.jpg` для OG. В те же наборы входят лицензионные стоковые фото Freepik/Magnific (`<topic>-photo-N`), подписанные «Фото: Freepik (иллюстративное)»; `news/covers.py` чередует иллюстрацию и фото и выбирает обложку по номеру заметки. Фото из чужих материалов не используются.

Мобильный — в первую очередь, без фреймворков: один файл `static/css/site.css`, токены на `:root`, иконки — SVG-спрайт `templates/includes/icons.svg` (`i-mark`, `i-telegram`, `i-spiral`, `i-pin`, `i-clock`, `i-arrow`, `i-external`, `i-alert`).

**Key Characteristics:**
- Белая бумага + чернильно-синий; зелень залива как голос навигации и действий.
- Оранжевый `storm` — только для срочного; жёлтый `sun` — для предупреждений, фокуса и текущего положения.
- Таблички регионов-указатели на чернильной полосе — фирменный элемент.
- Плоско: глубина — тоном панелей и внутренними рамками, не тенями.
- Обложки 16:9 со скруглением 8px, лёгкий zoom при наведении.

## Colors

Сдержанная «дорожно-приморская» палитра: чернила и бумага несут текст, зелень залива — навигацию, оранжевый и жёлтый зарезервированы под сигналы.

### Primary
- **Зелень залива** (`gulf`): фон табличек регионов, основная кнопка, квадратный маркер заголовков секций, цифры дайджеста, иконки источников.
- **Глубокий залив** (`gulf-deep`): hover основной кнопки и табличек, фон Telegram-карточки, текст ссылок в теле статьи, хлебных крошках, рубрике в мета-строке, чипах и ghost-кнопке. Основной цвет ссылок на белом.

### Secondary
- **Штормовой оранжевый** (`storm`): полоса «Срочно», флажок «Срочно» в заголовках, метка «Чрезвычайное» у погодных предупреждений. `storm-deep` — текст белой метки внутри оранжевой полосы.
- **Солнечный** (`sun`): текущая табличка региона, кнопка подписки, метка «Сильное», ссылки на чернильной панели, кольцо фокуса, выделение текста, ссылка «К содержанию». `sun-soft` — фон плашки предпросмотра.

### Tertiary
- **Мелководье** (`shallow`): hover-подчёркивание заголовков и тем, hover чипа, время истечения предупреждений и заголовки колонок в подвале (на чернилах).

### Neutral
- **Чернила** (`ink`): основной текст, фон полосы табличек, погодной панели и подвала, `theme-color`.
- **Чернила-2** (`ink-2`): подзаголовки, лиды, тизеры, неактивные темы.
- **Приглушённый** (`muted`): мета-строки, подписи, дата, номер страницы, метка рекламы.
- **Бумага** (`paper`): фон страницы и шапки.
- **Туман** (`mist`): фон чипов, блока источников, рекламных блоков и плейсхолдеров обложек.
- **Линия** (`line`): разделители строк ленты, дайджеста, индекса тем, ghost-кнопка (inset 2px).

### Named Rules
**The Storm Is Only for Storms Rule.** `storm` появляется только там, где есть флаг срочности или чрезвычайное предупреждение (`is_urgent`, severity extreme). Никаких оранжевых кнопок и декоративных акцентов.

**The Darker Orange Rule.** UI-оранжевый (`storm`) темнее постерного `#F26B1D` иллюстраций и `#c8460b` из направления: белый текст на нём обязан проходить контраст. Палитры обложек и интерфейса родственны, но не тождественны.

**The Yellow Means "You Are Here / Act" Rule.** `sun` — текущее положение (табличка `is-current`), фокус, подписка и предупреждения. Не использовать как фон контента.

## Typography

**Display Font:** Unbounded 800 (fallback Golos Text, system-ui)
**Body Font:** Golos Text 400/600/700/800 (fallback system-ui, -apple-system, Segoe UI, Roboto)

Шрифты самохостятся из `static/fonts` (кириллица + латиница, `font-display: swap`; 400 и 800 кириллицы — preload).

**Character:** Широкий геометричный Unbounded — голос вывески: логотип и маленькие капительные метки. Golos Text — плотная современная гротескная кириллица для всего, что читают.

### Hierarchy
- **Display** (Unbounded 800, 1.6rem / 1.2rem на телефоне, uppercase): только словесный знак «Florida RU».
- **Headline** (Golos 800, clamp(1.75rem, 4.2vw, 2.75rem), 1.08, −0.028em): заголовок главной темы; `story__title` — clamp(1.85rem, 4.6vw, 2.9rem), max 22ch; `section-head__h` — clamp(1.8rem, 4vw, 2.6rem).
- **Title** (Golos 700, 1.08–1.15rem, 1.25–1.28): заголовки плиток и строк ленты. Golos 800 1.3–1.4rem — заголовки Telegram-карточки и пустых состояний.
- **Lede** (Golos 400, clamp(1.05rem…1.3rem), 1.45–1.5, `ink-2`, 60–62ch): тизер главной и лид статьи.
- **Body** (Golos 400, 1.0625rem/1.55); тело статьи — 1.15rem/1.7, max 68ch, абзацы через 1.05em.
- **Label** (Unbounded 800, 0.72–0.78rem, uppercase, +0.06…0.08em): заголовки секций «Лента новостей», «Самое важное за сутки», «Темы», «Источники», колонок подвала; метки «Срочно» и severity.
- **Meta** (Golos 400, 0.85rem, `muted`, tabular-nums): время, регион с иконкой-пином, рубрика (600, `gulf-deep`).

### Named Rules
**The Unbounded Is a Sign Rule.** Unbounded только 800 и только в вывесочных ролях: словесный знак, капительные метки, цифры дайджеста (1.5rem, `gulf`). Никогда для заголовков статей и текста.

**The Tight Headline Rule.** Заголовки 700–800 с отрицательным трекингом (−0.01…−0.028em), `text-wrap: balance`; цифры времени — всегда tabular-nums.

## Layout

Контейнер `.wrap`: max 1240px, поля `clamp(16px, 3vw, 32px)`. Мобильный-первый, брейкпоинты 600 / 760 / 960px.

- **Шапка:** строка даты и «Наш Telegram» → логотип 56px и теглайн справа (28ch, скрыт <600px) → чернильная полоса табличек регионов → строка тем с подчёркиванием 3px → оранжевая полоса «Срочно».
- **Первый экран главной:** блок погоды (сетка `1fr 180px` с иллюстрацией от 760px) → `.front`: главная тема 2fr + дайджест 1fr от 960px (gap 40px) → три плитки от 600px над линией.
- **Лента + сайдбар:** `minmax(0,1fr) 320px`, gap 56px (статья — 64px) от 960px; сайдбар `sticky; top: 20px`.
- **Строка ленты:** миниатюра 112px квадрат → от 600px 200px 16:9 + тизер; padding 18px, линия снизу.
- **На телефоне:** плитки «ещё главное» становятся компактными строками 112px; ряды табличек и тем скроллятся горизонтально с маской-затуханием справа; полоса «Срочно» показывает один пункт в 2 строки.
- **Ритм:** 6–14px внутри компонентов, 18–24px между элементами, 28–40px между блоками, 64px низ `main`.
- Цели касания ≥ 44px (кнопки, таблички; 40px таблички на телефоне, 36px чипы).

## Elevation & Depth

Система плоская: ни одной `box-shadow`-тени у поверхностей. Глубина передаётся тоном — чернильная панель погоды, тёмно-зелёная Telegram-карточка, туманные блоки источников и рекламы на белой бумаге — и линиями. Единственные «рамки-тени» — `inset`: двойное внутреннее кольцо табличек (3px цвета фона + 4.5px белого) и 2px `line` у ghost-кнопки. Пульсирующее кольцо (`@keyframes signal`, 2.4s) — только у метки «Срочно» в полосе.

### Named Rules
**The Flat Paper Rule.** Поверхности не поднимаются тенями. Если нужно выделить блок — тональная панель (`ink`, `gulf-deep`, `mist`) со скруглением 10–12px.

## Shapes

Мягкие, но собранные углы. Обложки, реклама, предупреждения — 8px (`--radius`); крупные панели (погода, Telegram) — 12px; блок источников — 10px; таблички — 7px с белой внутренней рамкой, как у дорожного знака; метки severity — 4px; флажок «Срочно» и маркер секции — 2–3px; кнопки и чипы — пилюля 999px. Обложки всегда 16:9 (`object-fit: cover`), в ленте на телефоне — квадрат. Заголовок секции подчёркивается чертой 3px `ink` с квадратным маркером 10px `gulf` слева.

## Components

### Buttons
Пилюли, уверенные и простые.
- **Shape:** пилюля (999px), min-height 44px, Golos 600 1rem.
- **Primary** (`.btn`): `gulf` / белый; hover — `gulf-deep`; active — сдвиг вниз на 1px. Переход 0.2s `--ease`.
- **Sun** (`.btn--sun`): `sun` / `ink` — подписка в Telegram-карточке.
- **Ghost** (`.btn--ghost`): прозрачная, `gulf-deep`, inset-кольцо 2px `line`; hover — `mist`. Пагинация.
- **Footer** (`.btn--tg`): белая на чернилах, hover — `sun`. **Focus** глобально — обводка 3px `sun`, offset 2px.

### Таблички регионов (signature)
`.sign` на полосе `ink`: фон `gulf`, белый текст 600, радиус 7px, двойное inset-кольцо, создающее белую внутреннюю рамку. Hover — `gulf-deep` и подъём на 1px. Текущий регион — `sun` с чернильной рамкой и `aria-current="page"`. Под полосой — строка тем: ссылки 600 0.95rem `ink-2` с бордюром 3px (hover `shallow`, текущая `gulf`).

### Срочно
- **Полоса** (`.urgent`): `storm`, белый текст 600, белая метка Unbounded с текстом `storm-deep` и пульсом.
- **Флажок** (`.flag`): `storm`/белый, Unbounded 800 0.55em, радиус 3px, стоит внутри ссылки заголовка перед текстом; `.flag--lg` для заголовка статьи. Только при `is_urgent`.

### Погода и ураганы (signature)
Чернильная панель 12px; заголовок с иконкой-спиралью `sun`; сетка предупреждений `auto-fit minmax(240px,1fr)` на полупрозрачных плитках (`rgb(255 255 255 / .06)`, 8px). Severity-метка: extreme — `storm`, severe — `sun`, прочие — `mist`. Ссылки — `sun`. От 760px справа иллюстрация `weather-640.webp`.

### Карточки новостей
- **Главная тема** (обложка 1200px, headline, лид, мета) и **плитка / строка** (обложка 640px, title, мета) — без фона и тени. Hover — обложка `scale(1.03)` за 0.6s, заголовок получает подчёркивание 2px `shallow`.
- **Дайджест:** нумерованный список, цифры Unbounded `gulf` в колонке 46px, разделители `line`.

### Chips
`mist`/`gulf-deep`, пилюля, 600 0.9rem; hover — `shallow`/`ink`. Темы региона и теги (`#тег`).

### Telegram-карточка
`gulf-deep`, 12px, padding 24px, иконка 36px `sun`, заголовок Golos 800 1.3rem, кнопка `sun`. В сайдбаре, после статьи и на страницах.

### Источники
Туманный блок 10px, метка `gulf-deep`, список «издание жирным + заголовок» с иконкой `i-external` `gulf` справа, разделители `rgb(11 122 117 / .18)`. Обязателен под каждой заметкой.

### Navigation (подвал)
Чернила, 4 колонки от 960px (1.6fr 1fr 1fr 1.2fr), метки колонок Unbounded `shallow`, белые ссылки, логотип 44px.

### Реклама
Метка «Реклама · рекламодатель» 0.75rem `muted` над блоком `mist` 8px; текстовый вариант — 600 `gulf-deep`. Всегда отделена и подписана.

## Do's and Don'ts

### Do:
- **Do** брать цвета только из токенов `:root`; ссылки на белом — `gulf-deep`, на чернилах — `sun`.
- **Do** ставить сигналы в порядке угрозы: полоса «Срочно» → погода → главная тема → лента.
- **Do** давать каждой новой рубрике набор из 3+ обложек: иллюстрации в том же постерном стиле и палитре плюс спокойные стоковые фото без брендов, цен и смакования; каждая в трёх файлах (`.webp` 1200×675, `-640.webp`, `.jpg`).
- **Do** использовать иконки только из спрайта `icons.svg` (`<svg class="i"><use href="#i-…"/></svg>`, 1em).
- **Do** держать цели касания ≥ 44px и уважать `prefers-reduced-motion` (вся анимация отключается).
- **Do** использовать `--ease` (`cubic-bezier(.16, 1, .3, 1)`) для всех переходов.

### Don't:
- **Don't** использовать `storm` вне срочного и чрезвычайного.
- **Don't** вводить тени у карточек и панелей — система плоская.
- **Don't** набирать Unbounded заголовки статей или текст.
- **Don't** превращать ленту в сетку одинаковых карточек блога: строки с миниатюрой, дайджест — список.
- **Don't** ставить стоковые фото или фото из чужих материалов вместо собственных иллюстраций.
- **Don't** публиковать заметку без блока «Источники».
