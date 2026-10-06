# TreeTranslate AW 0.7.1 — Glossary Engine & Knowledge Packs

Дата: 24.09.2026. Проект: `C:\TreeTranslate`, ветка `codex/next-cycle`.

## Итог простыми словами

Добавлен локальный глоссарий, отдельный от памяти переводов. Подтверждённое предложение из TM сохраняет приоритет. Если его нет, глоссарий находит термины и либо возвращает полный термин напрямую, либо закрепляет термины при переводе предложения. Производственные словари не загружались и не устанавливались: пользовательские базы остаются без автоматически добавленного корпуса.

Реальный пример M2M100 ZH→RU:

- Источник: `更换冷却液并检查连接器。`
- Без терминов: «Заменить холодильник и проверить соединитель.»
- С проверочными терминами: «Заменить антифриз и проверить разъём.»

Это результат конкретного теста, а не гарантия качества любого технического текста. Полные результаты: [real-backends.json](qa/aw071/real-backends.json).

## 1. Аудит и архитектура

Изучены AW0.7 TM, KnowledgeEngine и его extension points, TranslationRequest/Result, HybridTranslationService, TranslationRouter, реальные Argos/M2M100 backends и токенизация, normalizers, faithful_result, DocumentJob, DOCX/PDF/OCR callbacks, AppData/config и текущие тесты. Backends не имеют glossary prompt API; выдуманный prompt не добавлялся.

Новый пакет `app/glossary`: models, database, repository, normalization, matcher, ranking, constraints, placeholders, engine, importer, exporter, packs, maintenance, errors. Общий SQLite-код TM не переписывался. Совместимый импорт прежнего `GlossaryEntry` теперь указывает на расширенную сущность глоссария; термины не записываются в таблицу TranslationUnit.

```text
Текст / DOCX / native PDF / PaddleOCR result
  → TranslationKnowledgeEngine
  → TM safe hit: вернуть подтверждённый перевод без изменений
  → TM miss: Glossary lookup
      полный доверенный термин → fidelity → результат без модели
      совпадения внутри предложения → PlaceholderCodec
        → существующий TranslationRouter → Argos/M2M100
        → проверка маркеров → восстановление терминов → fidelity
      повреждение маркера/ограничения → исходный запрос к Router + warning
```

`backend_only` обходит оба слоя знаний. Source==target/пустой текст сохраняют прежний passthrough. Новые поля результата: knowledge_source, glossary_hits_count, pack_ids, domain, constraint_status. В UI использованы существующие строки статуса; нового редактора или UI-компонента нет.

## 2. Хранилища и миграции

User DB: `%LOCALAPPDATA%\CHOPIK Team\TreeTranslate\glossary.db`. Development override: `TREETRANSLATE_GLOSSARY_PATH`, аргумент API или CLI `--db`. Это отдельный файл от translation_memory.db; изменение одной базы не меняет другую.

SQLite schema v1 (`PRAGMA user_version`):

- `entries`: поля термина, языковая пара, domain/context, case/whole_word, priority/status/trust/mode, origin/provenance/source_pack, notes, dates, явные варианты и запрещённые целевые варианты.
- `aliases`: нормализованные основные термины/варианты и индекс `(pair, domain, hash, entry_id, term)`.
- `lengths`: небольшой каталог встречающихся длин терминов для пары/domain.
- `suppressions`: пользовательские запреты встроенных терминов.
- `packs`: активные версии, локальные пути, manifest и enabled state.
- `metadata`: ревизия; триггеры на изменение entries/suppressions/packs инвалидируют кеши.

WAL, FULL synchronous, foreign keys, trusted_schema OFF, busy timeout 250 мс. Создание схемы атомарно под BEGIN IMMEDIATE, версия повторно читается после получения блокировки. Более новая/неизвестная схема не перезаписывается. Повреждённая база не удаляется автоматически.

Найденная регрессия concurrency исправлена: одновременная начальная настройка WAL/схемы сериализуется короткой отдельной блокировкой. Повторное открытие готовой v1 не берёт ненужную write-транзакцию. Обычные операции используют отдельные SQLite connections, без общего cursor. Проверены пять повторов конкурентного сценария по четыре потока с отдельными экземплярами движка.

Read-only builtin: отдельные базы через SQLite `mode=ro`, в том числе immutable payloads установленных пакетов. Управление enabled и пользовательские изменения находятся только в user DB. Обновление приложения не переустанавливает пользовательские термины.

## 3. Matcher и нормализация

Выбран **индексированный поиск кандидатов**, а не полный Python trie/Aho-Corasick: он не требует загружать сотни тысяч терминов в RAM. На запись строятся SQLite alias indexes. На чтение лениво загружаются только встречающиеся длины терминов для пары/domain; из нормализованного текста формируются подстроки этих длин и пакетные hash-запросы. После хеша обязательно сравнивается строка.

Стоимость зависит от длины сегмента и числа различных длин терминов, не от полного количества записей. Полного цикла `for every entry` в lookup нет. EXPLAIN QUERY PLAN подтверждает `SEARCH aliases USING PRIMARY KEY (pair=? AND domain=? AND hash=?)`. Построение основного индекса входит в время вставки/import; benchmark «lazy index» включает первое чтение каталога длин и первый lookup, а не создание всех SQLite indexes.

Нормализация: NFKC по символьным/комбинируемым последовательностям, унификация кавычек и пробелов, отдельный casefold для insensitive поиска. Сохраняется карта координат в **исходную** строку: расширение `ß→ss`, составное `e + accent` и повторные пробелы не сдвигают маскируемые spans. Частичное совпадение внутри расширенного символа отвергается. Цифры, дефисы и регистр sensitive-терминов не удаляются.

Latin/Cyrillic whole-word учитывает Unicode буквы/цифры/комбинируемые знаки/underscore: car не совпадает внутри card. Для Chinese используется последовательность символов без требования пробела. Stemming, автоматические синонимы и ML domain detector не добавлены. Варианты задаются явно; направление пары не инвертируется автоматически.

## 4. Пересечения, приоритеты, доверие

Кандидаты ранжируются детерминированно: user CONFIRMED → точный domain → priority → длина исходного span → trust → стабильные id/store. Затем выбираются непересекающиеся spans. Longest-match действует при равенстве более высоких приоритетов: для одинаково доверенных записей выбирается `engine coolant temperature sensor`, а не вложенное `coolant`.

Requested domain берётся из TranslationRequest/DocumentConfig; без выбора — general. Допускаются только выбранный domain и general fallback. Непустой context требует совпадения. Domain-specific не перебивает явно подтверждённое пользовательское переопределение более высокого уровня.

CONFIRMED/REVIEWED/IMPORTED/BUILTIN могут применяться. AUTO/REJECTED/DISABLED не применяются. Пользовательский импорт без явного trusted остаётся AUTO. Импорт не присваивает чужим данным статус пользовательского подтверждения.

`remember_term()` — API для будущего редактора. `disable/remove` управляют user entries; `suppress/unsuppress` сохраняют запрет builtin term в user DB, не меняя пакет. Пользователь может затем задать свой перевод того же термина. Повторная идентичная запись не размножается; импорт может повысить доверие AUTO→IMPORTED, но не снимает DISABLED/REJECTED. Для редактирования других полей существующей user-записи сейчас используются remove/add; полноценный редактор отложен.

## 5. Маркеры: реальная проверка

Проверены три формата, по одному и двум маркерам в предложении для каждой пары. Ниже число сохранённых тестов из двух:

| Backend / пара | TTTERM0001 | __TTTERM0001__ | ZXQ0001QXZ |
|---|---:|---:|---:|
| Argos EN→RU | 2/2 | 0/2 | 2/2 |
| Argos RU→EN | 2/2 | 0/2 | 2/2 |
| M2M100 ZH→RU | 0/2 | 0/2 | 2/2 |
| M2M100 EN→RU | 2/2 | 2/2 | 2/2 |

Выбран `ZXQ{:04d}QXZ`: **8/8 в данном проверочном наборе**. Это не предположение об универсальной сохранности. Каждый runtime-результат всё равно проверяется. Артефакт: [placeholders.json](qa/aw071/placeholders.json), воспроизведение: `tools/probe_glossary_placeholders.py`.

Codec пропускает номера маркеров, уже присутствующие в источнике, хранит mapping и требует ровно одно целое вхождение каждого ожидаемого маркера. Missing, duplicate, mutation, частичное повреждение или встраивание в другое ASCII-слово отвергаются. Перестановка допустима: восстановление идёт по идентичности, а не исходной позиции. После восстановления действует дополнительный fidelity guard.

Если маскированный запрос не проходит либо backend возвращает повреждённые маркеры, выполняется обычный запрос с исходным текстом и warning. Повреждённая промежуточная строка не публикуется. Cancel не перехватывается как повод для повторного inference. Нет слепой замены слов в уже переведённом тексте.

## 6. Применение терминов и ограничения грамматики

`GLOSSARY_FULL_SEGMENT`: весь нормализованный сегмент совпадает с одним доверенным термином; возвращается его перевод без Router. Для PDF добавлен ранний **knowledge-only** callback перед прежним сохранением коротких заголовков. Иначе `Coolant` мог бы сохраниться как прежний protected title и не дойти до глоссария. Остальные правила PDF и writer не переписаны; отдельный тест доказывает замену короткой метки без вызова модели.

Для предложения маркеры маскируют найденные spans. Restore возвращает канонические target terms; склонения, число и род автоматически не подбираются. Explicit source variants не являются морфологическим анализатором. Например, вариант connectors с каноническим target «разъём» сам по себе не создаст форму «разъёмы» — при необходимости нужна отдельная запись с соответствующим target.

Modes: PREFERRED — canonical replacement; KEEP — исходный literal; FORBIDDEN — только проверка результата. `forbidden_target_variants` обнаруживаются с границами слов (для Chinese — последовательности символов). Наличие запрещённого варианта выдаёт warning/constraint_status; глобального blind replace нет. При обычном fallback терминология может остаться неверной: результат помечен `fallback_unconstrained`/`forbidden_detected`, а не `enforced`.

## 7. Fidelity и документы

Glossary full/prose results проходят прежний faithful_result плюс проверку полных IDs, URL/email, чисел, знаков/диапазонов/процентов и известных единиц. Есть небольшой **валидационный** список эквивалентных записей единиц (liters/литра/л и другие), без использования его как production glossary. 6.6 liters→6.6 gallons отвергается; 6.6 liters→6.6 литра допустимо. Список единиц не универсален; неоднозначные случаи консервативно отклоняются либо остаются ограничением прежнего model path.

Проверены GDS/ITM/IVT, PS4, Xbox, M10, ISO 9001, 6.6, 45–60%, 20, знаки и ссылки. KEEP сохраняет literal. После fallback сохраняется прежний pipeline: в PDF остаются его финальные guards и conservative preserve. Для обычного текстового model output не заявляется новый универсальный валидатор всех возможных физических единиц.

Сквозной тест DOCX/native PDF/OCR PDF использует один KnowledgeEngine, настоящий Argos и настоящее PaddleOCR CPU. В трёх результатах присутствует заданный термин, нет маркеров, оригиналы проверены SHA256. TM не пополнялась. Отчёт: [documents.json](qa/aw071/documents.json). OCR confidence/bbox/router не менялись.

## 8. Формат пакета и лицензии

`.tglossary` v1 — ZIP: manifest.json, entries.jsonl, optional LICENSE/NOTICE/README. Manifest: format/schema, pack_id/name/version, языки/domains/count, created_at, publisher/provenance/license/description, minimum TreeTranslate version, SHA256 entries. Private paths автоматически не включаются. Формат не исполняет код и не скачивает зависимости.

Проверяются версия, язык/domain каждой записи, count/hash, отсутствие повторных ZIP имён и посторонних/path-traversal entries, предел распаковки 512 МиБ, длина manifest/record. Проверка выполняется в отдельной временной SQLite; только полностью валидный payload активируется транзакцией registry. Пакет с 99 корректными и одной некорректной записью не оставляет установленную половину.

Official builder требует известный идентификатор лицензии из консервативного списка и непустые publisher/provenance. Неизвестные/неподдержанные license IDs блокируют официальную сборку; расширение списка требует отдельной проверки. Это проверка метаданных, не доказательство наличия у автора прав. User package может явно использовать `--user-package`; установка такого источника возвращает warning. `--trusted` — явное решение доверять содержимому, без него entries AUTO. Хеш проверяет целостность, **не цифровую подпись или подлинность издателя**.

Test fixture: [test-automotive.tglossary](qa/aw071/test-automotive.tglossary), 10 синтетических EN→RU entries, CC0-1.0, явно обозначен как **не production corpus**. Source/manifest находятся в `tests/fixtures/glossary`. Chinese/Cyrillic fixtures создаются тестами отдельно. Никакие интернет-корпуса не загружались.

## 9. Lifecycle, import/export и conflict scan

Build → install → lookup → disable → enable → update v1(10)→v2(12) → remove проверены тестом. Update не размножает старую версию в активных lookup, сохраняет user override и enabled state, меняет registry revision. Понижение версии запрещено. Payload-файлы immutable и читаются mode=ro. Старые версии после update/remove остаются **неактивным локальным кешем** ради безопасности конкурентных читателей; автоматическая очистка этих файлов пока не реализована. Remove удаляет регистрацию и исключает термины из lookup.

CSV/TSV: source/target/source_language/target_language/domain; optional priority/case_sensitive/whole_word/notes/variants. Варианты в CSV/TSV — JSON-массив. JSONL имеет поля GlossaryEntry. Import одной транзакцией, ошибка отменяет все записи. Export user JSONL обходит только user repository, не встроенные пакеты. Пользовательский набор можно явно собрать в .tglossary через builder с manifest.

CLI `tools/glossary.py`: list/stats/add/remove/disable/suppress/unsuppress/import/export/install-pack/remove-pack/enable-pack/disable-pack/packs/integrity/duplicates/conflicts. Builder: `tools/build_glossary_pack.py`.

`conflicts` делает отдельный локальный дисковый audit всех зарегистрированных stores, включая выключенные пакеты: одинаковый source/domain с разными target, точные дубликаты и пересекающиеся aliases. Возвращает итоговые counts и до 1000 деталей каждого типа, ничего не удаляя. Это явная административная операция, не часть runtime lookup. В лёгком stats поле conflicts относится к user DB (`conflict_scope=user`); total entries учитывает и выключенные установленные пакеты.

## 10. Кеши, отказоустойчивость и privacy

Result cache: до 512 записей; ключ содержит исходную строку для корректности offsets, языковую пару, domain/context, ревизии user/builtin/pack registry и config. Каталог длин: до 8 compiled-index cache entries. Max term 256 символов, max matches 128, candidate limit 4096, max lookup fragments 100000, source bound 20000. Превышение лимита сегмента пропускает глоссарий с предупреждением, не останавливая модель.

Коррумпированная/locked/неподдержанная glossary DB временно отключает глоссарий; TM и модели работают. Коррумпированная TM не блокирует glossary/model. Обе неисправны — остаётся model path. Это проверено spy-тестами. Retry/перезапуск повторяет попытку; повреждённые базы не удаляются.

В runtime logs нет source/target: только безопасный код предупреждения. Тесты запрещают socket DNS/connect; KnowledgeEngine сохраняет offline_scope. Экспорты, CLI list и синтетические developer QA transcripts содержат текст по явному запросу. SQLite не зашифрован; используются права локальной учётной записи. Автоматического обучения на output нет.

## 11. Benchmark до 500000

Ryzen 7 5700X, Windows, Python 3.12.13. Синтетические EN→RU/ZH→RU/RU→EN entries; temporary DB удалена после замера, пользовательский словарь не наполнен. Ниже медианы мс; singleton по 5 повторов, scans/batch по 3. Cold очищает прикладной result cache, но **не OS disk cache**. Некоторая фоновая нагрузка от тестов возможна.

| Entries | DB startup | Lazy index + lookup | Exact | Chinese | Cyrillic | 10 terms | 100 terms | Batch ≤100 segments | Import delta, с |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 1.69 | 4.64 | 4.64 | 4.52 | 4.47 | 5.09 | 5.93 | 18.33 | 0.02 |
| 100 | 1.69 | 4.62 | 4.44 | 4.50 | 4.70 | 6.13 | 11.38 | 158.19 | 0.02 |
| 1000 | 1.57 | 4.42 | 4.79 | 4.79 | 4.89 | 6.52 | 24.67 | 482.43 | 0.09 |
| 10000 | 2.05 | 4.82 | 4.86 | 5.65 | 4.67 | 7.46 | 30.72 | 495.40 | 0.86 |
| 100000 | 1.60 | 4.48 | 4.37 | 4.40 | 4.44 | 6.97 | 26.55 | 457.54 | 10.83 |
| 500000 | 1.74 | 4.78 | 4.38 | 4.48 | 4.45 | 7.25 | 29.76 | 457.57 | 52.02 |

На маленьких корпусах фактических терминов меньше 10/100, потому что записи распределены по трём парам; `actual` и batch size указаны в JSON. Для 500000 записей 1 term ≈4.43 мс, 10 terms ≈7.25 мс, 100 terms ≈29.76 мс. Batch — последовательные вызовы lookup для 100 разных сегментов, не векторизированный model batch.

RSS после 500000: 35753984 байт (~34.1 МиБ), peak working set процесса 38400000 (~36.6 МиБ). SQLite DB: 195203072 байт (~186.2 МиБ). Это RSS отдельного benchmark процесса без Argos/M2M100/Paddle и не оценка всей памяти TreeTranslate. Все 6 integrity_check=ok. Импорт последнего delta — 400000 записей за 52.02 с; полный корпус собирался последовательно.

Первичный источник чисел, максимумов, RSS и query plan: [benchmark.json](qa/aw071/benchmark.json), инструмент `tools/benchmark_glossary.py`. Индексы строятся при insert/import; «index build» здесь не означает загрузку всех терминов в RAM. Безусловные target latency и универсальная скорость не заявляются.

## 12. Тесты и окончательный статус

Проверены schema/migrations, user/builtin split, pairs, Unicode/case/boundaries/variants, longest/overlap/domain/context/priority/trust, overrides/suppression, direct labels, codec/reorder/collision/corruption, fidelity/units/KEEP/forbidden, import/export, versioned packs/atomic errors, conflict scans, cache invalidation, repeated concurrency, corrupt fallback, offline/log privacy, backend_only и TM priority.

Реальные backend tests: Argos EN→RU/RU→EN, M2M100 ZH→RU/EN→RU, canonical terms в многотерминных предложениях. Actual outputs/model IDs/device сохранены. Документный тест реально запускает PaddleOCR и Argos на CPU; probe/backend tests используют CUDA. Полный регрессионный набор также проверяет прежние CPU/GPU/Auto, OCR, PDF, DOCX, pause/cancel и UI.

Первоначальные glossary tests: [glossary-tests.xml](qa/aw071/glossary-tests.xml), 63 passed. Первоначальный полный прогон: [full-tests.xml](qa/aw071/full-tests.xml), 411 passed. После завершающих исправлений: **429 passed, 0 failed, 0 skipped**, 149,07 секунды; [новый JUnit](qa/aw071/continuation/full-tests.xml). Compileall и diff check успешны.

## 13. Ограничения и границы этапа

- Сохранность выбранного маркера не гарантируется для любого контекста: обязательны per-result validation и честный fallback.
- Canonical term не гарантирует русское склонение, plural agreement или литературный перевод окружения.
- Domain/context сейчас задаются через API/DocumentConfig; отдельного UI выбора domain/редактора нет.
- Набор проверяемых единиц ограничен; общий перевод модели при fallback не становится автоматически терминологически проверенным.
- Нормализация консервативна и проверена на заявленных Latin/Cyrillic/Chinese примерах; полный универсальный Unicode grapheme engine не заявляется.
- Явные priority/user override могут победить более длинный термин — это выбранный порядок конфликтов из ТЗ.
- При большом количестве длин/конфликтов срабатывает budget и warning, а не неограниченная обработка.
- Нет цифровой подписи packs и автоматического решения лицензионной совместимости. Неизвестный SPDX ID требует review/добавления в builder allowlist.
- Old immutable pack payloads не удаляются автоматически. User entry edit пока remove/add.
- Нет массового production наполнения, scraping, обучения, новых моделей, embedding DB, облака, editor UI, установщика или переписывания OCR.

## 14. Изменённые файлы и Git

Новые: `app/glossary/**`, `assets/config/glossary.json`, tools build_glossary_pack/glossary/benchmark_glossary/probe_glossary_placeholders, glossary tests/fixtures, этот отчёт и `docs/qa/aw071`.

Расширены: TranslationKnowledgeEngine/GlossaryEntry compatibility import, фабрика, TranslationResult metadata, HybridTranslationService warnings, ранний direct knowledge callback PDF, status controller, constants/changelog/README/NEXT_CYCLE. UI не переделан; существующий статус показывает источник и предупреждения. OCR, model backends и writers не переписаны.

Предыдущие незакоммиченные изменения AW0.7 сохранены; весь dirty diff нельзя приписывать AW0.7.1. Новых commit/push в этом этапе нет. Снимок: `docs/qa/aw071/git-status.txt`.

После финальных проверок работа останавливается. AW0.7.2 Knowledge Population не начинается автоматически.

## 15. Продолжение и завершающая проверка — 24.09.2026

При продолжении работы реализация AW0.7 и AW0.7.1 уже находилась в незакоммиченной рабочей копии. Источником состояния были файлы проекта; прежний код не восстанавливался из истории чата. Сохранённый исходный JUnit AW0.7.1 содержит 411 успешных тестов, без ошибок и пропусков.

Исправлены два пробела в проверках:

- PlaceholderCodec теперь отклоняет неизвестные маркеры всех трёх поддерживаемых форматов, включая TTTERM и __TTTERM__. Ранее проверка неизвестных маркеров охватывала только ZXQ. Исходные literal-маркеры и выбор свободного номера сохранены.
- Manifest проверяет явные языковые коды в нижнем регистре, каждый domain и тип SHA256. Некорректные метаданные отклоняются также при сборке пустого пакета. Регрессионные тесты проверяют сохранение установленного пакета и integrity пользовательской базы после неудачной установки.

Добавлены 18 регрессионных случаев; отдельный запуск tests/test_glossary.py: 78 passed. Схема SQLite, UI, модели и OCR не менялись.

Для сохранения существующих QA-артефактов smoke tools и glossary integration tests поддерживают TREETRANSLATE_QA_DIR. Новый прогон пишет в qa/aw071/continuation, а runtime TM/glossary направлены в отдельные базы build/aw071-continuation. Пользовательские базы не наполнялись. Старые скриншоты и результаты проверок не перезаписываются.

Замеры до 500000 записей в benchmark.json относятся к исходной реализации AW0.7.1; повторный benchmark после этих правок не заявляется, алгоритм поиска и индексы не менялись.

Свежая полная регрессия: **429 passed за 149,07 секунды**, без ошибок и пропусков. Реальные Argos/M2M100, OCR, DOCX/PDF, CPU/GPU/Auto и Qt smoke включены в прогон. [Документные результаты](qa/aw071/continuation/aw071/documents.json): все три формата применили глоссарий, SHA256 оригиналов сохранены, TM units=0. [Результаты моделей](qa/aw071/continuation/aw071/real-backends.json) записаны отдельно от предыдущего запуска. `python -m compileall -q app tools`, `git diff --check`, CLI integrity/stats на отдельной пустой базе успешны.

Дополнительно изменены при продолжении: app/glossary/packs.py, app/glossary/placeholders.py, tests/test_glossary.py, tests/test_glossary_integration.py, tools/smoke_translation_ui.py, tools/smoke_lexical_ui.py, CHANGELOG.md, README.md, docs/NEXT_CYCLE.md и этот отчёт. Сверка с SHA256-снимком начала продолжения подтверждает отсутствие удалённых файлов и сохранность остальных исходных файлов, включая прежние QA-артефакты. Commit/push/reset/revert не выполнялись. Этап AW0.7.1 закрыт; наполнение знаний остаётся отдельной задачей.
