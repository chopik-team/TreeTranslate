# TreeTranslate AW 0.7.3 — Knowledge Expansion

Дата: 25 сентября 2026. Этап расширяет данные существующего AW0.7.2 Harvester.
TM, GlossaryEngine, TranslationKnowledgeEngine, Router, модели, OCR, PDF/DOCX и формат AW0.7.1 не переписаны.

## Результат

Обработано **181 495 исходных записей** из трёх разрешённых источников. Итог: **48 предварительных пакетов**, 13 областей, **4 406 записей ZH→RU / 4 334 RU→ZH**. Это количество записей с повторением между областями, а не число уникальных понятий. Уникальных VERIFIED пар ZH/RU без учёта domain: **3 041**.

Статусы кандидатов отдельно: **VERIFIED 4 409; REVIEW 50 326; AUTO 141 989; REJECTED 222**. VERIFIED означает прохождение автоматической policy, не экспертную сертификацию. Подтверждённых человеком пар: **0**. Ни одной model/LLM-generated production pair не добавлено. English не поставляется как направление перевода этих пакетов.

## Audit и сохранность

Исходное состояние изучено по коду и файлам проекта, включая README, CHANGELOG, NEXT_CYCLE, отчёты AW0.6.2/AW0.7/AW0.7.1/AW0.7.2, конфигурации, тесты, source catalog и git diff/status. Предыдущие TM/glossary extension points и обычный текстовый режим присутствовали до расширения.

Ветка `codex/next-cycle`, HEAD `9aa36fc327463b5ef11d6d02e40a810207bd5e8f`. AW0.7–AW0.7.2 уже находились в незакоммиченном состоянии. Автоматических commit/reset/revert/delete не выполнялось. Начальная инвентаризация: `build/aw073/audit/baseline.json`, 989 файлов; исходный binary diff и status сохранены рядом. Отсутствующих файлов при финальной проверке: **0**. Оригинальные runtime-пакеты перенесены в `build/aw073/audit/aw072-runtime`; хеши совпадают с baseline. См. [preservation.json](qa/aw073/preservation.json).

Общее gitignore-правило `build/` скрывало также исходники `tools/knowledge_harvester/build`. Добавлено точечное исключение для этого Python-пакета. Корневой `build/aw073`, raw данные и временные индексы остаются игнорируемыми. Инвентаризация 989 файлов не охватывала исходники, скрытые прежним правилом; это ограничение исходного снимка, а не заявление о полной резервной копии проекта.

## Источники, лицензии, revisions

Проверка действующих условий: **25.09.2026**. [SOURCES.json](qa/aw073/SOURCES.json) содержит pinned metadata, SHA256 и acquisition plan; [license-audit.json](qa/aw073/license-audit.json) — границы лицензирования.

| Источник | Реально принято | Revision | Лицензия и использование |
|---|---:|---|---|
| CC-CEDICT / MDBG | 125 101 | 2026-09-23T10:03:34Z | CC-BY-SA-4.0; весь официальный published dump, build-only китайские формы/пиньинь/EN meanings |
| AGROVOC / FAO | 42 001 | 2026-09-07T10:09:21Z | CC-BY-4.0; поддержанные materialized SKOS ZH/RU/EN полного LOD |
| Wikidata contributors | 14 393 | individual lastrevid в исходных entity и NOTICE; получено 25.09.2026 | CC0-1.0; ограниченный technical subset |

[CC-CEDICT: официальные условия и download](https://www.mdbg.net/chinese/dictionary?page=cc-cedict), [AGROVOC: актуальные условия FAO](https://www.fao.org/agrovoc/maintenance), [AGROVOC releases](https://www.fao.org/agrovoc/releases), [Wikidata structured-data licensing](https://www.wikidata.org/wiki/Wikidata:Licensing). Для AGROVOC использованы текущие условия CC-BY-4.0, а не устаревшее упоминание CC-BY-IGO в прежних FAQ. Другие языки AGROVOC не включались.

SHA256 входов:

Уточнение аудита AW0.7.4: прежние Wikidata API-запросы не включали `props=info`, поэтому individual `lastrevid`/`modified` в этих исходных entities отсутствуют. Снимок AW0.7.3 закреплён полными SHA256 файлов и ответов, но утверждение выше о сохранённых individual revisions для старой выборки неточно. Новые точечные запросы AW0.7.4 требуют `info` и отклоняют ответы без revision; старые исходники не подменены.

- CC-CEDICT gzip: `595a2e44ae73bf8b5c97b9f2f1dbf4e693628fa56e29a283a68246180359f687`.
- AGROVOC официальный ZIP: `dca2c10e1ac797ac6a8f989efbcfd73815b7867892a36ec7d353253e5f618b30`.
- AGROVOC derived JSONL: `d2f6aba1891e8cf09f540f11a3bc9571c3dede80e48c69b251ed8bc7461393bd`.
- Wikidata final JSONL: `fcab62fcbc86e307e31d1824008a6d34d428637af6263b11801174f0a6dce325`.

Wiktionary остался REVIEW_REQUIRED и не получен; WIPO не использован. Источники с неизвестными/неподтверждёнными правами в официальные пакеты не включены. Каталог «О проекте» содержит 207 строк компонентов и ссылки на полные notices; пакетам AGROVOC назначена атрибуция FAO, пакетам Wikidata — Wikidata contributors. Неопределённость прав отдельных Argos EN↔RU весов и изображений явно сохранена: этот этап не выдаёт общее разрешение на распространение всех компонентов приложения.

## Получение и обработка

CC-CEDICT: 125 131 строка (30 служебных/комментариев), 125 101 принятая запись, 0 ошибок. Сохраняются исходные simplified/traditional, пиньинь и English meanings; пиньинь не становится runtime alias.

AGROVOC: ZIP содержит 10 255 762 N-Triples строки. Минимальный build-only конвертер потоково извлекает materialized prefLabel/altLabel ZH/RU/EN, broader и exactMatch в staging SQLite; затем используется прежний adapter. 42 001 concept; preferred EN 42 000, RU 42 000, ZH 41 856; aliases EN 12 796, RU 9 568, ZH 8 646; broader 42 447, exactMatch 36 799. Нематериализованные SKOS-XL определения не объявляются импортированными. Checkpoint, SHA pin и ограничение распакованного размера проверены; resume повторяет декомпрессию префикса, весь граф в RAM не загружается.

Wikidata: официальный API, taxonomy BFS depth 3, cap 1 500 на domain, batches до 50 entities; исходные 664 IDs сохранены как seeds и перечитаны с актуальными revisions. Планы и ответы закреплены в `build/aw073/sources/wikidata-expanded`. Корректный union — `haswbstatement:P279=Q1|P279=Q2`. Первый диагностический запуск с буквальным OR сохранён отдельно и **не включён в harvest DB**. Весь Wikidata dump не скачивался; subset не гарантирует полноту или статистическую репрезентативность. Industrial-safety/electrical остаются небольшими ветвями.

## Linking, trust и покрытие

Canonical concepts: **181 495**, межисточниковых canonical merges в этом запуске **0**. AGROVOC содержит 43 явных Wikidata mappings, но совпадений с выбранными Wikidata IDs не образовалось. Независимое cross-source direct agreement не заявляется.

Cross-source English pivot: **5 854** кандидата (4 704 exact и 1 150 ambiguous), все **REVIEW**, ни один не вошёл в runtime. DIRECT_CONCEPT label стоит у 191 092 кандидатов, включая записи без русской пары: это не число доверенных двуязычных переводов. Исходных записей с прямыми ZH+RU labels: **44 791**. VERIFIED provenance: AGROVOC 893, Wikidata 3 516, CC-CEDICT 0. Полная статистика: [corpus-summary.json](qa/aw073/corpus-summary.json).

ZH присутствует в 171 281 исходной записи; уникальных preferred candidate ZH terms — 161 532. Source-declared Traditional: 127 014 записей; Simplified: 126 988. Эти множества пересекаются и не складываются. 157 369 записей имеют ZH-строку длиной больше одного символа; это техническая метрика длины, **не утверждение о числе технических compounds**. Все runtime варианты происходят из source aliases, без автоматического преобразования письменности.

Score/threshold/базовые trust gates AW0.7.2 не снижены. Expansion policy добавляет проверенные taxonomy roots и ужесточает markers для automotive/electrical по результатам QA. Fingerprint: `d6ef89b6bd77b71221c1d761c473742f0f490e03d7c6246aacad3cc67f297ca5`. Некоторые источники ingest закреплены предыдущим config: для повторного ingest нужен записанный fingerprint или новая DB, а для финальной классификации — expansion policy.

## Counts по областям

Один concept может принадлежать нескольким областям по существующей multi-domain policy. Не classified/agriculture-only слова не форсируются в technical-core. Runtime требует явно выбранную область; general не активирует все отраслевые пакеты сразу.

| Domain | VERIFIED | REVIEW | AUTO | REJECTED | Runtime ZH→RU | Runtime RU→ZH |
|---|---:|---:|---:|---:|---:|---:|
| automotive | 140 | 1067 | 819 | 4 | 140 | 140 |
| chemistry-engineering | 144 | 55 | 1347 | 0 | 144 | 144 |
| computer-hardware | 182 | 241 | 1095 | 66 | 182 | 182 |
| electrical | 38 | 101 | 217 | 0 | 38 | 36 |
| electronics | 315 | 379 | 1625 | 59 | 315 | 313 |
| industrial-safety | 12 | 0 | 4 | 0 | 12 | 12 |
| manufacturing | 145 | 44 | 709 | 1 | 145 | 141 |
| materials-science | 591 | 53 | 1381 | 9 | 589 | 573 |
| measurement | 390 | 111 | 1253 | 1 | 390 | 382 |
| mechanical-engineering | 338 | 196 | 1415 | 2 | 338 | 330 |
| metallurgy | 150 | 57 | 661 | 1 | 150 | 144 |
| software | 344 | 134 | 1019 | 5 | 343 | 341 |
| technical-core | 1620 | 894 | 6215 | 71 | 1620 | 1596 |
| unclassified | 0 | 46994 | 124229 | 3 | 0 | 0 |

## Конфликты, review, dedup

В build DB **4 530 направленных conflict edges**, а не 4 530 уникальных пар. Коллизии ZH/domain и aliases остаются REVIEW. Отдельная очередь cross-domain ambiguity: **762 кандидата**; она не выбирает глобального победителя. Контекст между разными областями пока проверяется выбором domain, экспертная редактура очереди не завершена.

Сборка ZH→RU объединила **3** повторных pair/domain записи; вся provenance осталась в NOTICE. Обратная сборка объединила **2**, отклонила **73** candidate occurrences из-за reverse collision и удержала **3 461** RU alias вне matching. Итоговая проверка всех runtime alias/domain ключей: **0 конфликтов**.

На реальной сборке обнаружены 13 неоднозначных обратных ключей, ранее различавшихся только регистром (например «Пайка»/«пайка»). Исправление ограничено build gate: сравнивается Unicode-normalized/casefold runtime key через временный SQLite-индекс. Это также устраняет полный скан 196 946 candidates для каждой reverse pair. Новый тест воспроизводит кириллическую коллизию; runtime ranking не переписан.

В `build/aw073/review-release/stratified-review.jsonl` — детерминированная выборка до 50 кандидатов на domain, с ZH/RU/EN, score, link type, source и provenance. Отдельно прочитаны 40 VERIFIED примеров из пяти приоритетных областей; [spot-check-notes.json](qa/aw073/spot-check-notes.json) сохраняет находки. Всего 15 candidate occurrences отложены агентом через existing KEEP_AUTO review API: 13 при исходном spot check и 2 после runtime QA. Это не human verification, production labels не редактировались.

Примеры проблем источников: turbocharger/device против «турбонаддув», shaft против «балансировка двигателя», display против backlighting, и 压机 («пресс») против «прокатка». Доменные утечки marine/spacecraft в automotive и powertrain layouts в electrical отсечены дополнительными review markers. Не утверждается, что выборочная проверка нашла все ошибки.

## Automotive QA и обычный текст

Повторён прежний корпус из шести автомобильных предложений через существующий loader → GlossaryEngine → TranslationKnowledgeEngine → реальный M2M100, с baseline backend-only. [Полные before/after](qa/aw073/automotive.json). SHA исходного automotive PDF неизменен.

- 6 сегментов, 0 совпавших терминов, 0 enforced, 0 fallback; before/after одинаковы.
- Существующий автоматический fidelity validator: **2/6 до и 2/6 после**. Это проверка структуры/чисел/ограничений, не экспертная смысловая оценка.
- Из шести отдельно запрошенных терминов найден **冷却剂 → охлаждающая жидкость**; **冷却液, 散热器, 散热器盖, 连接器, 怠速** не получили полного runtime-match в automotive.
- 冷却剂 отсутствует именно в шести исходных предложениях, поэтому отдельное покрытие не означает совпадение в корпусе. 散热器 найден в source candidates, но остался REVIEW; недостающие пары/aliases не добавлялись ради QA.
- Существующие UI/service тесты отдельно проверяют обычный текст 冷却剂 и предложение 更换冷却剂。, domain selector, приоритет подтверждённой TM и отсутствие автоматической записи в user glossary/TM.

## Metallurgy QA

Поиск выполнялся по фактическим EN labels в harvested metallurgy candidates; отсутствие term здесь не доказывает отсутствие всех синонимов во всём источнике. [Полная provenance и примеры](qa/aw073/metallurgy.json).

| Запрошенный term | Найдено candidates | VERIFIED |
|---|---:|---:|
| steel | 8 | 2 |
| alloy steel | 1 | 1 |
| continuous casting | 1 | 1 |
| mold | 0 | 0 |
| tundish | 0 | 0 |
| billet | 0 | 0 |
| slab | 0 | 0 |
| bloom | 0 | 0 |
| ladle | 0 | 0 |
| rolling | 1 | 0 |
| heat treatment | 0 | 0 |

После исключения ошибочного rolling осталось **3** source-derived проверки через реальный M2M100: 钢铁 → сталь, 合金钢 → легированная сталь, 连铸 → непрерывная разливка. Все получили enforced. Предложения «检查…» — синтетические QA-обёртки над реальными терминами, не production corpus. Получены «Проверьте сталь», «Проверьте легированная сталь», «Проверьте непрерывная разливка»: термины подставлены, но падежное согласование не решено существующим placeholder engine. Ошибочный rolling отсутствует в финальных пакетах.

## DEV/BUILD и RUNTIME size

Все размеры ниже в байтах, один зафиксированный локальный снимок. Total build включает сохранённые промежуточные прогоны, диагностический Wikidata cache, review queues и резервную копию AW0.7.2; это не минимально необходимый размер сборки. Подсекции пересекаются и не суммируются повторно.

| Категория | Байты |
|---|---:|
| build_aw073_bytes | 2 160 670 106 |
| harvest_db_bytes | 823 160 832 |
| sources_bytes | 463 553 378 |
| staging_db_bytes | 63 655 936 |
| review_release_bytes | 240 592 210 |
| tglossary_bytes | 3 924 333 |
| runtime_sqlite_bytes | 8 183 808 |
| runtime_total_bytes | 22 930 970 |

Исходники: CC-CEDICT gzip **3 975 790**, распакованный текст **9 851 590**; AGROVOC ZIP **96 365 215**, логический распакованный NT **1 461 478 821** (не хранится отдельным файлом), derived JSONL **19 579 897**; final Wikidata JSONL **116 411 243** плюс pinned API cache/metadata.

Runtime knowledge: **8 183 808** байт SQLite (7.80 MiB), **22 930 970** байт с LICENSE/NOTICE/README/manifest (21.87 MiB). Сжатые 48 `.tglossary`: **3 924 333** байта. В `assets/knowledge` нет source archives, raw tables, harvest DB, staging SQLite, review queues или ZIP `.tglossary`; только окончательные DB и необходимые notices. Здесь измерен knowledge payload будущей поставки; installer в этом этапе не создан и не проверялся.

## Performance

Реальный ingest: CC-CEDICT **20.553 s** / ~6 087 accepted records/s, peak RSS **29 470 720**; AGROVOC после streaming conversion **3.373 s** / ~12 451/s, peak RSS **26 873 856**. Wikidata ingest измерен при исходном запуске: **2.239 s** / ~6 427/s. Эти времена не включают network acquisition или конвертацию полного NT.

На corpus 181 495 raw / 196 946 candidates: reviewed link **56.750 s**, из них conflict scan **2.612 s**; reports **31.995 s**, измеренный peak RSS этого прохода **54 087 680** байт. Финальная сборка после обратного gate: **12.471 s**, prepare SQLite через существующий installer API: **4.685 s**. RSS acquisition, конвертации и реального model runtime не выдается за эти 54 MB. Полный synthetic million-record benchmark не повторялся.

Шесть повторных warm lookup: **244.7 ms** суммарно на этой машине; каждый lookup по-прежнему проверяет revisions нескольких DB. Это наблюдение, не SLA. [Машинные метрики](qa/aw073/expansion-metrics.json).

## Проверки и границы результата

- Все 48 final DB: SHA256, SQLite integrity_check, journal_mode DELETE, ожидаемые row counts; provenance approved, LICENSE соответствует источнику, runtime candidates только VERIFIED DIRECT_CONCEPT.
- Существующий bundled loader открыл все пакеты; выборка до 5 терминов на пакет дала **216/216** успешных lookup. Все alias/domain ключи проверены на коллизии. [Integrity](qa/aw073/integrity.json), [pack manifests/checksums](qa/aw073/packs.json).
- Реальные модельные вызовы проходят через существующий `TranslationRouter.offline_scope`; downloads выполнялись отдельно с явным `--allow-network`. Модели не добавлялись/не менялись. QA user glossary rows = 0, TM units = 0.
- Полный regression: **462 passed in 206.02 s**; все прежние 457 тестов сохранены, добавлены 4 проверки expansion и 1 regression кириллических обратных коллизий. [JUnit](qa/aw073/full-tests.xml).
- `python -m compileall -q app tools` и `git diff --check` выполнены успешно; предупреждения Git LF→CRLF не являются whitespace errors.

Ограничения: preview quality; неполное отраслевое покрытие; source label granularity; 50 326 REVIEW кандидатов; отсутствие доказанного trusted cross-source enrichment; неполное совпадение вариантов китайской письменности; bounded Wikidata traversal; отсутствующее морфологическое согласование. Automotive corpus не улучшен. Массовый импорт и расширение реально выполнены, экспертная редактура всего корпуса не выполнена.

Версия приложения: **AW 0.7.3**, без alpha. Изменения остаются незакоммиченными; [финальный git status](qa/aw073/git-status.txt). AW0.8, fine-tuning, новые модели и installer не начаты.
