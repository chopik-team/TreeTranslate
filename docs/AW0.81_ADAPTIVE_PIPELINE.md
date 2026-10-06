# AW0.81 — Adaptive Pipeline / Scheduler

## 1. Current serialization root cause

ArchiveJob раньше выполнял child целиком до следующего member. PDFium защищён общим PDF_LOCK; prepare включает OCR, поэтому native extraction/OCR и PDF writer одного процесса одновременно небезопасны. RuntimeManager уже ограничивает lock inference/lifecycle; окружающие Knowledge/guards не входят в этот lock. Архитектурная карта до изменений: `qa/aw081/adaptive_pipeline/baseline.json`.

## 2. Safe stage boundaries

Существующий DocumentJob разделён на generator boundaries: prepared detached IR → существующие resolve/profile/snapshot/prefetch/translation/guards → destination → существующие write/validate/publication. Child.run параллельно не вызывается: mutable KnowledgeRouter/job_depth остаётся у semantic owner. В pipeline повторное открытие cached PDF заменено передачей первого detached IR; full source/output equivalence подтверждена. DOCX/PDF используют те же методы перевода и writer.

## 3. Hardware-aware planner

CPU logical/physical, total/available RAM, CUDA/free VRAM, resident OCR/NMT reserves и pressure задают только execution ceilings. Production proven depth ceiling = 2; при CPU/RAM/VRAM pressure — serial depth1. Один prepare, один semantic owner, один writer; OS headroom и RAM reserve сохраняются. Synthetic A/B/C/D, negative/zero/pressure/monotonic bounds проверены; quality parameters одинаковы. Capabilities и ceilings: `pipeline_plan.json`.

## 4. Queue/backpressure architecture

Bounded admission window удерживает lease до canonical commit, включая failed documents: максимум depth документов/futures, готовые IR и ожидающие результаты входят в тот же budget. В writer максимум один running + один queued. Для каждого member есть estimate (`max(32 MiB,16×source size)`), measured detached IR и sequence_id. Предельный concurrent budget 3.19 GiB; фактический estimate high-water 64.0 MiB, IR high-water 18.5 MiB. Oversized input изолируется; неожиданно большой IR освобождается и обрабатывается serial после drain readers. Это budget detached work, не общий RSS/backend allocator cap.

## 5. Lock changes

PDF_LOCK, OCR runtime и NMT RuntimeManager locks не менялись. Один GPU admission owner охватывает OCR before_ocr/release_models и весь semantic translation turn; перевод не требует PDF_LOCK. Diagnostic SQLite connection теперь check_same_thread=False под общим RLock, как и её streams/pending/counters; отдельные ContextVars передаются между стадиями последовательно. Glossary SQLite/thread scope не менялся. Writer получает один собственный doc; FontResolver локален, font_bytes cache immutable. На cancel/fatal остановка admission, cooperative control.cancel, join обоих workers, cleanup, затем существующая atomic archive policy.

После measured run исправлены две аварийные ветки: extraction до создания SourceFile сохраняет исходный global exception вместо AttributeError; post-preflight pipeline помечается как document work для ARCHIVE_IO diagnostics. Все 20 measured members имели SourceFile, fatal=0, поэтому guard не меняет ни одну измеренную ветку перевода/записи. Targeted injected BadZipFile/DocumentError и full pytest проверили final revision. Measured и final hashes отдельно сохранены в `post_measurement_repair.json`; дополнительного fixed20 не было.

## 6. Mini depth benchmark

Одна fixed6 subset из исходной fixed20, индексы 0/1/2/3/13/19: OCR/native/medium/heavy, успешные и failed. Excluded warmup и MID options сохранены; максимум четыре mini runs, depth4 не запускался.

| Depth | Wall, s | Translated docs/h | CPU, % одного logical CPU | GPU device, % | Peak RSS tree, GiB |
|---|---:|---:|---:|---:|---:|
| depth1 | 166.42 | 108.2 | 128.2 | 43.2 | 3.46 |
| depth2 | 163.87 | 109.9 | 129.4 | 45.1 | 3.16 |
| depth3 | 164.18 | 109.7 | 130.3 | 44.6 | 3.50 |

Выбран depth2: depth3 относительно depth2 -0.19%. Все три controls равны по candidates, writer, fingerprints/render, full source contracts, profiles и ZIP order. Первоначальный FAIL profiles был только tuple/list mismatch QA observer; сохранённые JSON совпали, повторного benchmark не было. OPTIONAL EASY_FIRST использует только size, archive context остаётся из canonical inventory, names/collision slots распределяются в canonical commit order, включая writer failures. Короткий initial writer turn перед тяжёлым speculative OCR сохраняет early readiness: 39.32 → 3.16 s (12.5×). Outputs/context/order совпали; production default ORIGINAL, UI option не добавлена. Это readiness внутреннего child, финальный ZIP публикуется целиком.

## 7. Fixed20 before → after

Ровно один ORIGINAL measured fixed20: reference 07e4d3b8a299 → 1cca0a6c2a1f. Wall **451.46 → 452.60 s**, reduction **-0.25%**. Translated docs/h 127.6 → 127.3; source pages/h 311.0 → 310.2. 16 TRANSLATED / 4 FAILED_SOURCE_PRESERVED / 0 fatal.

Active document seconds median/p90/p95: 10.81/53.32/89.93 → 24.47/77.30/94.20; pipeline waits могут входить в latency. Stage times inclusive, не складывать: pdf_write может включать ожидание PDF_LOCK.

| Stage | Before, s | After, s |
|---|---:|---:|
| ocr_recognize | 87.40 | 176.46 |
| glossary_lookup | 66.89 | 76.46 |
| model_translation | 206.72 | 209.61 |
| pdf_write | 42.79 | 100.64 |
| pdf_page_layout_write | 13.98 | 15.90 |
| template_routing | 21.76 | 23.94 |

## 8. Resource utilization before → after

CPU process tree avg 125.5% → 126.4% (100% = один logical CPU). GPU device avg 51.6% → 49.7%; RSS tree peak 3.72 → 3.90 GiB; VRAM device peak 5.83 → 5.89 GiB. GPU telemetry включает другие приложения.

Pipeline depth 2; in-flight/ready/writer high-water 2/2/1 (writer включает running). Translation owner waiting ready 104.89 s; admission idle waiting ready, без OCR-owned intervals 18.85 s; prepare admission blocked full/budget 450.42 s; writer waiting work 348.76 s; archive waiting canonical result 13.05 s. Эти counters описывают scheduler ownership/waits, не CUDA kernel utilization; точный physical GPU idle из них не выводится. Evidence: `pipeline_metrics.json`.

## 9. Equivalence

**PASS**: все 20 statuses; полные OCR source contracts (text/bbox/confidence/order/polygon/model); ordered glossary lookup matches/selected terms/encoded constraints и raw preselection replay; candidates; preserved segments/IDs/numbers; profiles/snapshot signatures; page counts/normalized PDF objects/four fixed first-last render probes; final paths/directories; exact failed source bytes/path; ZIP inventory/order/CRC; source SHA. OCR resident loads = 2. Frozen OCR, Glossary, Knowledge, NMT, Router/guards, writer и UI hashes прежние; 49 dictionary databases прежние. `output_equivalence.json`, `lookup_equivalence.json`, `final_audit.json`.

## 10. Remaining bottleneck

NMT/Knowledge остаются существенными стадиями; PDF_LOCK сериализует OCR/native prepare с PDF writer. Более глубокая очередь сама по себе не решает эту границу. Большой speedup не заявляется, если wall reduction ниже 15%. Общий archive/semantic owner также может задерживать canonical append до завершения очередного semantic turn. Реальное масштабирование на 100 PDF в этом этапе не измерялось.

## 11. Full pytest

1248 passed / 0 failed / 0 errors / 0 skipped; 321.90 s. Production hashes до/после совпали (256 files). Targeted race/ownership/recovery tests, slow writer, reversed completion, original and translated collisions, pressure, GPU admission, pause/cancel nonempty queues, stage/append failures, depth1 PDF equivalence PASS. Runtime workers после QA = 0; test TM пуст. Изменены только пять файлов document orchestration/diagnostics; новая UI/quality configuration отсутствует.

## 12. Verdict

**ADAPTIVE PIPELINE FUNCTIONAL PASS**. Этап №3 завершён, 100%; общая AW0.81 и MAJOR ledger не переоценивались. STOP. 100/17211 PDF, PHASE B/C, Frozen B и AW0.82 не запускались. Commit не создан.
