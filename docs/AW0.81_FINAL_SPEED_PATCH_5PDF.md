# AW0.81 — Final performance patch / fixed5

## 1. Fixed5 sample

Ровно пять исходных fixed20 members: 0, 13, 14, 16, 17, 21 страниц. Детерминированные правила: minimum measured native/EASY_NATIVE document wall; maximum mixed OCR; maximum image-only OCR; maximum remaining model_translation; maximum remaining actual page layout/write. Ties — original index; ZIP order восстановлен. Два FAILED_SOURCE_PRESERVED cases. Manifest/source SHA заморожены до baseline. Baseline — current uncommitted AW0.81 source, hashes сохранены; это не Git HEAD без предыдущих изменений.

## 2. Before bottlenecks

Baseline 277.59s: NMT inference 100.20s, model_translation 109.88s, glossary 44.46s, OCR recognition 88.12s, postprocess 14.43s. Timings inclusive, их нельзя складывать как wall. Reference fixed20 glossary был 76.46s на stage3; 66.89s относится к предыдущему stage2.

## 3. NMT findings

886 real CT2 calls, все batch=1; median 12.0 source tokens. 348 повторных точных prepared inputs, но M2M encode/source/decode суммарно <0.09s: cache не нужен. 13 real CT2 loads, из них четыре CUDA M2M на существующих OCR memory boundaries; 858 M2M load/reuse checks заняли 3.25s, model reuse работает. Argos CPU/CUDA fallback определяется guards и сохранён.

GPU получает множество коротких синхронных запросов между glossary/guards; model_translation включает actual CT2 и lifecycle/preparation. CT2 synchronous public API не разделяет host/device transfer и kernel time, поэтому это N/A, а не ноль. Encode/decode отдельно измерены для M2M; Argos preparation/discovery входит в оставшийся model runtime. Токены — model-ready source pieces с language/EOS, не output tokens. Replay первых64 совместимых captured inputs: sequential 4.133s; batch8 0.935s exact PASS; batch16 0.575s exact FAIL. Production не имеет очереди уже routed независимых requests: следующий semantic turn ждёт result/guards/fallback предыдущего. Assembler сейчас немедленно flush batch1; новый async semantic scheduler сюда не добавлен.

## 4. PDF_LOCK / writer findings

До fix writer: 39.79s wait и 6.94s actual work. После: 0.00s wait, 6.39s work. Lock освобождается ровно вокруг recognize по copied RGB image: bitmap уже закрыт, rotation восстановлена; page/objects не используются. Все PDFium operations остаются под lock; exception/cancel восстанавливает ownership в finally. Recursive caller scope сохраняется. Раздельные native/OCR/writer/validation outer scope данные в lock_profile.json; layout/write nested inclusive, не дополнительное время.

## 5. Accepted changes

Два небольших runtime changes в трёх production files: detached OCR lock scope и geometry-first deduplication. Ни models, thresholds, DPI, gate, candidate order, Knowledge, constraints, beam, decoding, routing, fallback, UI не изменены. Microtests: detached writer overlap 34.73% faster, exact PDF objects/render; dedup replay 83.55% faster, exact decisions. В baseline5308 raw recognized segments против3611 retained OCR blocks; postprocess14.43s оправдывал проверку residual path. Final postprocess 7.27s. Новый real PDF race test подтверждает source contracts/render; 49 Knowledge DB hashes unchanged.

## 6. Rejected / no-benefit ideas

Batch16 нарушил exact output; batch8 требует отсутствующей ready request queue. Preparation cache экономил бы <0.09s. NMT lifecycle уже reuse, не переписан. Writer process: actual work только2.5% baseline wall, ниже10% potential cutoff. Knowledge hot path: большая стоимость PRAGMA data_version нужна для external commit invalidation; immutable run-wide revision cache изменил бы поведение. OCR allocation/models/thresholds не менялись.

## 7. Before → after

| Metric | Before | After | Reduction / gain |
|---|---:|---:|---:|
| wall (s) | 277.589 | 269.082 | 3.065% |
| successful docs/hour | 38.910 | 40.141 | 3.162% |
| model_translation (s) | 109.885 | 109.256 | 0.572% |
| ocr_recognize (s) | 88.124 | 89.598 | -1.673% |
| ocr_postprocess (s) | 14.432 | 7.265 | 49.657% |
| glossary_lookup (s) | 44.462 | 43.894 | 1.277% |
| knowledge_snapshot (s) | 0.495 | 0.128 | 74.121% |
| template_routing (s) | 13.009 | 12.926 | 0.640% |
| NMT inference_seconds | 100.200 | 99.824 | 0.376% |
| NMT calls | 886.000 | 886.000 | 0.000% |
| NMT sequences | 886.000 | 886.000 | 0.000% |
| NMT tokens | 10513.000 | 10513.000 | 0.000% |
| NMT median_sequences | 1.000 | 1.000 | 0.000% |
| NMT median_tokens | 12.000 | 12.000 | 0.000% |
| NMT batch1 | 886.000 | 886.000 | 0.000% |
| NMT batch2 | 0.000 | 0.000 | N/A% |
| tokenizer_encode (s) | 0.028 | 0.028 | -0.537% |
| tokenizer_source_tokens (s) | 0.001 | 0.001 | -2.112% |
| tokenizer_decode (s) | 0.055 | 0.055 | -0.713% |
| m2m100_load_or_reuse (s) | 3.250 | 3.251 | -0.020% |
| actual CT2 loads | 13.000 | 13.000 | 0.000% |
| PDF_LOCK total wait (s) | 39.793 | 0.001 | 99.998% |
| PDF_LOCK total held (s) | 113.507 | 17.710 | 84.397% |
| writer lock wait (s) | 39.793 | 0.000 | 100.000% |
| writer actual work (s) | 6.940 | 6.390 | 7.931% |
| layout/write (s) | 6.642 | 6.177 | 6.999% |
| CPU average (% of one logical CPU) | 113.258 | 114.319 | -0.937% |
| GPU average (device-wide %) | 47.656 | 50.023 | -4.967% |
| peak RSS (GiB process tree) | 3.606 | 3.895 | -8.023% |
| peak VRAM (GiB device-wide) | 5.492 | 5.521 | -0.533% |

Одинаковые MID QA controls: CPU8, OCR4, NMT tokens768, OCR batch6, serial GPU owner, same excluded warmup. Model parameters одинаковы. GPU utilization/VRAM device-wide включают другие приложения; RSS/CPU process tree,100%CPU=один logical CPU. Status counts:3 TRANSLATED,2 FAILED_SOURCE_PRESERVED,0fatal. Exactly one baseline, one final; дополнительный разрешённый depth1 recheck 268.36s против final depth2 269.08s, depth2 gain -0.27%. Depth3/4 не запускались; существующий conservative ceiling2 оставлен без scheduler изменений.

## 8. Equivalence

PASS: все final checks в output_equivalence.json: statuses, full captured OCR sources, ordered glossary/selected terms/constraints, profiles/snapshots, candidates, writer protected IDs/numbers/preserved segments, page counts/normalized objects/render probes всех translated PDFs, paths/directories, failed exact bytes, ZIP inventory/order/CRC, source SHA. Для каждого runtime request совпали semantic identity/backend/options/model output и ordered prepared CT2 input/output, fallback attempts/circuit skips. Дополнительно все PDF bytes совпали после исключения только сгенерированного trailer /ID: его random bytes меняют raw CRC translated PDFs при каждом save. ZIP CRC integrity проверен для всех entries; FAILED_SOURCE_PRESERVED bytes/CRC совпали буквально. Нет quality regrade/Frozen A evaluation.

## 9. Full pytest

1256 passed, 0 failures, 0 errors, 0 skipped; pytest 323.55s, command wall324.74s. Production SHA до/после совпали. 1248 baseline +8 новых проверок. Earlier targeted:67 existing +8 new PASS.

## 10. Remaining bottleneck

Синхронные маленькие NMT requests и glossary revision polling. NMT model time reduction 0.57% — отдельный20% NMT target не достигнут. Пересчёт времени17211 PDF по пяти PDF не выполнялся: требуется отдельная исходная100-PDF calibration.

## 11. Verdict

**FUNCTIONAL PASS; SPEED TARGET NOT MET**. Wall reduction 3.06%. Это измеренный результат одного before/after на fixed5, не прогноз для полного архива. No new fixed20 /100 /17211 runs, resource modes, UI changes, AW0.82 or commits. STOP.

Raw source contracts, glossary traces, run logs, per-document fingerprints, translated result ZIPs и pytest XML/stdout сведены в `qa/aw081/final_speed_patch_5pdf/evidence.zip`. Проверены CRC архива и SHA-256 каждого entry. Основные8 JSON и frozen input ZIP доступны отдельно; временные копии дополнительно сохранены в raw_copies/. Helper читает их оттуда; исходные receipt paths также восстанавливаются распаковкой evidence.zip в его каталог.
