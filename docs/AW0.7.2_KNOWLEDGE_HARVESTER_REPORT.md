# TreeTranslate AW 0.7.2 — Knowledge Harvester & Technical Knowledge Population

Аудит и реализация: 24–25 сентября 2026. Версия приложения: **AW 0.7.2**, без `-alpha`. Фундамент AW0.7 Translation Memory и AW0.7.1 Glossary сохранён. Это завершённый первый build pipeline и **ограниченный developer preview данных**, не экспертно выверенный технический словарь.

## 1. Архитектура и границы

`tools/knowledge_harvester/`: sources → normalized raw concepts → canonical concepts → domain/link candidates → quality/conflict/review → существующий `.tglossary`. Модули `models`, `storage`, `ingest`, `normalization`, `linking`, `domains`, `quality`, `review`, `licenses`, `network`, `build` разделены. Runtime не импортирует harvester; сеть есть только в явных developer acquisition/fetch-командах с `--allow-network`.

Build SQLite v1 находится в `build/knowledge/preview-1000.db`, содержит sources/files/checkpoints/raw_records/relations/concepts/english_labels/candidates/aliases/conflicts/reviews/errors/metadata. Она не является пользовательской TM/glossary. Существующие AppData записи не использовались как corpus и не наполнялись автоматически.

Runtime получает 26 отдельных read-only payloads из `assets/knowledge/manifest.json`, проверяет SHA256 и границы путей. Повреждение отключает bundled knowledge с metadata-only warning; пользовательский glossary и model router продолжают работать. Payloads подготовлены штатным AW0.7.1 installer во временной registry, затем переведены в SQLite journal_mode DELETE. Чтение не требует создания WAL/SHM рядом с приложением. Пользовательская БД и её WAL-поведение не изменены.

## 2. Источники, лицензии и отклонения

| Источник | Проверенные условия | Фактический статус |
|---|---|---|
| Wikidata structured entities | CC0-1.0, [Wikidata Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing) | Принят, единственный источник реальных пакетов |
| AGROVOC zh/ru/en | CC-BY-4.0, [FAO](https://www.fao.org/agrovoc/maintenance); другие языки не покрываются этим разрешением | Локальный expanded SKOS JSON-LD adapter; реальный dump не включён |
| CC-CEDICT | Актуальная CC-BY-SA-4.0, [MDBG](https://www.mdbg.net/chinese/dictionary?page=cc-cedict) | Локальный parser классического dump; реальный corpus не включён, страницы словаря не скрейпились |
| Wiktionary | CC-BY-SA-4.0/GFDL, [copyrights](https://en.wiktionary.org/wiki/Wiktionary:Copyrights) | REVIEW_REQUIRED; ограниченный структурированный adapter, production dump отложен до pinning и attribution audit |
| WIPO Pearl | [Terms](https://www.wipo.int/en/web/wipo-pearl/terms-wipopearl) запрещают массовое извлечение/хранение/переформатирование/распространение без разрешения | NOT_REDISTRIBUTABLE, загрузки нет |
| Коммерческие/неизвестные словари | Нет проверенного разрешения | Исключены |

Дата проверки условий: 2026-09-24. Реестр: [source_catalog](../tools/knowledge_harvester/source_catalog.json), [отклонённые источники](qa/aw072/rejected-sources.json). AGROVOC RDF/XML/Turtle/RDF-XL и полный Wiktionary extraction **не заявлены реализованными**. Локальные parser fixtures проверяют контракт адаптеров, а не заменяют реальный corpus.

License gate использует APPROVED_FOR_REDISTRIBUTION / REVIEW_REQUIRED / NOT_REDISTRIBUTABLE / UNKNOWN; последние три не допускаются в official pack даже после human ACCEPT. Metadata требуют revision/date/license/source/attribution. Проверяются языки labels и aliases. Разные license families получают отдельные пакеты, смешанная provenance блокируется. Share-alike не превращается молча в CC0. Полные CC legalcodes сохранены локально. Это техническая проверка закреплённых сведений, не автоматическое юридическое заключение для любого URL.

## 3. Реальный сбор, revisions и hashes

Вместо дорогого multilingual SPARQL join (служба вернула 502) использован [официальный Wikidata API](https://www.wikidata.org/wiki/Wikidata:Data_access): ограниченные `haswbstatement:P279=Q...` запросы по проверенным taxonomy roots и `wbgetentities` по 20 entities. Запрос максимум 1000 дал **664** уникальных concepts; выборка не случайна и не представляет весь технический словарь. До неё проверен sample 98 records. Массовый dump и дальнейшее массовое наполнение не выполнялись.

Raw ответы, queries и `entities.jsonl` сохранены в `build/knowledge-sources/wikidata/preview-1000/` (локальные build artifacts, не Git). В [SOURCES.json](qa/aw072/SOURCES.json) сохранены acquisition date `2026-09-24T18:29:33.548770+00:00`, SHA каждого API response/query и input SHA. Индивидуальные `lastrevid` сохранены в raw и pack NOTICE. Нельзя обозначать live subset как одну общую ревизию Wikidata.

Input JSONL: **12 448 091 байт**, SHA256 `c273fe564f580a72b8f1bcd11e6af456f912111c7de2db414cf272ce87bef73e`. Текущий config fingerprint: `fa2475dbac66bf6237b0d34c6c400bcf8d9100500ab15f177721f83550b35d6e`. Инвентарь исходного кода: [code-inventory.json](qa/aw072/code-inventory.json); tool version 0.7.2 и git HEAD включены в pack provenance. HEAD не содержит текущую незакоммиченную работу, поэтому одного HEAD для воспроизведения недостаточно.

Повторная сборка **из локального raw при заблокированных Python socket** воспроизвела SHA всех 26 `.tglossary`: [pack-integrity.json](qa/aw072/pack-integrity.json). Для новых API runs request URL/expected response key закрепляются рядом с cache; изменённый запрос не может использовать старый cached response. Старый cache без request pin требует новый выходной каталог.

## 4. Streaming, resume, canonical concepts

JSONL/построчный Wikidata array/CEDICT читаются ограниченными строками; поддержаны gzip/bz2, max-record/decompression limits, checkpoints каждые 100 строк, SHA/config pin и idempotent insert. Невалидная строка сохраняет metadata error и не скрывает следующую допустимую запись. Uncompressed resume использует byte seek; compressed resume повторно распаковывает префикс. Default decompressed limit 2 GiB меняется явно для более крупных dump.

NFKC/пробелы/кавычки нормализуются отдельно от оригинальных labels. Simplified/Traditional берутся только из source-declared zh-hans/zh-hant/zh-cn/zh-tw; конвертер не выдумывает синонимы. `RawConcept` содержит original labels/aliases/descriptions/definitions/relations/mappings/metadata, `CanonicalConcept` объединяет записи по устойчивому ID или явному exactMatch. Совпадение английского написания само по себе не сливает concepts.

RAM ограничена строкой/пачкой/одним concept, graph walk и коротким pivot candidate set. Concepts с более чем 128 raw records не объединяются, raw сохраняются, счётчик виден в metadata (в текущем corpus 0). Полный dump не материализуется в Python dict/list. Предел traversal — 512 узлов / 12 уровней; неполный граф может снизить покрытие.

## 5. Linking, domains, quality, review и dedup

Direct ZH↔RU — labels одного concept; cross-source direct требует явного общего canonical ID. Английские labels/короткие определения индексируются в SQLite; точный pivot и неоднозначный pivot различаются, **оба не становятся VERIFIED автоматически**. MACHINE_CANDIDATE зарезервирован, model inference для наполнения отсутствует.

13 configurable domains; evidence содержит taxonomy paths. P31/P279/broader дают классификацию, keyword hints одни остаются review-only. Один concept может попасть в несколько областей. Имена людей/организаций/географические объекты/бренды/языки исключаются; подозрительные labels/descriptions, model names, слишком общие термины и пограничные отрасли понижаются. Roots были проверены по actual API labels; ошибочные первоначальные QIDs удалены до сборки preview. Эти эвристики не гарантируют отсутствие оставшихся семантических ошибок.

Score объяснимый: direct 60, preferred bilingual pair +15, taxonomy +20, независимое подтверждение +5; generic −30, pivot −35; threshold 90. Mirror с тем же independence_group не повышает независимость. Недостающая языковая пара → AUTO, неопределённая лицензия/слабый domain/conflict → REVIEW. Score — **не вероятность правильности перевода**.

Коллизии всех ZH aliases внутри области при разных RU targets направляются в review; 16 directed conflict edges (обе стороны, не 16 независимых понятий). Human decisions закреплены evidence SHA; изменённая provenance инвалидирует прежнее принятие. ACCEPT/REJECT/CHANGE_TARGET/CHANGE_DOMAIN/MERGE/KEEP_AUTO поддержаны, не обходят license gate. Повторный conflict scan защищает от конфликтующих ACCEPT. MERGE разрешает лишь идентичную пару/domain и сохраняет evidence.

При упаковке одинаковые pair/domain объединяются с полным NOTICE. **474 VERIFIED candidates → 472 runtime entries на направление**: по одному дублю объединено в materials-science и technical-core. Обратные пары проверяются на неоднозначный preferred RU; RU aliases оставлены в provenance, но не экспортированы в runtime без отдельной проверки обратных коллизий.

## 6. Состав preview и пакеты

[Полная статистика](qa/aw072/harvest-summary.json): raw/concepts **664**; domain candidates **994**; VERIFIED **474**, REVIEW **132**, AUTO **388**, REJECTED **0**; malformed raw **0**; human review decisions **0**. VERIFIED здесь означает прохождение policy, **не экспертно подтверждённые переводы**. Все 994 candidate records имеют DIRECT_CONCEPT origin; это включает AUTO с недостающими labels, поэтому число не равно числу двуязычных пар. Реальные packs: 100% source-derived direct, 0% pivot, 0% ручной semantic review, один источник Wikidata. Multi-domain объясняет, почему candidates больше исходных concepts.

| Область | VERIFIED | REVIEW | AUTO | Записей в каждом направлении | ZH→RU / RU→ZH, байт |
|---|---:|---:|---:|---:|---:|
| automotive | 36 | 22 | 46 | 36 | 19772 / 19106 |
| chemistry-engineering | 22 | 1 | 24 | 22 | 14142 / 13828 |
| computer-hardware | 30 | 3 | 14 | 30 | 19065 / 18387 |
| electrical | 9 | 14 | 15 | 9 | 10847 / 10680 |
| electronics | 35 | 12 | 22 | 35 | 20142 / 19543 |
| industrial-safety | 1 | 0 | 1 | 1 | 7798 / 7796 |
| manufacturing | 14 | 2 | 31 | 14 | 12015 / 11825 |
| materials-science | 40 | 1 | 8 | 39 | 20315 / 19796 |
| measurement | 59 | 4 | 29 | 59 | 26604 / 25620 |
| mechanical-engineering | 4 | 22 | 28 | 4 | 8952 / 8891 |
| metallurgy | 32 | 5 | 58 | 32 | 17175 / 16740 |
| software | 32 | 7 | 4 | 32 | 20467 / 19647 |
| technical-core | 160 | 34 | 107 | 159 | 60826 / 58003 |

26 пакетов: **472 ZH→RU + 472 RU→ZH**, всего 944 runtime rows с повторением общих понятий по областям. Все CC0-1.0, DEVELOPER PREVIEW. `.tglossary` суммарно **507 982 байт**, SQLite payloads **1 708 032 байт**, build DB **4 173 824 байт**. Это не 944 независимых новых concepts. SHA/размеры/источники/duplicate counts каждого пакета: [packs.json](qa/aw072/packs/packs.json) и per-pack `.report.json`; per-domain direct/pivot/manual percentages, variants и source-declared Traditional — в `harvest-summary.json`.

Формат AW0.7.1 не расширен: manifest.json, entries.jsonl, NOTICE, LICENSE, README. SOURCES вложен в JSONL NOTICE, а отдельно сохранён в QA; неподдерживаемое имя ZIP-члена не добавлено. Полный legalcode и provenance доступны offline. Existing install/enable/disable/remove lifecycle сохранён. Bundled assets читаются как built-in providers; CLI lifecycle управляет отдельно устанавливаемыми пользовательскими пакетами. Для общего отключения glossary используется прежний config enabled=false.

## 7. Review artifacts и реальные QA

[review_queue.jsonl](qa/aw072/review_queue.jsonl): 994 кандидата со статусами и evidence; [conflicts.jsonl](qa/aw072/conflicts.jsonl): 16 записей; [stratified-review.jsonl](qa/aw072/stratified-review.jsonl): 579 записей, до 50 на область, seed 1729. [gold-source-derived-review.jsonl](qa/aw072/gold-source-derived-review.jsonl): 240 source-derived ожидаемых label pairs, помечены SOURCE_ALIGNED_REQUIRES_HUMAN_SEMANTIC_REVIEW. Это **заготовка для gold review**, не 240 автоматически объявленных правильными эталонов.

Automotive QA использует существующие 6 excerpts из `tests/fixtures/pdf/semantic-corpus.json`, связанные с `automotive.pdf`, реальный M2M100 CUDA до/после: **2 term matches, 1 enforced, 1 fallback, fidelity 2/6 до и 2/6 после**. [Результаты с полными парами](qa/aw072/automotive.json). Это сегментная проверка, не новый прогон всего PDF writer. Оригинал PDF SHA `ba930a3e2470c3566dd1bcd79247863717bb66a4ae5fb93d5a9fbaceb2b1bf1f` не изменён. Пользовательская TM не пополнялась.

Общего повышения качества не доказано. В sample отсутствует source alias `冷却液`, присутствует `冷却剂` → «охлаждающая жидкость»; нужный alias не был придуман вручную. В предупреждении про двигатель каноническая вставка ухудшает грамматику («при жарке двигатель»). Fidelity здесь проверяет структурные инварианты, а не смысл или русское согласование. Placeholder fidelity/fallback не решают морфологию, ошибки базовой модели и недостаток покрытия.

Metallurgy: `检查合金钢。` → «Проверьте легированная сталь.»; source-derived 合金钢 выбирается как longest match вместо вложенного 钢, domain isolation и enforced insertion подтверждены. [QA](qa/aw072/metallurgy.json). Согласование падежа остаётся ограничением.

Все **944 canonical runtime entries** проверены lookup через существующий GlossaryEngine, все 26 SQLite integrity_check=ok, checksums совпали, sidecars=0. Это проверка загрузки/поиска, не независимая оценка семантики.

## 8. Обычный перевод текста и UI

Переиспользованы TextTranslationPage, FileTranslationPage, TranslationPreferences, TranslationUiController и HybridTranslationService. Добавлен обычный QComboBox «Область перевода» с русскими названиями 13 областей и `general`; общая preference сохраняется и синхронизируется. Domain передаётся в submit_text/TranslationRequest и DocumentConfig. Смена области запускает новый текстовый перевод; file selector блокируется на время file job. Отдельного движка или отдельной пользовательской базы не создано.

Реальный Qt controller test: general → модель; automotive + `冷却剂` → прямой glossary hit; подтверждённая TM для того же текста → пользовательский ответ с высшим приоритетом. Отдельный реальный M2M100 service test: `更换冷却剂。`, domain automotive, pack_ids заполнены, constraint_status=enforced, автоматических записей TM/glossary нет.

[Текстовый экран](qa/aw072/text-ui.png), [минимальный размер 1180×680](qa/aw072/text-ui-minimum.png), [файлы](qa/aw072/files-ui.png) и [лицензии](qa/aw072/about-licenses.png) отрендерены Windows Qt с WA_DontShowOnScreen и просмотрены. При минимальном размере нижние справочные блоки прокручиваются. Offscreen-plugin на Windows дал квадраты вместо системных шрифтов; итоговые screenshots получены Windows platform plugin, без изменения font logic приложения.

AboutDialog переиспользован: существующая информация о движках сохранена во вкладке, рядом добавлена прокручиваемая вкладка лицензий. Новые tabs/browser используют общую тёмную тему, ссылки — цвет accent. Исправлено прежнее описание поддержки архивов: показаны реально поддержанные текст/DOCX/PDF/сканы. Это все UI-переработки данного этапа, полный редизайн не выполнялся.

## 9. Лицензии в «О проекте»

Локальный каталог: **185 component rows**, включая runtime lock, 104 OCR distributions, model cards, данные, шрифт, иконки, build/test компоненты и 26 knowledge packs. Доступны полные сохранённые LICENSE/NOTICE, CPython LICENSE с included notices, PDFium/native notices, OFL шрифта, документ иконок и provenance пакетов. Ссылки открываются только явным действием пользователя; runtime ничего не скачивает.

Указано точное выражение wheel Qt `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`, отдельно отмечен commercial вариант. Различаются лицензии программы, weights, datasets и images. **Неопределённость итоговых Argos EN↔RU weights и полного per-asset перечня Flaticon/Icons8 сохранена явно**, а не подменена MIT программы. Каталог не равен завершённому legal audit будущего installer; отдельные native Qt module obligations требуют проверки при распространении. [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md).

## 10. Производительность и проверки

[Benchmark](qa/aw072/benchmark.json), синтетические records вне production corpus:

| Записей | Ingest, с | Link/classify, с | Build, с | Peak RSS процесса, MiB | Build DB, MiB |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.02 | 0.02 | 0.12 | 35.3 | 0.45 |
| 1 000 | 0.08 | 0.14 | 0.29 | 37.5 | 3.48 |
| 10 000 | 0.70 | 1.40 | 2.16 | 40.2 | 33.85 |
| 100 000 | 6.85 | 17.28 | 26.05 | 42.4 | 338.46 |

100k: ingest ≈14 605 records/s, linking ≈5 788/s, standalone classify ≈69 008/s, conflict scan 0.56s, pack 12 339 513 байт. Peak RSS — OS peak working set процесса, не изолированная аллокация одного этапа. Замер сделан до финального добавления scope keyword filters/cache pin/UI; структура алгоритма та же, это сохранённый benchmark этапа, не новый замер финального commit. Runtime glossary benchmark AW0.7.1 сохранён отдельно. Проверка миллионов records не выполнялась.

Полный regression и итоговые static checks: см. [validation.json](qa/aw072/validation.json), [JUnit](qa/aw072/full-tests.xml). Базовые 429 тестов сохранены; добавлены проверки streaming/resume/hash/license/aliases/pivot/review/conflicts/reproducibility/bundled readonly/ordinary-text UI/real model. Итоговый полный прогон: **457 passed, 163.17 s**, 0 failures/errors/skips. После последних исправлений cache pin и разрешения локальных ссылок About повторены профильные проверки: **28 passed, 5.38 s**. Compileall и git diff --check: exit 0. Все локальные ссылки каталога лицензий проверены на существование файлов.

## 11. Изменённые файлы, сохранность и завершение

Новые группы: `tools/knowledge_harvester/**`, benchmark/QA/license builder, `tests/test_knowledge_harvester.py`, `tests/test_knowledge_text_ui.py`, `app/config/knowledge_domains.py`, `app/glossary/bundled.py`, `assets/knowledge/**`, `assets/licenses/**`, дополнения `vendor/licenses`, отчёт и QA artifacts. Изменены existing factory/controllers/services/pages/About/styles/version/changelog и README/NEXT_CYCLE/THIRD_PARTY_NOTICES. Точный baseline delta: [preservation.json](qa/aw072/preservation.json), окончательный git status: [git-status.txt](qa/aw072/git-status.txt).

Ветка `codex/next-cycle`, HEAD `9aa36fc327463b5ef11d6d02e40a810207bd5e8f`. Репозиторий уже содержал незакоммиченные AW0.7/AW0.7.1 и QA snapshots. Исходный снимок `build/aw072-audit/baseline.json` охватывает **706 файлов**; пропавших файлов **0**. Прежние TM/glossary modules, tests и QA snapshots не заменены; новые изменения наложены поверх сохранённой работы. Промежуточные сгенерированные пакеты/базы перемещены в build audit archive перед окончательной пересборкой. Reset/revert, удаление пользовательских файлов и commit не выполнялись.

Остаются ограничения preview: неполный corpus и taxonomy, нет экспертного gold set, нет морфологического согласования, отсутствуют полный AGROVOC dump/Wiktionary extractor и общий native licensing audit installer. Новые модели, fine-tuning, cloud, installer, AW0.8 и массовая ручная редактура не начаты. Продолжение наполнения и review — отдельное задание.
