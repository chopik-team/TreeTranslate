# TreeTranslate AW 0.7.4 — Cross-source Linking & Knowledge Refinement

Завершение: 27 сентября 2026. Работа начата на существующем AW0.7.3; итоговый regression выполнен 26 сентября, финальные проверки и отчёт закреплены 27 сентября.

## Результат и его границы

Корпус переиспользован без повторного массового ingest: **181 495 → 181 550 raw records**, добавлены только **55 явно связанных Wikidata entities**. Concepts: **181 495 → 181 507**; 43 новых записи вошли в существующие canonical IDs AGROVOC exactMatch. Сравнение всех исходных raw payloads: **0 потерянных или изменённых** — [raw-preservation.json](qa/aw074/raw-preservation.json).

English Pivot V2 расширил retrieval до **16 524 REVIEW pivot-кандидатов** против 5 854 ранее; ещё 8 pivot-кандидатов REJECTED по исключённым классам. **1 387 REVIEW_HIGH** имеют совпадение исходной китайской формы и однозначный найденный target, но это приоритет review, а не proof или автоматический VERIFIED. **2 прямых кандидата повышены, 6 прежних VERIFIED occurrences отложены**. Уникальные VERIFIED ZH/RU пары без domain: **3 041 → 3 038**. Рост доверенного словаря не заявляется.

| Status | AW0.7.3 | AW0.7.4 |
|---|---:|---:|
| VERIFIED | 4,409 | 4,405 |
| REVIEW | 50,326 | 61,082 |
| AUTO | 141,989 | 141,935 |
| REJECTED | 222 | 230 |

Итоговые **48 пакетов / 13 областей**: **4 402 ZH→RU / 4 330 RU→ZH** против 4 406 / 4 334. Статусы кандидатов, уникальные пары и runtime rows — разные метрики; domain repeats не выдаются за новые слова. Runtime knowledge с notices: **22 894 244 байта (21.83 MiB)**.

Главное улучшение — более полный и объяснимый список гипотез, сохранность правильных source aliases и различение доказанной альтернативы от английского предположения. Смысловая корректность всего корпуса человеком не подтверждена. Automotive corpus всё ещё **0→0 matched terms**; это ограничение результата, а не улучшение качества перевода.

## Audit и сохранность

Изучены AW0.7.3 report, source catalog, adapters, linker/scoring/domain logic, review/conflicts, assets, tests/configs/tools, README/CHANGELOG/NEXT_CYCLE, git status/diff. Исходная версия была AW0.7.3. Ветка `codex/next-cycle`, HEAD `9aa36fc327463b5ef11d6d02e40a810207bd5e8f`; работа прошлых этапов уже была незакоммиченной.

До изменений сохранены **1 108 файлов** с SHA256, полный ZIP исходного рабочего состояния и binary diff: `build/aw074/baseline.zip`, `baseline.json`, `baseline.diff`, `baseline-status.txt`. Отсутствующих файлов по baseline: **0**. Прежние payloads находятся в `build/aw074/aw073-runtime`, каждый проверен по исходному SHA. Промежуточные прогоны также сохранены build-only. См. [preservation.json](qa/aw074/preservation.json).

TM, GlossaryEngine, TranslationKnowledgeEngine, Router, Argos/M2M100, OCR, PDF/DOCX, `.tglossary` schema и bundled loader не переписаны. Из `app/` изменены только версия и история выпусков. Пользовательские glossary/TM не заполнялись и не редактировались. EN/RU Dictionary / Usage Examples не изменены.

## English Pivot V2

Расширен существующий linker, а не создан отдельный runtime engine. Временный build SQLite индекс хранит preferred EN, EN aliases и short glosses; raw records остаются исходными. Короткие значения разделяются по `;`, скобочные qualifiers сохраняются вместе с исходной строкой. Например, `(automotive) idling; idle speed` даёт два retrieval term; `radiator (for cooling an engine)` сохраняет qualifier, а не теряет его как будто это универсальный radiator.

На каждую гипотезу записаны исходное EN значение, тип target label, конкурирующие concept IDs, общие ZH формы, domain evidence, общие parent IDs, пересечение definition tokens, признак truncation. Длинные определения не сравниваются fuzzy-метрикой для принятия перевода. English string и definition overlap самостоятельно ничего не переводят в VERIFIED.

Лимиты: 64 значения источника, 64 найденных строки на значение, максимум 128 target concepts; усечение явно помечается и сохраняет неоднозначность. Concepts cache ограничен 512 элементами. Taxonomy для target без RU не обходится повторно. Никаких embeddings, LLM classifiers, model-generated или вручную придуманных production pairs.

Для `driver`, `seal`, `bearing`, `mold`, `cell`, `bus`, `port`, `terminal`, `current` новые tests подтверждают: несколько подходящих concepts не превращаются в первого выбранного победителя. REVIEW_HIGH требует дополнительного source-declared Chinese evidence; даже он остаётся REVIEW. Все прежние threshold/weights/exclusions/license settings сохранены и сравниваются тестом с AW0.7.3; конфигурация отличается только `pivot_version: 2`.

## Aliases, Chinese scripts и compounds

Исправлена конкретная ошибка прежнего pivot: он объединял китайские варианты исходного **и целевого** понятий. Теперь source ZH aliases принадлежат только source record, RU aliases — target records. Иначе, например, похожее английское слово могло внести чужое китайское написание и создать искусственные коллизии. Тест проверяет отсутствие такого переноса.

Source-declared `zh-hans`, `zh-hant`, `zh-cn`, `zh-tw`, original preferred и aliases сохраняются. Ни OpenCC, ни другая script conversion не добавлялись. Pinyin остаётся metadata; compounds не дробятся для увеличения совпадений. Longest-match runtime не менялся. Метрики ниже относятся к исходным записям и preferred candidate terms; Simplified/Traditional множества пересекаются.

| Coverage metric | AW0.7.3 | AW0.7.4 |
|---|---:|---:|
| raw_with_zh | 171,281 | 171,329 |
| raw_direct_zh_ru | 44,791 | 44,839 |
| source_declared_traditional | 127,014 | 127,042 |
| source_declared_simplified | 126,988 | 127,017 |
| chinese_compound_records | 157,369 | 157,417 |
| unique_candidate_zh_terms | 161,532 | 161,567 |
| unique_verified_pairs | 3,041 | 3,038 |

`chinese_compound_records` — только длина ZH больше одного символа, не экспертная классификация технических compounds.

## Targeted mappings и provenance

Из локальных AGROVOC exactMatch получены **43 отсутствовавших QID**. Для source-derived QA concepts дополнительно получены **12 отсутствовавших непосредственных P31/P279 родителей**. Список фиксируется до сети; новые полученные parents дальше не обходятся. Весь Wikidata dump или новая taxonomy crawl не запускались.

Финальный source: `wikidata-explicit-f4f42f93e368defe`. Получено 55/55, missing 0, ingest errors 0. JSONL **3 210 411** байт, SHA256 **`f4f42f93e368defe3a8fca94a5c65a9cb43c5211087764dbea6c5c82ce6e7c0f`**. План содержит QID→исходный source/record/hash/relation; cached API responses, per-entity lastrevid/modified и SHA сохранены. [targeted-source.json](qa/aw074/targeted-source.json); raw файлы — `build/aw074/targeted-final/`.

Выявлен прежний provenance gap: запросы AW0.7.3 не включали `props=info`, поэтому individual revisions отсутствовали, несмотря на формулировку прошлого отчёта. Старые данные всё ещё точно закреплены source/file SHA, но нельзя выдавать их за per-entity revision pinning. В старый отчёт добавлено уточнение; старые файлы не подменены. Acquisition tools теперь запрашивают info; targeted output без lastrevid отклоняется. Ранние ответы AW0.7.4 без info сохранены как промежуточные и не входят в финальную DB, созданную заново копированием AW0.7.3.

Wikidata CC0 подтверждён повторно 26.09.2026 по [официальной политике](https://www.wikidata.org/wiki/Wikidata:Licensing). Использованы прежние CC-CEDICT CC-BY-SA-4.0, AGROVOC ZH/RU/EN CC-BY-4.0 и Wikidata CC0; иных источников/лицензий нет. Пinned source metadata сохраняют исходную дату проверки 25.09.2026, повторная проверка не переписывает metadata. UNKNOWN/REVIEW_REQUIRED/NOT_REDISTRIBUTABLE и mixed-license gates сохранены. В «О проекте» обновлены фактические counts и notices, 207 component rows; прежние неопределённости по отдельным моделям/изображениям не скрыты.

Фоновый API отвечал maxlag; эти ответы сохранены. Для ограниченного интерактивного запроса использован явный `--interactive` согласно [MediaWiki maxlag etiquette](https://www.mediawiki.org/wiki/Manual:Maxlag_parameter), разрешающему omission при ожидающем пользователе. Сеть всегда требует `--allow-network`; background default остаётся maxlag=5, retry delay не менее 5 s.

## Cross-source agreement, tiers и trust

Зафиксированы **52 группы совпадающих прямых ZH/RU пар** от разных `independence_group`. Это evidence для review, не автоматическое объединение разных concepts. Зеркала одной группы не увеличивают независимость. Новые mapped Wikidata записи имеют ту же группу `wikidata`.

Финальный breakdown: DIRECT_CONCEPT VERIFIED **4 405**; CROSS_SOURCE_CONCEPT **58, все REVIEW**; English exact pivot **2 316 REVIEW**; ambiguous pivot **14 208 REVIEW + 8 REJECTED**. Mapping разных лицензий и несовпадение preferred labels не исчезают из gate после получения QID. Из новых explicit mappings не заявляется прирост доверенных технических переводов.

Высокоприоритетных REVIEW_HIGH **1 387**, REVIEW_AMBIGUOUS **15 137**; остальные REVIEW — прямые/explicit-mapped кандидаты, не прошедшие классификацию, лицензионные или конфликтные условия. Human verified = **0**. Существующие 15 агентских deferral decisions AW0.7.3 сохранены, включая rolling/压机; они не считаются человеческим подтверждением.

## Уточнение конфликтов и переходы статусов

Английское retrieval-предположение отличается от альтернативы, реально названной по-китайски в target source. Для `retrieval_only_challenge` нет общего source-declared ZH между исходным и целевым concept. Такая гипотеза остаётся REVIEW и видна в conflict graph, но не отменяет direct relation самостоятельно. Direct-vs-direct, альтернативы с подтверждённым ZH, scope/license restrictions и реальные source-alias collisions по-прежнему блокируют VERIFIED. Это refinement типа evidence; score threshold и правила принятия самого pivot не ослаблены.

Конкретный пример: English `tin` предлагал для 马口铁 «олово», хотя прямой источник давал «белая жесть», а target concept не называл себя 马口铁. Принимать «олово» или объявлять этим исходную пару ошибкой было бы выводом только из English string. Гипотеза сохранена для review, прямая запись сохраняет свой исходный trust.

**Два повышения REVIEW→VERIFIED** имеют уже существовавшие direct/taxonomy доказательства с score 95:

- 化学工程 → «химическая инженерия», chemistry-engineering, AGROVOC root c_9752.
- 製程 → «производственный процесс», manufacturing, Wikidata Q1408288.

Они освобождены от неподтверждённого retrieval-only challenge; новые русские переводы не сочинялись. **Шесть понижений VERIFIED→REVIEW**: 气压计 (measurement и technical-core), 自行车, 喷雾器, 轭, 软管 (technical-core). Там есть source-attested Chinese alternative, расхождение target label/числа либо mixed-license provenance. Например «барометры»/«барометр» не сливаются новым morphology engine; 轭 имеет competing «хомуты»/«штурвал самолёта». Это шесть случаев для review, не шесть доказанных человеком ошибок. [Все причины](qa/aw074/demotions.json).

Первый диагностический прогон с широким блокированием всех pivot отложил 133 occurrences. Классификация evidence сохранила 127 из них и добавила 2 повышения других direct records; окончательное сравнение с AW0.7.3 — **2 вверх / 6 вниз**, а не промежуточные числа. [refinement-summary.json](qa/aw074/refinement-summary.json) содержит полную матрицу переходов.

Общее число directed edges: **4 530 → 9 506**, из них **2 060 retrieval-only directed edges**, сохраняемых для проверки. Больше гипотез порождает больше review relations; это не рост числа доказанных семантических ошибок. Парные категории ниже считались один раз (`candidate < other`), остальные строки — отдельные ключи/группы и не складываются с ними:

| Category | Count |
|---|---:|
| retrieval_only_challenge | 1030 |
| alias_collision | 340 |
| semantic_ambiguity_requires_review | 3370 |
| case_normalization_collision | 13 |
| duplicate_provenance_pairs | 2961 |
| domain_separation_keys | 1268 |
| reverse_only_collision_keys | 36 |

`semantic_ambiguity_requires_review` означает потенциальное смысловое расхождение, требующее редактора. `duplicate_provenance_pairs` — группы одинаковых pair/domain с несколькими candidate IDs, не автоматическое доказательство тождества concepts. Case collisions выделены отдельно. Reverse-only неоднозначности отсекаются существующей Unicode-normalized/casefold политикой RU→ZH, RU aliases не включаются без доказанной безопасности.

## Domain refinement

Положительные English keywords теперь ограничены границами слов и простым множественным числом: `car` не совпадает с `carbohydrate`, `electronic` допускает `electronics`. Строгие AW0.7.3 domain review markers сохранены, включая compounds `lightships/lifeboats/baitboats`. General/technical-core не получает всех неизвестных terms. Target-domain evidence у pivot помечено review-only и не выдаётся за собственную source taxonomy.

По ходу QA обнаружены и исправлены повреждение Unicode при генерации черновой policy и недостаточно строгие границы scope markers. Черновые результаты не включены в финальные пакеты. Тест гарантирует точное равенство всей policy AW0.7.3, кроме переключателя V2. Прежние marine/spacecraft и powertrain scope exclusions сохранены; hardcoded исключений отдельных production строк не добавлено.

| Domain | VERIFIED до | VERIFIED после | REVIEW после | Runtime ZH→RU | Runtime RU→ZH |
|---|---:|---:|---:|---:|---:|
| automotive | 140 | 140 | 1350 | 140 | 140 |
| chemistry-engineering | 144 | 145 | 109 | 145 | 145 |
| computer-hardware | 182 | 182 | 732 | 182 | 182 |
| electrical | 38 | 38 | 330 | 38 | 36 |
| electronics | 315 | 315 | 915 | 315 | 313 |
| industrial-safety | 12 | 12 | 4 | 12 | 12 |
| manufacturing | 145 | 146 | 186 | 146 | 142 |
| materials-science | 591 | 591 | 1396 | 589 | 573 |
| measurement | 390 | 389 | 477 | 389 | 381 |
| mechanical-engineering | 338 | 338 | 1042 | 338 | 330 |
| metallurgy | 150 | 150 | 146 | 150 | 144 |
| software | 344 | 344 | 576 | 343 | 341 |
| technical-core | 1620 | 1615 | 3394 | 1615 | 1591 |
| unclassified | 0 | 0 | 50425 | 0 | 0 |

После пересоздания производной проекции **4 338 старых candidate IDs отсутствуют**, поскольку изменились наборы/виды pivot targets и keyword domains; это не удаление raw records. Все 181 495 старых source payloads сохранены точно. Новые candidate IDs, старые повышения/понижения и новые raw entities считаются отдельно.

## High-value review

[high-value-review.jsonl](qa/aw074/high-value-review.jsonl) содержит **1 000** ranked REVIEW/AUTO кандидатов: ZH, source-declared simplified/traditional, RU alternatives, EN meanings, domain, sources, link/domain evidence, score, conflict IDs/types и причины review. Полная очередь находится только в `build/aw074/review-proof/review-queue.jsonl`.

Порядок: запрошенные automotive QA terms → automotive → metallurgy → mechanical → electronics/electrical → прочие; внутри учитываются source record occurrences, independent agreement, REVIEW_HIGH и score. Число source occurrences не называется пользовательской частотой употребления. Скриптовые поля у pivot ограничены формами source term, чужие target ZH variants туда не переносятся. Ни один просмотренный агентом sample не помечен human verified.

## Automotive: причины по терминам

Исследованы исходные labels, aliases, glosses и candidate evidence, включая упоминания внутри compounds. Упоминание в compound/definition не означает допустимый alias общего термина. [Полные записи и причины](qa/aw074/automotive-gaps.json).

| Term | Что реально найдено | Почему / итог |
|---|---|---|
| 冷却液 | Нет source-declared формы в собранном корпусе | Нельзя добавить как alias 冷却剂 из знаний агента; runtime match отсутствует |
| 冷却剂 | CC-CEDICT и Wikidata Q1056832; 冷卻劑 сохранён | Direct «охлаждающая жидкость» VERIFIED в automotive; CC-CEDICT pivot остаётся REVIEW |
| 散热器 | CC-CEDICT с двумя radiator glosses; Wikidata Q1163026 с RU «Радиатор автомобиля» | V2 находит EN alias `radiator`, но automotive не подтверждён taxonomy: родитель vehicle component включает также суда/авиацию. Keyword-only score 75 не достигает 90; REVIEW. В mechanical контекст иной |
| 散热器盖 | Нет source-declared compound | Нельзя придумать «крышку радиатора» для прохождения QA; полного match нет |
| 连接器 | CC-CEDICT и Wikidata Q18819626; в других raw есть специализированные compounds | Общему Wikidata concept недостаёт RU; electrical/другие pivot senses неоднозначны и не превращаются в automotive preferred term |
| 接头 | CC-CEDICT `connector; joint; coupling` | Полисемия; среди automotive hypotheses есть «Автосцепка», но это не доказательство общего эквивалента, REVIEW |
| 怠速 | CC-CEDICT `(automotive) idling; idle speed` | V2 разбирает значения; в собранных target concepts нет доказанной RU связи, direct остаётся AUTO |

Повторены те же **6** automotive предложений через existing bundled loader → GlossaryEngine → TranslationKnowledgeEngine → реальный M2M100 в offline scope. Сравнение AW0.7.3/AW0.7.4: matched terms **0/0**, enforced **0/0**, fallback **0/0**, автоматический structural fidelity **2/6 → 2/6**, тексты результатов одинаковы. Из отдельно проверенных шести terms полностью покрыт только 冷却剂; он не встречается в самих шести предложениях, где нужен 冷却液. [before/after](qa/aw074/automotive-comparison.json), [предложения](qa/aw074/automotive.json). Fidelity здесь проверяет ограничения/структуру, не является экспертной смысловой оценкой. SHA исходного PDF неизменен.

## Metallurgy source coverage и реальная модель

Source matches ниже — exact normalized preferred/alias/short-gloss retrieval по запрошенному EN, включая форму с `s`; это не количество переводов и не подтверждение металлургического смысла. Кандидаты/VERIFIED относятся к существующей metallurgy domain. [Исходные labels/aliases/relations](qa/aw074/metallurgy-source-coverage.json), [полный QA](qa/aw074/metallurgy.json).

| Term | Source records | ZH/RU candidates в metallurgy | VERIFIED |
|---|---:|---:|---:|
| steel | 7 | 12 | 2 |
| alloy steel | 1 | 1 | 1 |
| continuous casting | 2 | 2 | 1 |
| mold | 14 | 0 | 0 |
| tundish | 1 | 0 | 0 |
| billet | 3 | 0 | 0 |
| slab | 8 | 0 | 0 |
| bloom | 3 | 0 | 0 |
| ladle | 9 | 0 | 0 |
| rolling | 4 | 2 | 0 |
| heat treatment | 1 | 0 | 0 |

`mold` конкурирует с плесенью/формой, `billet` — с должностью/размещением, `slab` — с древесиной/плитой, `bloom` — с растительным налётом, `ladle` — с бытовой ложкой. Tundish найден как EN-only entity без доказанной ZH/RU пары. AGROVOC heat treatment — 热处理/«тепловая обработка» в broader processing, что не доказывает metallurgy-specific sense. AGROVOC rolling относится также к обработке почвы; прежняя ошибочная preferred пара 压机/«прокатка» остаётся отложенной review decision.

Реальная модель применила три source-derived canonical terms: 钢铁→«сталь», 合金钢→«легированная сталь», 连铸→«непрерывная разливка», **3 enforced**. QA-обёртки «检查…» синтетические и не добавлены в production data. Результаты «Проверьте легированная сталь» и «Проверьте непрерывная разливка» по-прежнему грамматически несогласованы; morphology не реализовывалась, согласно границе этапа.

## Пакеты, runtime и размеры

48 `.tglossary` собраны существующим builder и установлены в readonly SQLite через прежний prepare API. **4 405 VERIFIED occurrences → 4 402 forward rows** после dedup; **4 330 reverse rows** после collision gate. Контрольные суммы/manifest: [packs.json](qa/aw074/packs.json). Пакеты имеют прежний формат, LICENSE и полную candidate provenance в NOTICE; в assets нет raw archives, harvest/staging DB или review queues.

| Payload | AW0.7.3, байты | AW0.7.4, байты |
|---|---:|---:|
| `.tglossary` total | 3 924 333 | 3 923 003 |
| Runtime SQLite | 8 183 808 | 8 155 136 |
| Runtime knowledge со всеми notices | 22 930 970 | 22 894 244 |

BUILD-only локальный снимок, категории пересекаются и не суммируются повторно:

| Category | Bytes |
|---|---:|
| build_aw074_bytes | 3,233,035,822 |
| final_harvest_db_bytes | 890,650,624 |
| final_review_artifacts_bytes | 328,768,267 |
| targeted_acquisition_bytes | 6,479,741 |
| original_runtime_archive_bytes | 22,930,970 |
| baseline_zip_bytes | 24,213,959 |

Build total включает сохранённые черновые DB/queues, baseline ZIP, API retries и оба поколения payloads. Это не размер будущего installer и не минимальная стоимость сборки. Пользовательские TM/glossary находятся отдельно; QA подтвердил 0 автоматически созданных units/rows.

## Performance и проверка

На **181 550 raw / 181 507 concepts / 207 652 candidates** окончательный link занял **123.775 s**, примерно **1466 concepts/s**. Peak RSS всего measured link/report процесса **109,137,920** байт. Corpus report **38.193 s**, review/conflict prioritization **11.501 s**; отдельно conflict taxonomy **0.423 s**. Повторный full ingestion benchmark не запускался.

Pack rebuild **11.754 s**, prepare **4.849 s**. Шесть warm lookup **194.0 ms** суммарно; runtime structure не менялась. Targeted lookup — две API пачки на фиксированные 55 IDs; стеночное время вместе с сетью/maxlag не выдаётся за throughput локального linker. [metrics.json](qa/aw074/metrics.json).

- Все **48/48** DB прошли integrity_check, SHA256, journal_mode DELETE, row counts и provenance/license validation.
- Все runtime alias/domain keys проверены: **0 коллизий**. Loader/GlossaryEngine sample: **218/218** lookup. [integrity.json](qa/aw074/integrity.json).
- Реальные model calls работали в существующем `TranslationRouter.offline_scope`; original PDF не изменён. Обычный текстовый UI/service, shared domain selector и TM precedence проверяются прежними тестами.
- Полный окончательный regression: **484 passed**, 0 errors / failures / skipped, **156.388 s**. Это 462 прежних теста и 22 новых. [JUnit](qa/aw074/full-tests.xml).
- Финальные `python -m compileall -q app tools` и `git diff --check`: **exit code 0**. [validation.json](qa/aw074/validation.json).

## Ограничения и остановка

Refinement не доказал общего улучшения перевода и не дал массового перевода REVIEW/AUTO в VERIFIED. Доказано более полное retrieval/evidence, две обоснованные смены статуса прямых кандидатов, сохранение неподтверждённых гипотез вне runtime и разбор конкретных automotive gaps. Большая часть CC-CEDICT не имеет доказанного RU concept link; 61 082 REVIEW требуют дальнейшей работы, corpus coverage/границы sense и mixed-license families остаются ограничением. Никакого ручного LLM заполнения недостающих terms не было.

Версия **AW 0.7.4**, без `-alpha`. Git остаётся с незакоммиченными изменениями; auto commit/reset/revert/delete не выполнялись. AW0.7.5 EN/RU Dictionary, AW0.8, morphology, fine-tuning, новые translation models и installer **не начаты**.

Итоговый снимок рабочего дерева: [git-status.txt](qa/aw074/git-status.txt). Существующие незакоммиченные изменения сохранены; исходное состояние доступно в baseline ZIP.
