# Каталог «Детям»: данные и зацепки для проверки

## Файлы для импорта (все записи — черновики)

```bash
python manage.py import_clubs kids/data/from_directory_central_fl.csv
python manage.py import_clubs kids/data/research_2026_11_central_fl.csv
```

- `from_directory_central_fl.csv` — 3 записи из справочника `/links/deti/` (Центральная Флорида), описания
  переписаны без национальных маркеров. Ресёрч справочника: октябрь–ноябрь 2026.
- `research_2026_11_central_fl.csv` — 5 записей, найдены 26.11.2026. **Важно:** сеть облачной сессии не
  пускала на сами сайты, факты взяты из поисковых выдержек этих страниц. Перед публикацией откройте
  источники из `editor_note` и сверьте. Отдельно решите про Bilingual Bridges (общенациональный
  репетиторский сервис) и Sonya Flex Academy (русский язык занятий не заявлен — только языки тренеров).

## Зацепки, которые не удалось подтвердить (в CSV не вошли)

Найдены только в поисковой выдаче 26.11.2026; сайты открыть не удалось. Проверить вручную и при
подтверждении добавить через админку или CSV.

### Центральная Флорида
- YouSwim — плавание на русском и английском; город не указан: https://youswim.org/
- Russian-American Community Center of Florida — субботние занятия для детей; страница старая
  (набор осень 2017): http://russianamericancenter.org/services/russian-classes-for-children/
- Украинская католическая церковь Покрова (Апопка) — уроки украинского для детей, данные 2022 г.:
  https://mynews13.com/fl/orlando/news/2022/03/28/how-language-brings-together-the-ukrainian-community
- Varyvoda Christian Academy — частная школа, не кружок: https://www.varyvodaacademy.com/
- Тренеры по плаванию на Thumbtack / teachme.to (язык не указан):
  https://teachme.to/listings/swimming/swimming-with-olena-sadovska
- Alpha & Omega Chess Club — без указания языка: https://chessorlando.com/membership/

### Южная Флорида, Джексонвилл (за пределами текущего списка городов — нужны новые города в админке)
- «Золотой ключик» (Sunny Isles Beach) — воскресная школа 3–12 лет: чтение и письмо, математика, шахматы:
  http://goldenkeyrus.com/
- Miami Russian Academy (Aventura) — язык, музыка, рисование, театр «Галактика»:
  https://svoi.us/company/miami-russian-academy-50
- Плавательная школа «Малахит» — тренеры говорят по-русски; Майами, Санни-Айлс, Халландейл, Авентура,
  Холливуд: https://swimmalahit.com/
- Kirova Dance Academy (Hallandale Beach) — балет по методу Вагановой, 3–18 лет; язык не подтверждён:
  https://app.enrollio.ai/v2/preview/R7rxA7gj4mVkRgh0VTKC
- Russian Immersion (MET School, Miami) — продлёнка 1–5 классы:
  https://metschool.jumbula.com/AfterSchool202526/RussianImmersion
- After School Program (Sunny Isles / Aventura), 5–12 лет:
  https://www.miamifamilyclub.com/ru/services/child-daycare/after-school-program-13664.html
- Alagymnastics (Miami) — художественная гимнастика; язык не подтверждён: https://tampafp.com/?p=262219
- Каталоги объявлений: https://www.bazar.club/miami/business/section ,
  https://www.bazar.club/jacksonville/business/all-for-kids
- Global Outreach Charter Academy (Jacksonville) — школа с русским языком; источнику ~10 лет:
  https://russkiymir.ru/publications/208964/

По Тампе и украиноязычным кружкам зацепок не нашлось.
