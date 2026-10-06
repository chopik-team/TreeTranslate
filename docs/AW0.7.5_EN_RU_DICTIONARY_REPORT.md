# TreeTranslate AW 0.7.5 — EN/RU Dictionary & Usage Expansion

Дата: 27 сентября 2026. Этап ограничен английским и русским словарём и примерами. Translation Router, AW0.7.4 Harvester, PDF/OCR, модели и другие языки не изменялись.

## До AW0.7.5

`LexicalAssistance` открывал одну SQLite `vendor/lexicon/lexicon.sqlite3` в read-only режиме и выполнял индексированный lookup по `(source, target, key)`. FreeDict/WikDict давал 62 181 EN→RU и 42 600 RU→EN строк: 57 076 уникальных английских и 42 283 русских ключа. Отдельный `assets/language/usage.json` содержал 20 вручную подготовленных CC0-групп и 36 примеров (EN 25, RU 9, ZH 2); поиск этого маленького слоя был линейным. UI уже имел блоки «Словарь» и «Примеры использования», асинхронный worker и логику выбранного/текущего слова.

База занимала 43 921 408 байт. Русские опубликованные формы не индексировались, а отсутствие точной формы предлагало пользователю ввести начальную форму.

## После AW0.7.5

Существующий `LexicalAssistance`, worker, UI и SQLite сохранены. Схема 2 добавляет в ту же базу таблицы `articles`, `forms`, `examples`, `example_terms`, `lexical_sources`. FreeDict остаётся переводным слоем; новые статьи и примеры дополняют ответ общего API. Весь словарь в RAM не загружается: каждый запрос открывает read-only SQLite, использует индексы и получает до 12 статей и 5 примеров.

| Метрика | До | После |
|---|---:|---:|
| Уникальные EN ключи FreeDict / EN леммы WordNet | 57 076 | 147 765 |
| Уникальные RU ключи FreeDict / RU леммы OpenRussian | 42 283 | 45 238 |
| EN/RU senses нового monolingual-слоя | 0 | 206 978 / 46 982 |
| Опубликованные EN/RU forms | 0 | 161 545 / 486 262 |
| Корпусные EN/RU examples | 0 | 68 008 / 53 569 |
| Ручные CC0 examples | 36 | 36 (сохранены отдельным слоем) |
| Runtime lexical DB | 43 921 408 B | 316 022 784 B |

## Источники и лицензии

- FreeDict/WikDict EN↔RU 2025.11.23 — CC BY-SA 3.0; прежние официальные SHA512 и TEI attribution сохранены.
- Princeton WordNet 3.0 — WordNet 3.0 License, которая разрешает использование, изменение и распространение при сохранении notice. Получен из закреплённого `nltk/nltk_data` revision `550b6625bcef1f2abff2ff770a5a0d272c9c6b2a`; полный LICENSE включён.
- OpenRussian — CC BY-SA 4.0, OpenRussian.org contributors. Revision `50e210c4803237779cb562bc1abcea529066031c`; изменения: CSV преобразован в общую SQLite, формы нормализованы и индексированы. Полный текст лицензии включён.
- Tatoeba EN/RU detailed exports 26.09.2026 — textual sentences CC BY 2.0 France по §6.2 Terms of Use. Для каждого runtime-примера сохранены sentence ID и contributor. Полный legalcode включён.

URL, revision/date, acquisition date, license, attribution, размер и SHA256 каждого raw-файла находятся в `vendor/lexicon/manifest.json`. Acquisition разрешена только через `tools/prepare_lexicon.py --allow-network --expand-en-ru`; повторная сборка из локальных файлов сеть не использует.

## Импорт и качество

WordNet synset остаётся отдельным sense; омонимы `bank`, `current`, `driver` не склеиваются в одну строку. Синонимы сохраняются только внутри исходного synset. OpenRussian semicolon-группы английских эквивалентов сохраняются отдельными senses; грамматические поля и оригинальная accented/lemma spelling остаются в payload.

OpenRussian: 45 561 статьи принято, 13 263 строки отклонено из-за отсутствующей пригодной леммы/английского значения, 1 точный дубль удалён. Tatoeba просканировано 2 035 201 EN и 1 226 454 RU предложений. Фильтр отклонил соответственно 30 842 и 52 970 записей с неподходящей длиной, URL/markup, повреждённым Unicode или нечитабельной структурой; дополнительно удалено 232 и 4 217 повторов предложений. Для каждой леммы остаются до трёх лучших корпусных предложений; общий UI-limit — пять с учётом связанных форм.

Ranking предпочитает законченное предложение длиной около 70 символов и 3–30 слов, штрафует чрезмерную длину. Пример обязан содержать форму, опубликованную источником. Автоматическое сопоставление примера с конкретным sense не заявляется.

## Русские формы и нормализация

Lookup использует реальные формы OpenRussian. QA подтвердил `двигателя → двигатель`, `машины → машина`, `людям → человек`, `работает → работать`. Агрессивного stemming и догадок нет. NFC, casefold и снятие знака ударения сохранены. Для русского lookup `ё` и `е` приводятся к общему ключу, но headword/source spelling остаётся неизменным.

## Размер

- Raw AW0.7.5 English sources: 45 684 745 B (WordNet + Tatoeba EN).
- Raw AW0.7.5 Russian sources: 46 204 027 B (OpenRussian CSV/license + Tatoeba RU).
- Все новые raw sources: 91 888 772 B; они находятся только в ignored `build/lexical-sources/aw075`.
- Предыдущие build lexical sources: 57 912 755 B (включая закреплённые FreeDict и build-файлы).
- Final build DB = runtime DB: 316 022 784 B. Отдельная несжатая build DB не поставляется.
- Логический payload: bilingual entries 33 393 282 chars/bytes units SQLite; EN articles 46 852 673; RU articles 10 767 825; forms 19 890 799; examples 11 572 969; example links 2 938 661. Остальной размер — SQLite pages, row/index overhead и индексы.
- Четыре именованных runtime lookup-индекса (`lookup`, `article_lookup`, `form_lookup`, `example_lookup`) занимают суммарно 50 196 480 B: размер измерен на временной копии как разница после удаления этих индексов и `VACUUM`. Служебные UNIQUE auto-indexes остаются частью остального storage overhead.
- Notices AW0.7.5: WordNet 1 625 B, OpenRussian 20 131 B, Tatoeba legalcode 39 707 B.

APP RUNTIME SIZE увеличился на 272 101 376 байт относительно прежней lexical DB. DEV/BUILD raw sources составляют дополнительно 91 888 772 байта и в installer не входят.

## Производительность и RAM

`tools/benchmark_lexicon.py` проверил шесть EN/RU lookup на установленной базе:

- cold median 1.35 ms, max 2.05 ms;
- warm median 1.21 ms, max 1.60 ms;
- RSS delta 3 371 008 B;
- peak process working set 26 611 712 B.

Результат сохранён в `docs/qa/aw075/lexical-benchmark.json`. Lookup выполняется индексами `article_lookup`, `form_lookup`, `example_lookup`; полного скана таблиц в runtime нет.

## QA и offline

Обязательные EN: `hello`, `person`, `house`, `water`, `work`, `car`, `engine`, `connector`, `steel`, `radiator`; ambiguous `bank`, `current`, `driver`. Обязательные RU: `привет`, `человек`, `дом`, `вода`, `работа`, `машина`, `двигатель`, `разъём`, `сталь`, `радиатор` и четыре формы. Все получили source-derived статьи; все базовые слова и формы получили Tatoeba examples.

Socket connect блокируется в тесте, после чего EN/RU articles и examples продолжают работать. `PRAGMA integrity_check=ok`; DB SHA256 и все доступные raw hashes проверяются. Raw `.csv/.bz2/.zip` отсутствуют в runtime assets. Native UI smoke проверил ambiguous English `bank` и inflected Russian `двигателя`; screenshots: `docs/qa/aw075/english-bank.png`, `russian-inflected-engine.png`.

## Ограничения

- OpenRussian snapshot закреплён по последней ревизии опубликованного GitHub CSV (2021); TogetherDB live export сознательно не scraped.
- OpenRussian даёт английские эквиваленты, а не полноценные русскоязычные толковые определения.
- Tatoeba examples монолингвальны: перевод показывается только у прежнего CC0 curated layer, поскольку безопасная связь с переводом не входила в выбранные per-language exports.
- Forms покрывают опубликованные парадигмы; неизвестные формы не угадываются. Morphology overhaul не выполнялся.
- Ranking не доказывает соответствие конкретному sense/domain; он отвечает за читаемость, наличие формы и отсутствие мусора.
- Производная база содержит материалы с разными лицензиями; применимые notices и attribution должны поставляться вместе с ней.

## Карта изменений AW0.7.5

- Runtime/API: `app/services/lexical_assistance.py`.
- Существующий UI: `app/gui/pages/text_translation_page.py`, `app/gui/widgets/assisted_text_edit.py`.
- Build/import: `tools/prepare_lexicon.py`, `tools/lexical_expansion.py`.
- QA/benchmark: `tests/test_lexical_expansion.py`, `tools/benchmark_lexicon.py`, `tools/smoke_lexical_expansion_ui.py`, `docs/qa/aw075/*`.
- Reproducibility/provenance: `vendor/lexicon/manifest.json`, `vendor/licenses/WordNet/*`, `vendor/licenses/OpenRussian/*`, `vendor/licenses/Tatoeba/*`, локальный license catalog.
- Product docs/version: `app/config/constants.py`, `app/gui/dialogs/changelog_dialog.py`, `README.md`, `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md`, `docs/NEXT_CYCLE.md`.
- Regression-only fix: `app/translation_memory/database.py` — общий внутрипроцессный lock одного SQLite path устранил нестабильную конкуренцию разных экземпляров без изменения TM semantics.

## Проверки

- Targeted lexical/UI tests: 68 passed.
- Native lexical UI smoke: passed.
- Lexical DB integrity/hash/licenses/source hashes: passed.
- Полный regression: 516 passed за 159,16 s.
- Конкурентный доступ Translation Memory дополнительно проверен 20 повторными прогонами: 80 проверок, 0 ошибок. Разные экземпляры `Database` теперь делят внутрипроцессный writer/initialization lock по каноническому пути; внешний SQLite lock и безопасный fallback сохранены.
- `python -m compileall -q app tools`: passed.
- `git diff --check`: passed.

## Git status

Работа выполнена поверх существующего незакоммиченного состояния ветки `codex/next-cycle`; reset/revert/delete не применялись. Runtime DB и raw corpora исключены из Git, воспроизводимый manifest, код, tests, reports, screenshots и notices остаются видимыми в diff.
