# AW0.81 — финальная калибровка на прежних 100 PDF

**TOTAL AW0.81 SPEEDUP: 3,35×; WALL REDUCTION: 70,14%.**
OLD: 79,73 мин → NEW: 23,81 мин / 100 PDF. Equivalence: **PASS**.

## 1. Same-100 verification

**SAME SAMPLE AS 25825c3f75a7: PASS.** Historical manifest скопирован дословно. Для всех100 проверены original paths, inventory PDF indices/order, size, ZIP CRC, source SHA256 и равенство байтов historical subset/full source. Использован прежний subset ZIP, чтобы сохранить прежний archive context; новых PDF и замен failures нет.
Full CN7C: 17 211 PDF; SHA256 `ecc0fd54bbc421af33febcb4f971e9a4735b15102aae9c451334a449c3a85330`. Production hash freeze совпадает с последним1256 PASS; все49 DB Knowledge неизменны.

## 2. Hardware/runtime

CPU: 8 physical / 16 logical; RAM 31,91 GiB; GPU `NVIDIA GeForce RTX 3080`.
DocumentConfig: source auto, target ru, domain auto, device AUTO, profile AUTOMATIC, threads default; filenames/directories включены как в baseline. Pipeline planner/caps/GPU ownership/cache policy не подменены; policy ORIGINAL. No MID/Ultra overrides, process commit caps или benchmark OCR caps.
Actual pipeline: depth 2, prepare_workers 1, semantic_workers 1, writer_depth 1, GPU owner 1; inflight high water 2. План и полный pipeline telemetry сохранены в run_summary.json.
Historical helper run() не содержит explicit warmup. Поэтому warmup0s, resident models до старта нет; fresh isolated TM/user DB. Cold model loads входят в wall, как раньше. Общая проверка source/sample вне wall; sample scan входит в wall.
Sample scan: 0,05s. Production/Knowledge/source/model policy в процессе не менялись. QA observers только пересылают исходные вызовы и собирают данные; их накладные расходы включены в новый wall. Никаких prewarm100/cache-full-inputs.

## 3. Old baseline

Run25825c3f75a7: 4783,64s / 79,73min; 100 processed,76 TRANSLATED,24 FAILED_SOURCE_PRESERVED,0 fatal;157 source/190 output pages. Processing75,26docs/h. Исторический typical229,51h /9,56d.

## 4. New 100-PDF result

Run `736fc7a72805`: 1 428,60s /23,81min; 100 processed, 76 TRANSLATED, 24 FAILED_SOURCE_PRESERVED, 0 fatal. Source 157, output 190 pages.
Первый child start 2,01s; first processed 48,96s; first translated 48,96s. Completion25/50/75/100%: `{'25': 311.2725934, '50': 573.6453462999998, '75': 983.8056975, '100': 1427.3464844}` seconds.
Latency max 121,83s. Scope: child admission→canonical archive append; queue waiting входит, per-document latencies перекрываются. Их сумма 2 466,05s vs wall 1 428,60s.

## 5. Before → after

| Metric | Old100 | New100 | Change |
|---|---:|---:|---:|
| Wall,s | 4 783,64 | 1 428,60 | -3 355,04 |
| Wall,min | 79,73 | 23,81 | -55,92 |
| Docs/hour | 75,26 | 252,00 | 176,74 |
| Source pages/hour | 118,15 | 395,63 | 277,48 |
| Output pages/hour | 142,99 | 478,79 | 335,80 |
| Processed segments/s | 1,56 | 5,22 | 3,66 |
| Semantic segments/s | 0,79 | 2,66 | 1,87 |
| Latency mean,s | 47,80 | 24,66 | -23,14 |
| Latency median,s | 17,99 | 19,07 | 1,08 |
| Latency p90,s | 132,63 | 47,06 | -85,57 |
| Latency p95,s | 242,21 | 69,11 | -173,10 |
| Latency p99,s | 298,53 | 100,49 | -198,03 |
| Latency max,s | 299,26 | 121,83 | -177,42 |
| First processed,s | 44,88 | 48,96 | 4,08 |
| First translated,s | 44,88 | 48,96 | 4,08 |
| OCR recognize inclusive,s | 3 098,42 | 478,55 | -2 619,87 |
| OCR worker load,s | N/A | 186,07 | N/A |
| OCR worker inference,s | N/A | 120,02 | N/A |
| OCR postprocess,s | 18,86 | 10,80 | -8,06 |
| Glossary lookup inclusive,s | 889,78 | 196,26 | -693,53 |
| Model translation inclusive,s | 497,22 | 621,87 | 124,64 |
| Actual CT2 calls | N/A | 3 597,00 | N/A |
| CT2 batch1 calls | N/A | 3 590,00 | N/A |
| CT2 batch2+ calls | N/A | 7,00 | N/A |
| CT2 median sequences | N/A | 1,00 | N/A |
| CT2 median source tokens | N/A | 12,00 | N/A |
| CT2 synchronous inference,s | N/A | 564,10 | N/A |
| Writer document_write inclusive,s | 177,24 | 216,60 | 39,36 |
| Writer PDF_LOCK wait,s | N/A | 0,00 | N/A |
| Process-tree CPU avg,% | N/A | 136,25 | N/A |
| Device GPU avg,% | N/A | 48,16 | N/A |
| Process-tree peak RSS,GiB | N/A | 3,86 | N/A |
| Device peak VRAM,MiB | N/A | 6 049,00 | N/A |
| TRANSLATED | 76,00 | 76,00 | 0,00 |
| FAILED_SOURCE_PRESERVED | 24,00 | 24,00 | 0,00 |
| Fatal | 0,00 | 0,00 | 0,00 |

N/A означает отсутствие historical instrumentation, а не 0. Old CPU/GPU/CT2 batching/tokens/lock timings отсутствуют; новые значения не выдаются за сопоставимое улучшение.
Общий throughput вырос, но first processed +4,08s; median +1,08s; model_translation +124,64s; writer +39,36s. По одному run и без historical continuous resource trace нельзя надёжно разделить влияние contention/частот и изменений runtime. Это зарегистрировано, не исправлялось.

## 6. Stage profile before → after

Одна и та же historical методика interval-union: OCR→model→glossary→TM→templates→guards→writer→validation→profiler→snapshot→extraction→append→path priority. Каждая wall interval принадлежит одной категории. При parallel execution это occupancy, не causal critical-path attribution; OCR recognition включает GPU-owner wait и может перекрывать NMT. Inclusive stage суммы отдельно, они могут превышать wall.

| Stage | Old seconds | Old% | New seconds | New% |
|---|---:|---:|---:|---:|
| OCR | 3 098,42 | 64,77 | 478,55 | 33,50 |
| glossary | 889,78 | 18,60 | 164,31 | 11,50 |
| model | 497,22 | 10,39 | 533,48 | 37,34 |
| writer | 177,24 | 3,71 | 170,06 | 11,90 |
| Other | 120,97 | 2,53 | 82,20 | 5,75 |

OCR: 90 attempted pages /120 regions; model loads 28 (186,07s), resident reuse 212; worker inference 120,02s, parent postprocess 10,80s.
Glossary: 24682 lookup calls; 4900 unique logical keys; 1358559 SQL statements; repeated negative results 8507. Lexical cache positive hits 10048, negative hits 247315, misses 11858. Ключи cache negative hits — lexical candidate hashes; повторные пустые final lookup results имеют другой scope. Полные counters в stage_profile.json.
Writer: pdf_write 216,58s; actual lock-held 216,57s; lock wait 0.002508s; page/layout 70,33s. Это вложенные метрики, не сумма.
Other inclusive seconds: template_routing=60,81, knowledge_snapshot=22,80, DocumentProfiler=0,07, semantic_guards=36,61, pdf_validation=2,43, archive_extract=0,35, archive_pack_member=2,81.

## 7. NMT profile

3597 actual CT2 calls; 3604 sequences; 59811 source pieces (language/EOS included); median 1,00 sequences/call, 12,00 tokens/call; batch1=3590, batch2+=7.
Actual synchronous CT2 564,10s = 39,49% measured wall; model_translation 621,87s inclusive. CT2 owns transfer/preparation internally; separate kernel/transfer timing unavailable.
CT2 constructor loads 93 ({'m2m100': 35, 'argos': 58}, 30,78s); M2M load/reuse calls 3282, из них resident reuse 3247; backend failure attempts 168, fallback attempts 167. Old M2M real loads35/Argos58, load-or-reuse3282: новые counts совпадают. Native failure/fallback counts168/167 тоже совпадают; это measurement текущей политики, не утверждение об устранении всех повторов. Loads/device records in nmt_profile.json; options unchanged.

## 8. Failures/status equivalence

**Output equivalence PASS**; checks `{'statuses': True, 'destination_paths': True, 'zip_inventory_and_order': True, 'directory_structure': True, 'crc': True, 'failed_source_preservation': True, 'normalized_translated_semantics': True, 'available_source_metadata': True, 'bounded_frontier_candidates': True}`. Current failure categories `{'VALIDATION': 17, 'UNSUPPORTED_STRUCTURE': 6, 'MODEL_LIMITATION': 1}`, exception types `{'PdfError': 17, 'IndexError': 6, 'TranslationError': 1}`. Никакие document failures не исправлялись.
Проверены все100 statuses/destinations/failed original paths+bytes, ZIP order/inventory/directory structure/CRC, protected ID/number multisets, normalized PDF text/objects на всех translated pages и first+last render probes каждого translated PDF. Generated trailer/ID исключён только из отдельной byte comparison.
Дополнительно: 24 members raw binary exact; все100 members byte-exact после исключения generated trailer /ID. У всех76 translated PDF единственное byte отличие — /ID; все24 failed originals совпадают без нормализации.
Historical candidate evidence: bounded frontier {'old': 38, 'new': 38}; сравнение доступных current_candidate_translation и metadata. Полного historical ordered candidate/source OCR contract нет; это UNAVAILABLE. Новые source contracts записаны, historical отсутствие не считается PASS полного OCR contract.
Изменения статусов, source metadata, текста или пути перечислены по member в output_equivalence.json. При несовпадении это регрессия/неподтверждённая эквивалентность, не улучшение; production не исправлялся.

## 9. Resource use

CPU tree avg 136,25% /peak 764,86% (100%=one logical core); RSS peak 3,86GiB; private commit peak 9,94GiB; system available RAM minimum 17,35GiB.
Device GPU avg 48,16%, VRAM peak 6 049,00MiB; device-wide includes desktop and other apps. 1401 one-second samples. Historical root RSS sampled peak 1,39GiB; tree RSS NOT DIRECTLY COMPARABLE. Per-process WDDM VRAM unavailable; no heavy monitoring installed.

## 10. Full17 211 forecast

Direct throughput: 1 428,60×172,11=68,30h /2,85d continuous.
Historical exact formula восстановлена из tools/aw081_speed_calibration_report.py; replay old188,228323905/229,509831647/303,933432202h PASS. Те же family population weights, Random(81),2000 within-family bootstrap samples; optimistic=min(P10,typical−0,25×weightedOCR); conservative=max(P90,typical+0,50×weightedOCR+lowerFailureExtra). Новые коэффициенты не вводились.
Typical=sum(weight×admittedLatency)+max(0,wall−sumLatency)+fullScan. Здесь latency overlap ratio 1,73×. Старую формулу применили буквально: она сохраняет очереди/перекрытие pipeline и даёт scenario proxy, не оценку wall с устранённым overlap. Для фактического текущего throughput использовать direct forecast; scenarios не confidence interval. Full scan retained historical verified unchanged-source 3,16s.

| Scenario | Old,h | New,h /d | Saved,h | Saved,d |
|---|---:|---:|---:|---:|
| optimistic | 188,23 | 107,04 /4,46 | 81,19 | 3,38 |
| typical | 229,51 | 118,28 /4,93 | 111,23 | 4,63 |
| conservative | 303,93 | 131,27 /5,47 | 172,67 | 7,19 |
| direct_linear | 228,70 | 68,30 /2,85 | 160,40 | 6,68 |

## 11. One next bottleneck

**NMT**. Выбор по новому100: actual measured work `{"NMT": 564.1015580999874, "OCR": 316.8859843999935, "Writer": 216.56781170000158, "Glossary": 198.7580138999483}` seconds. Для OCR использованы worker inference+real load+postprocess, а не parent recognition gate waiting. Для NMT — real CT2 synchronous time; writer — held, glossary — real lookup. Это измеренные вложенные work scopes, не суммируемые доли wall.

## 12. NMT scheduler decision

**NMT SCHEDULER JUSTIFIED**. Actual CT2 wall fraction 39,49%; batch1 3590. Opportunity upper proxy при75% local inference reduction: 29,61% общего wall, НЕ обещание измеренного whole-run gain. Реалистичный выигрыш требует независимой semantic queue, сохранения guards/fallback/order и нового equivalence gate.
Прежний fixed5:886 CT2 calls, все batch1; captured replay batch8 exact PASS/большой local gain; batch16 exact FAIL. Это основание только для отдельного проекта, не коэффициент full-corpus forecast. Здесь batching не реализован.

## 13. Full archive readiness

**OPTIMIZATION STILL JUSTIFIED**. Наличие0fatal не отменяет equivalence gate. Допустимое пользователю время полного прогона не задано; прежний24h threshold был QA assumption, не подтверждённым согласием. Full archive автоматически не запускался.

## 14. Final verdict

TOTAL AW0.81 SPEEDUP **3,35×**; WALL REDUCTION **70,14%**. OLD79,73min→NEW23,81min/100PDF.
OLD TYPICAL229,51h/9,56d→NEW TYPICAL118,28h/4,93d (exact old scenario formula with admitted latency overlap caveat). Direct current wall forecast 68,30h/2,85d.
NEXT BOTTLENECK:NMT; NMT SEMANTIC BATCH SCHEDULER:JUSTIFIED; FULL ARCHIVE:OPTIMIZATION STILL JUSTIFIED.
Production/Knowledge hashes unchanged; last1256 PASS reused; measurement helper targeted tests passed. Ровно один100-PDF measured run. STOP: no second run, no optimization, no full corpus, no failure fixes, no AW0.82/PHASEB/C/FrozenB.
