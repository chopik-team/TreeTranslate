# AW0.81 OCR Adaptive Runtime

**OCR PERFORMANCE PASS**. Этап №1 выполнен. Ровно один measured fixed20, run `2681af77e18c`; sample 5/5/5/5 и MID execution settings сохранены.

## 1. Root cause

29 regions × два неизменных recognition candidates = 58 обращений. Старый worker держал один key: A → B → A → B. На 9 OCR-документах instrumentation зафиксировала 58 загрузок и 49 eviction при смене variant. Общие detector/orientation/layout/table bundles создавались заново вместе с recognizer.

Исторический MID: constructor load 657.46 с, inference 148.85 с. Отдельный legacy shadow до смены архитектуры: constructor 708.82 с, Paddle import/init 45.60 с, первый predict 156.75 с; поздних predict без перезагрузки не было. Spawn 0.084 с, shutdown 8.23 с.

| Компоненты legacy shadow | Конструктор, с | Первый predict, с |
|---|---:|---:|
| detector | 323.33 | 13.97 |
| recognizer | 29.56 | 32.40 |
| orientation | 32.25 | 31.13 |
| structure_table | 316.10 | 0.00 |

Это decomposition отдельного instrumented shadow, а не ретроспективное измерение 657 с MID. Первый native predict включает lazy child-model loading и warmup; чистый kernel warmup отдельно не отделялся. Все transitions сохранены в `ocr_load_transitions.jsonl` и `baseline.json`.

## 2. Что изменено

Run владеет одним ленивым OCR worker; дочерние DocumentJob заимствуют runtime. Bounded model cache держит bundles по device/backend/recognizer/options/model-pack; active references защищены, eviction — deterministic LRU по числу и фактическим RAM/VRAM footprints. Внутри run добавлен ограниченный result cache с source SHA, page, bbox, DPI/render/pixels, model pack, language и semantic options. Возвращаются независимые копии; cross-device reuse отключён.

## 3. Hardware-aware policy

RAM reserve = max(2 GiB, 15% total), residency ceiling = min(35% total, available − reserve). VRAM reserve = max(512 MiB, 15% total), ceiling = min(65% total, free − reserve), дополнительно ограничен существующим Paddle cap. Ceilings clamped к физической памяти. Result cache ≤256 MiB/1% usable RAM, prepared ceiling ≤128 MiB/2% usable; speculative queue не создаётся. Модели загружаются по запросу, память не резервируется искусственно.

Fake capabilities 8/no CUDA, 16/4, 32/12, 64/24 проверены: upper count 1/2/4/4, byte budgets и headroom обязательны. На текущем запуске реально использованы два variants. При RAM pressure result cache очищается, resident cache высвобождает неактивные bundles; CUDA allocator освобождается после eviction. Batch остаётся MID=6: прошлый bundle experiment не доказал безопасного изменения. При backend failure действует существующий fallback. OCR/NMT inference concurrency и threads не менялись.

## 4. Page/region gating

Shadow до изменений и measured after: 39 pages, 12 NATIVE_SUFFICIENT, 8 MIXED_NEEDS_REGION_OCR, 19 IMAGE_ONLY_NEEDS_OCR; UNCERTAIN_FALLBACK покрыт unit test и сохраняет old full-page path. Существующая page/region policy вынесена в дешёвый gate без OCR/NMT/Knowledge/Profiler. OCR: 27 pages / 29 regions; 7 image regions уже исключались старой policy. **Новых skips: 0.** Bbox, reading order, suppression и merge не менялись.

## 5. OCR load/reuse

58 → 2 loads; 56 resident reuse, 0 eviction, max simultaneous bundles 2. Result cache: 0 hits / 58 misses: fixed20 не повторяет одинаковые regions; repeated-input reuse отдельно проверен unit test. Targeted4: exact source contract PASS, 16 → 2 loads, 38.18 с.

## 6. Fixed20 wall

| Показатель | MID до | После |
|---|---:|---:|
| Wall, с | 1453.59 | 726.26 |
| Загрузки OCR | 58 | 2 |
| Конструкторы моделей, с | 657.46 | 24.25 |
| Worker inference с lazy load/warmup, с | 148.85 | 54.20 |
| OCR pages / regions | 27 / 29 | 27 / 29 |
| Workers | 9 | 1 |

Wall уменьшился на **50.04%**, throughput +100.15%. Warmup исключён одинаково с MID. Peak tree RSS 3.88 GiB, private commit 9.44 GiB; Paddle peak allocated/reserved 2.11/2.52 GiB. Device-wide peak 5962 MiB включает другие приложения; process VRAM under WDDM недоступна.

## 7. Equivalence

**PASS**: 20 source text/block/page, translation candidates, statuses, IDs/numbers, page counts, normalized PDF objects, четыре rendered first/last-page probes, failed exact bytes/path и ZIP CRC. 16 TRANSLATED / 4 FAILED_SOURCE_PRESERVED / 0 fatal, source ZIP SHA неизменён. Полные source contracts (включая bbox/polygon/order/confidence/model) совпали на 19 measured PDF и на targeted4.

Ограничение QA observer: для первого member до child extraction был сохранён native archive sample (26 blocks); фактический child имеет 27 blocks. Для него measured source text/block/page сверены через writer с MID и shadow, полный OCR contract ранее проверен в targeted4. Недостающие measured координаты/confidence не подставлялись из baseline; повторный fixed20 не запускался. Для одного другого failed PDF без MID writer использован legacy shadow contract. Это дополнительные source проверки; итоговые кандидаты/PDF сравниваются именно с MID.

## 8. Remaining OCR bottleneck

После устранения reload остаются обязательный первый load и native inference 54.20 с. Render 0.56 с, existing postprocess 15.78 с (stage measurements могут быть вложенными). Новые skips и batch changes без exact evidence не включались. Остальные потери перевода/Knowledge в этом этапе не оптимизировались.

## 9. Full pytest

1201 passed / 0 failed / 0 errors / 0 skipped, 337.35 с. Production hashes до/после suite совпали (252 files). Diff относительно начала этапа ограничен 13 OCR/runtime/ownership files; Knowledge, TM, glossary, NMT, UI/assets неизменны. Frozen MID harness/support SHA сохранены; TM test store пуст, workers завершены. Evidence: `qa/aw081/ocr_adaptive_runtime/`.

## 10. Verdict

**OCR PERFORMANCE PASS**. Этап OCR завершён, STOP. Общая AW0.81 и semantic MAJOR ledger не переоценивались. Следующие два performance этапа и 100/17211 PDF не запускались; commit не создан.
