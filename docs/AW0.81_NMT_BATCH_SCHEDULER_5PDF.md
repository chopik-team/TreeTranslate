# AW0.81 NMT SEMANTIC BATCH SCHEDULER — FIXED5

## 1. Fixed5 sample

**NMT SCHEDULER REJECTED на обязательном native replay gate. Production восстановлен точно.** Из сохранённой telemetry `736fc7a72805` выбраны уникальные максимумы CT2 calls/time/short batch1/backend transitions и mixed-OCR NMT. Категории: 56,82,76,64,49; canonical order: **49,56,64,76,82**. Ровно пять PDF, 27 source pages. Manifest заморожен; исходный большой ZIP и 49 Knowledge DB неизменны. Один baseline `2bf4fd0f345e`, без warmup/ресурсных caps: **350.89s; 3 TRANSLATED, 2 FAILED_SOURCE_PRESERVED, 0 fatal**. Старый `/100` console label у наследованного helper был только меткой: scanner проверил ровно 5; повтор baseline не делался.

## 2. Why batch1 happens

Trace: segment → direct Knowledge/TM lookup → protected representation/Glossary → Router fixes backend/languages/options → synchronous Runtime/CT2 → placeholder restoration/guards → retries/fallback → next segment. Следующий model request ещё не существует во время текущего inference. 1044 CT2 calls, все batch1; median 12 tokens. Resident reuse работает; это не задача нового model cache.

## 3. Scheduler design

Разработан и проверен прототип bounded intra-document continuations. Один активный semantic owner, один GPU execution owner; suspended stacks хранят исходные protected планы, broker получает immutable envelope. Пул максимум 8; no cross-document semantic concurrency, no artificial fill wait. Архив `rejected_prototype.zip` содержит код и 20 scheduler tests. После отказа все четыре изменённые production files восстановлены по SHA baseline; добавленный runtime module удалён из production. Никакие остальные оптимизации не внесены.

## 4. Safe batch frontier

Первый routed model attempt приостанавливался ДО mutable circuit check. Совпадали backend/model/device/languages/все frozen options; short source ≤32 pieces, batch ≤8/256 tokens/1MiB prepared estimate. Guards, retries, fallback и known-only result guards проходили canonical commit barrier. Capability planner снижал ceiling 8→4→2→1. Эти структурные гарантии оказались недостаточными: native outputs меняются при batch shape. Точная причина на уровне CUDA kernels не установлена; совпадение настроек не доказывает exactness.

## 5. Before → after NMT metrics

| Metric | Before | After | Gain |
|---|---:|---:|---:|
| Wall, s | 350.89 | N/A | N/A |
| Attempted docs/hour (all five) | 51.30 | N/A | N/A |
| Semantic Runtime requests | 1044 | N/A | N/A |
| Physical CT2 calls | 1044 | N/A | N/A |
| batch1 | 1044 | N/A | N/A |
| batch2 | 0 | N/A | N/A |
| batch3–4 | 0 | N/A | N/A |
| batch5–8 | 0 | N/A | N/A |
| Average sequences/call | 1.00 | N/A | N/A |
| Median sequences/call | 1.00 | N/A | N/A |
| Max sequences/call | 1 | N/A | N/A |
| Source tokens | 12344 | N/A | N/A |
| Average tokens/call | 11.82 | N/A | N/A |
| Median tokens/call | 12.00 | N/A | N/A |
| p90 tokens/call | 20 | N/A | N/A |
| CT2 inference, s | 123.71 | N/A | N/A |
| model_translation inclusive, s | 134.88 | N/A | N/A |
| M2M requests | 1009 | N/A | N/A |
| Argos requests | 35 | N/A | N/A |
| Fallback attempts | 17 | N/A | N/A |
| Failure attempts | 18 | N/A | N/A |
| Real CT2 model loads | 13 | N/A | N/A |
| M2M resident reuse | 1004 | N/A | N/A |
| GPU average, device-wide % | 47.94 | N/A | N/A |
| VRAM peak, MiB | 5903.00 | N/A | N/A |
| CPU average, process-tree % | 113.24 | N/A | N/A |
| RSS peak, GiB | 3.84 | N/A | N/A |
| OCR inference, s | 64.47 | N/A | N/A |
| OCR recognize inclusive, s | 157.14 | N/A | N/A |
| Glossary lookup, s | 56.96 | N/A | N/A |
| Writer pdf_write inclusive, s | 19.70 | N/A | N/A |

After отсутствует: unsafe patch не допущен к PDF benchmark. Native replay использовал **994 captured short CUDA M2M requests** с исходными token arrays, `int8_float16`, threads8, beam4 и неизменными decoding/token options. Один excluded native warmup; не PDF warmup. Replay не является whole-pipeline ускорением.

| Replay batch | CT2 calls | Inference s | Hypothesis differences | Decoded text differences | Exact |
|---|---:|---:|---:|---:|---|
| 1 | 994 | 118.095 | 0 | 0 | PASS |
| 2 | 497 | 72.122 | 26 | 26 | FAIL |
| 4 | 249 | 44.926 | 50 | 50 | FAIL |
| 8 | 125 | 24.920 | 78 | 78 | FAIL |

Старый PASS на 64 requests не распространяется на эту более широкую выборку. Batch16 не запускался. Статистика physical-call reduction и replay time reduction сохранена в `batch_replay.json`; production batched-request fraction и semantic_requests/CT2_call after — N/A.

## 6. Before → after wall

Baseline **350.89s (5.85min)**. Final **NOT RUN**: пользователь разрешил его только после принятой реализации и exact replay PASS. Gate FAIL означает, что запуск с этим scheduler нарушил бы frozen contract. No-op final на восстановленном baseline не создавался. Overall ≥8%/≥15% gain не измерен, не заявляется. Всего 1 baseline, 0 final, 0 новых 20/100/full-corpus benchmark runs.

## 7. Equivalence

**FAIL до финального PDF benchmark.** Batch1 совпал со всеми 994 captured native outputs. Batch2/4/8 дали 26/50/78 hypothesis differences. Пример batch2: `Сигнал на железе.` → `Сигнал на железе`. Есть лексические изменения и перемещения protected placeholder, а не только пунктуация. Full PDF statuses/OCR/glossary/candidates/writer/render/path/CRC equivalence прототипа **не оценивалась**, PASS ей не присваивается. Baseline captures сохранены для всех этих будущих сравнений. Production exact baseline SHA восстановлен; source/sample/Knowledge SHA сохранены.

## 8. Failures/fallback invariance

Прототип: **51 targeted PASS**, 20 новых scheduler cases +31 существующих runtime/pipeline tests, 33.20s. Проверены failing neighbor, original singleton replay, confirmed device breaker, serial guard retry, Unicode/IDs/numbers/placeholders, mixed lengths, empty/noise, near token limit, cancellation before/native/preparation wait, deterministic order, depth1/2 contexts, CPU/low VRAM/pressure и known-only guard barrier. Это protocol tests с контролируемыми backend outputs, не доказательство native exactness. Реальные before→after failure/fallback counts не заявляются без final. Production breakpoint/fallback code вернулся к baseline. Добавлен fail-closed benchmark gate и шесть его regression tests.

## 9. Resource use

Baseline CPU average **113.2%** process tree (100%=1 logical core), GPU average **47.9%** device-wide; RSS peak **3.84GiB**, VRAM peak **5903MiB**. One-second observations; after N/A. OCR inference 64.47s; parent recognize inclusive 157.14s; glossary lookup 56.96s; writer pdf_write inclusive 19.70s. Nested stages не суммируются как exclusive wall.

## 10. Full pytest

На восстановленном production: **1269 passed, 0 failures, 0 errors, 0 skipped**, 338.38s. Production SHA до/после совпадают и точно равны baseline; Knowledge/models/settings тоже frozen. Новый quality/performance code не активирован. Prototype tests сохранены в архиве; шесть новых replay-gate tests включены в full suite.

## 11. Remaining bottleneck

Baseline synchronous native CT2 123.71s = 35.26% wall. Полное массовое batching на текущих model/options не удовлетворяет exact-output контракту. OCR, glossary, writer только измерены, без изменения. Нельзя переносить replay acceleration на общий ZIP или прогноз 17211 PDF. Модель, quantization или decoding для восстановления batch exactness не менялись; новые работы не начаты.

## 12. Verdict

**NMT SCHEDULER REJECTED.** Это законченный эксперимент с отрицательным результатом обязательной приёмки; безопасный production сохранился. Performance optimization не принята, whole-pipeline speedup отсутствует. QA содержит все восемь требуемых central artifacts и архив прототипа. Final не выполнен по указанной выше prerequisite, не объявляется выполненным. STOP. No AW0.82, new resource modes, quality edits, document-failure fixes or commits.
