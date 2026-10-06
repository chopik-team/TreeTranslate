# TreeTranslate AW0.86

Technical alpha / development release: consolidated source freeze at the end of AW0.8x. This is not 1.0 and does not include a Windows installer or model weights. No new runtime algorithm or quality change was introduced during consolidation.

## Highlights

Accepted archive/runtime, adaptive OCR, glossary/Knowledge hot path, bounded pipeline, recovery and final runtime polish are frozen together. Historical milestones AW0.81–AW0.85 are documented in CHANGELOG, without fabricated old Git tags. The real annotated tag is `AW0.86`.

## Performance

Same 100 PDF: **79.73 → 23.81 min**, **3.35×**, **70.14% less wall time**; 75.26 → 252.00 processed PDF/hour on Ryzen 7 5700X, 32 GB RAM, RTX 3080 12 GB. Source/output pages: 157/190. **76 translated, 24 failed sources preserved, 0 fatal; output equivalence PASS.** The benchmark is the already measured run `736fc7a72805`, not a new release benchmark.

Direct forecast for 17,211 PDF: 68.30 h / 2.85 days; historical typical scenario 118.28 h / 4.93 days retains overlapping pipeline latencies. Corpus/hardware-specific, failures included, not a guarantee for every PDF. See [performance summary](../PERFORMANCE_AW0.86.md) and [benchmark history](../BENCHMARK_HISTORY.md).

## OCR

Lazy worker lifecycle, bounded resident model/result caches, hardware-aware RAM/VRAM policy and deterministic eviction. Historical same fixed20: 1453.59 → 726.26 s; OCR model loads 58 → 2; constructor/load 657.46 → 24.25 s. Output equivalence PASS.

## Glossary / Knowledge

Persistent read-safe SQLite handling, bounded lexical/normalization/negative caches, prefetch and revision/data_version invalidation. No ranking/semantic change in the optimization milestone. Fixed20 726.26 → 451.46 s; glossary 333.15 → 66.89 s; 9473 actual lookup queries equivalent.

## Archive handling

Streaming member-by-member ZIP processing; original paths reserved before lazy filename/folder translation; collision-safe deterministic publication, CRC and source immutability. Failed documents keep exact original paths/bytes while other members continue. RAR/7z and recursive nested extraction are not supported.

## Reliability

Bounded pipeline/backpressure and detached IR with pause/cancel cleanup and failure isolation. Pipeline milestone is FUNCTIONAL PASS, not a throughput breakthrough: 451.46 → 452.60 s. Final polish removed writer PDF_LOCK wait (39.79 → ~0 s), reduced OCR postprocess 14.43 → 7.27 s and lowered separate fixed5 wall 277.59 → 269.08 s. Accepted live ETA/countdown and file-bar contrast updates are included.

## Testing

Historical restored NMT safe baseline: **1269 passed, 0 failures/errors/skipped**. Fresh closing suite: **1278 passed, 0 failed/errors/skipped** (614.25 s), production hashes unchanged. Production hashes, compile and diff checks are recorded in [freeze receipt](../AW0.86_FREEZE_RECEIPT.md) and compact technical evidence. No repeat 100-PDF/full-corpus run was made for closure.

## Known limitations

Final100 preserved 24 failed documents: 17 VALIDATION/PdfError, 6 UNSUPPORTED_STRUCTURE/IndexError, 1 MODEL_LIMITATION/TranslationError. These are not fixed by this release. Technical integrity is not acceptance of semantic translation quality for the entire corpus. Model/dependency packaging and clean-machine licensing checks remain in the next cycle. [Known issues](../KNOWN_ISSUES.md).

## Research / rejected experiments

NMT Semantic Batch Scheduler is **REJECTED for AW0.8x under the current exact-output contract/model/runtime**. Native replay of 994 requests: batch1 exact, batches 2/4/8 had 26/50/78 output differences. Production was restored; the inactive prototype and evidence are archived separately. This does not rule out future research under a newly proven contract. [Research](../research/REJECTED_EXPERIMENTS.md).

## Next: AW0.9

Only stabilization/release preparation scope is opened. No AW0.9 features are implemented in this closure. The user will approve the roadmap separately. Windows public packaging targets the later 1.0 cycle. [Preliminary scope](../AW0.9_SCOPE.md).
