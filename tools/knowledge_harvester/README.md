# Knowledge Harvester AW 0.7.4

## Document corpus workflow (AW0.8.7)

Existing source adapters, Store, provenance and pack writer are reused. Use a
separate developer corpus database; these commands do not touch runtime user
glossary/TM databases or upload documents.

```powershell
.venv\Scripts\python.exe -X utf8 -m tools.knowledge_harvester.cli --db qa/corpora/incoming/harvest.db corpus-intake "C:\corpus" --corpus-id corpus-001 --language zh --origin USER_PROVIDED --permission REVIEW_REQUIRED
.venv\Scripts\python.exe -X utf8 -m tools.knowledge_harvester.cli --db qa/corpora/incoming/harvest.db corpus-export qa/corpora/incoming/candidates.jsonl
.venv\Scripts\python.exe -X utf8 -m tools.knowledge_harvester.cli --db qa/corpora/incoming/harvest.db corpus-review qa/corpora/incoming/reviews.jsonl
.venv\Scripts\python.exe -X utf8 -m tools.knowledge_harvester.cli --db qa/corpora/incoming/harvest.db corpus-build-pack qa/corpora/incoming/manifest.json qa/corpora/incoming/reviewed.tglossary
```

Review JSONL records contain `candidate_id`, `state`, `reviewer`, `reason`, and
`evidence_sha256` (digest of provenance). Verification requires an earlier
REVIEWED state, a target and unchanged evidence; model suggestions cannot become
VERIFIED through this path. Pack export additionally requires redistribution
permission. Unknown permissions keep candidates out of official packs.

PDF/DOCX/ZIP/folders are read-only; ZIP security/CRC limits reuse production
validation. Native PDF text is used by default. Scanned/OCR evidence can be sent
to `corpus.candidate` with the production-captured document hash, offset and
origin; automatic extra OCR intake is not enabled. Language metadata are
explicit, while Chinese action splitting is a bounded heuristic. Candidate
extraction is not bilingual alignment or independent translation review.

Before processing a new user corpus, retain its baseline translation. Keep
development documents separate from untouched holdout documents. Do not use
failed frozen holdout examples to extend production knowledge.

Developer/build layer. Runtime `app/` его не импортирует. Build database и исходные выгрузки находятся в `build/`, отдельно от пользовательских TM/glossary.

## Refinement AW0.7.4

`refinement_policy.json` содержит все настройки и пороги `expansion_policy.json` без изменений плюс `pivot_version: 2`. English Pivot V2 индексирует preferred EN labels, EN aliases и короткие glosses (до 100 символов/6 слов). Разделение `;` и скобочных qualifiers сохраняет исходное значение в evidence. Длинные определения дают только пересечение supporting tokens, без fuzzy proof. Неоднозначные значения, усечённая retrieval-выборка и даже единственный English match остаются REVIEW. `REVIEW_HIGH` — build-only приоритет с совпадением source-declared ZH, не автоматическое принятие.

У pivot китайские формы берутся только у исходного понятия, русские — только у целевого. Это исправляет смешивание вариантов разных смыслов. ExactMatch aliases используются для прохождения уже существующей taxonomy, только от approved sources. Положительные domain keywords учитывают границы слов/простое множественное число; строгие review markers AW0.7.3 сохранены. Межисточниковое совпадение пары учитывает `independence_group`, но не подменяет canonical ID и не отменяет mixed-license gate.

Conflict refinement различает source-attested alternative и `retrieval_only_challenge`: English pivot без совпадения исходной китайской формы в целевом источнике — гипотеза для review, а не подтверждённая альтернативная двуязычная связь. Она сохраняется в conflicts/очереди и не отменяет direct concept автоматически. Direct-vs-direct, source-attested Chinese alternatives и реальные aliases collisions по-прежнему блокируют VERIFIED. Сам pivot не повышается в статусе; веса, threshold, scope и license gates не меняются.

```powershell
# Работать с копией build DB, не с пользовательскими glossary/TM.
.venv\Scripts\python -m tools.knowledge_harvester.complete_mappings --db build/aw074/harvest-final.db --output build/aw074/new-targeted-snapshot --allow-network
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/aw074/harvest-final.db --config tools/knowledge_harvester/refinement_policy.json link
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/aw074/harvest-final.db --config tools/knowledge_harvester/refinement_policy.json build-packs build/aw074/new-packs --reverse
```

`complete_mappings` получает только отсутствующие QID из approved explicit mappings. Необязательный `--priority-concepts file.json` — список до 100 **существующих source concept IDs** для одного перехода по явно указанным P31/P279; parents новых полученных entities не обходятся. Лимит всей выборки 1000 IDs, batches по 50, immutable plan/cache/SHA. `props=info` обязателен, output без lastrevid не принимается. До AW0.7.4 старые acquisition tools не запрашивали info: прежние snapshots закреплены SHA, но individual revisions могли отсутствовать. Исторические raw файлы не перезаписываются.

Фоновый запрос использует `maxlag=5`. Для явно интерактивной операции с ожидающим пользователем есть `--interactive`, согласно [MediaWiki maxlag etiquette](https://www.mediawiki.org/wiki/Manual:Maxlag_parameter); набор QID не расширяется. Retry delay минимум 5 секунд. Нет автоматического обхода блокировок/ошибок и нет бесконечного crawl.

`refinement_report.write_refinement_report(store, baseline_db, output)` создаёт ranked `high-value-review.jsonl`, term-by-term automotive gaps, переходы статусов, independent-pair evidence и категории конфликтов. Частотность — число source-record occurrences, не измеренная частота употребления. Полные queues/build DB остаются build-only; runtime получает только прошедшие исходные trust/license gates пакеты.

## Источники

`source_catalog.json` содержит проверенные условия, но не заменяет metadata конкретной выгрузки. Перед `source-add` укажите `revision`, `acquired_at` и желательно `input_sha256`. Каждая новая ревизия получает новый `source_id`; зарегистрированные metadata неизменяемы.

- Wikidata: entity JSONL / построчный JSON array, `lastrevid`, labels/aliases/descriptions и P31/P279/P361/P2579. Для классификации по умолчанию используются P31/P279.
- CC-CEDICT: локальный UTF-8 dump с традиционной/упрощённой формой, pinyin в одинарных квадратных скобках, английскими определениями. Русский перевод не выдумывается. Формат v2 с двойными скобками требует отдельного адаптера.
- AGROVOC: один expanded SKOS JSON-LD node на строку; `prefLabel`, `altLabel`, `broader`, `exactMatch`. Полный RDF/XML, Turtle, RDF/XL dump не поддержан. Лицензия каталога относится только к zh/ru/en.
- Wiktionary: структурированный JSONL-поднабор (Wiktextract-style), обязательный `source_record_id` с page/revision; всегда review-only. Полный dump/parser и проверка атрибуции конкретной выгрузки отложены.

## Локальный цикл

Запуск из корня TreeTranslate; глобальные параметры идут перед командой.

```powershell
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db source-add source.json
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db ingest source.jsonl --source my-source --adapter wikidata --sample 100
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db ingest source.jsonl --source my-source --adapter wikidata
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db link
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db report
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db review-export build/review.jsonl --sample 50
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db conflicts build/conflicts.jsonl
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db review-import reviewed.jsonl
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/knowledge/work.db build-packs build/packs-v1 --reverse
.venv\Scripts\python -m tools.knowledge_harvester.build.bundled build/packs-v1 build/bundled-v1
```

`classify` повторяет `link` с актуальной policy, сохраняя raw input/human review. После нового ingest сборка требует relink. Изменение policy требует relink; продолжение ingest требует прежний config fingerprint либо новую build DB. Sample ingest ограничивает записи за текущий запуск, следующий запуск продолжает checkpoint. Review sample — детерминированная reservoir-выборка до N кандидатов **на область** (seed 1729), не автоматическое подтверждение качества.

Ingest принимает `.gz`/`.bz2`, ограничивает длину строки и распакованный объём, сохраняет SHA256, offset, ошибки и checkpoints каждые 100 записей. Для compressed resume префикс распаковывается повторно; всего dump в RAM нет. Для крупных dump лимит 2 GiB распакованных данных увеличивается явно в отдельной policy. Слияние ограничено 128 записями на concept; превышения видны в report metadata, raw записи сохранены.

## Review и доверие

`VERIFIED` означает прохождение build policy, **не независимую экспертную проверку**. English pivot остаётся REVIEW. UNKNOWN/REVIEW_REQUIRED/NOT_REDISTRIBUTABLE блокируют официальную сборку даже после ACCEPT. Разные лицензии разделены по пакетам; смешанная provenance требует отдельной проверки совместимости.

Review JSONL: `candidate_id`, `evidence_sha256`, `decision`, `reviewer`; CHANGE_TARGET использует `target`, CHANGE_DOMAIN — `domain`, MERGE — `merge_into`. Решения: ACCEPT, REJECT, CHANGE_TARGET, CHANGE_DOMAIN, MERGE, KEEP_AUTO. Изменение evidence делает старое решение неприменимым. MERGE допускает только совпадающие пару/область. Неразрешённые коллизии остаются REVIEW после повторной проверки.

Прямые и обратные пакеты используют формат AW0.7.1. Обратный пакет содержит только однозначные preferred RU labels; русские алиасы сохранены в NOTICE, но не применяются без отдельного анализа обратных конфликтов. Полная provenance и SOURCES находятся в JSONL NOTICE, legalcode — в LICENSE. Новых имён членов ZIP нет. Сборка не перезаписывает существующий пакет. `prepare` требует новый выходной каталог и переводит SQLite payload в journal_mode DELETE для чтения из каталога без прав записи.

## Явная сеть

```powershell
.venv\Scripts\python -m tools.knowledge_harvester.acquire_wikidata --output build/sources/new-sample --sample 100 --allow-network
.venv\Scripts\python -m tools.knowledge_harvester.cli fetch https://approved.example/dump.jsonl build/source.jsonl --source-metadata source.json --allow-network --dry-run
```

Без `--allow-network` запрос не выполняется. `fetch` также требует одобренные source metadata. URL должен соответствовать проверенному источнику: metadata не являются юридической проверкой любого URL. Реальная выборка Wikidata использует официальный API, ограниченные запросы и сохраняет raw ответы, query, SHA и per-entity revisions; это не полный или статистически репрезентативный корпус. Обхода ограничений источников нет.

Команды мутации CLI поддерживают `--dry-run`. Никакого model-generated наполнения, доступа к AppData или изменения моделей в harvester нет. Benchmark создаёт синтетические данные только в build-каталоге.

## Массовый запуск AW0.7.3

На реальном корпусе обнаружены обратные коллизии русских названий с разным регистром. Сборщик сравнивает нормализованные ключи runtime с Unicode casefold через временный SQLite-индекс. Это ужесточает gate RU→ZH и устраняет полный скан корпуса на каждую обратную пару. Runtime engine не изменён.

Полные CC-CEDICT и AGROVOC обрабатываются в `build/aw073/`; raw archives, staging SQLite, harvest.db, review queues и временные индексы не копируются в `assets/knowledge`.

`prepare_agrovoc.py` закрывает ограничение прежнего JSON-LD adapter: потоково читает официальный LOD N-Triples ZIP и сохраняет materialized SKOS labels/aliases ZH/RU/EN, broader/exactMatch. Промежуточная SQLite закреплена SHA архива и checkpoint; ZIP resume повторяет декомпрессию префикса. Другие языки, SKOS-XL internals и нематериализованные определения не выдаются за поддержанный текст. Полученный expanded JSONL обрабатывается прежним `agrovoc` adapter.

```powershell
.venv\Scripts\python -m tools.knowledge_harvester.prepare_agrovoc build/aw073/sources/agrovoc/agrovoc_lod.nt.zip build/aw073/sources/agrovoc/concepts.jsonl --staging build/aw073/agrovoc-staging.db
.venv\Scripts\python -m tools.knowledge_harvester.expand_wikidata --output build/aw073/sources/wikidata-expanded --per-domain 1500 --depth 3 --config tools/knowledge_harvester/expansion_policy.json --allow-network
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/aw073/harvest.db --config tools/knowledge_harvester/expansion_policy.json link
.venv\Scripts\python -m tools.knowledge_harvester.cli --db build/aw073/harvest.db --config tools/knowledge_harvester/expansion_policy.json build-packs build/aw073/packs --reverse
```

`expand_wikidata` использует официальный API с bounded taxonomy BFS и пачками до 50 entities. Синтаксис объединения условий — `haswbstatement:P279=Q1|P279=Q2`; слово OR не заменяет этот синтаксис. Query plan, ответы, SHA и individual revisions сохраняются; output нельзя переиспользовать с другим планом. Per-domain cap и depth — границы получения данных, не гарантия полноты ветви и не цель по VERIFIED.

`expansion_policy.json` добавляет проверенные taxonomy roots Wikidata/AGROVOC и ужесточает domain-scope markers по находкам реального QA. Score, threshold, exclusions, variants и остальные gates не ослаблены. `expansion_report.write_reports` сохраняет summary, stratified review и отдельную cross-domain review queue в build-каталог. Разные переводы одного ZH термина в разных domains не получают глобального победителя: runtime требует выбранную область, экспертный review остаётся отдельным.
