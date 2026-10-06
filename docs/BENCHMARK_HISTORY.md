# История benchmark TreeTranslate

Официальное сравнение AW0.86 — одна и та же выборка 100 PDF: **79,73 → 23,81 мин**, **3,35×**, **−70,14% wall**. Выборки fixed5, fixed20 и 100 различаются; их wall нельзя сравнивать друг с другом как один corpus. Speedup в таблице относится только к указанному before/after того же sample.

| Stage | Sample | Wall before → after | Speedup | Status | Report |
|---|---|---|---|---|---|
| Initial100 | Same100 | 4783,64 с / 79,73 мин | 1,00× reference | Baseline, 76 translated / 24 preserved | [Initial100](AW0.81_100PDF_SPEED_CALIBRATION.md) |
| OCR adaptive / milestone 0.82 | Fixed20 | 1453,59 → 726,26 с | 2,001× | Performance + equivalence PASS | [OCR](AW0.81_OCR_ADAPTIVE_RUNTIME.md) |
| Glossary / milestone 0.83 | Same fixed20 | 726,26 → 451,46 с | 1,609× | Performance + equivalence PASS | [Glossary](AW0.81_GLOSSARY_HOT_PATH.md) |
| Pipeline / milestone 0.84 | Same fixed20 | 451,46 → 452,60 с | 0,997× | Functional PASS; no throughput win | [Pipeline](AW0.81_ADAPTIVE_PIPELINE.md) |
| Runtime polish / milestone 0.85 | Separate fixed5 | 277,59 → 269,08 с | 1,032× | Small improvement, equivalence PASS | [Polish](AW0.81_FINAL_SPEED_PATCH_5PDF.md) |
| Final100 / AW0.86 official reference | Same100 as initial | 4783,64 → 1428,60 с | **3,348×** | **Equivalence PASS**, 76 / 24 / 0 fatal | [Final100](AW0.81_100PDF_FINAL_SPEED_CALIBRATION.md) |
| NMT semantic batching | NMT-heavy fixed5 + 994 native replay requests | Baseline 350,89 с; no final PDF run | N/A | **REJECTED**, batches 2/4/8 violate exact output | [Research](research/REJECTED_EXPERIMENTS.md) |

Final100 run `736fc7a72805`, initial100 `25825c3f75a7`. Failure statuses are included in wall and documents/hour. Successful translations alone are not the denominator of the reported 252 PDF/hour.

Forecast for 17 211 PDF: direct measured wall scaling **68,30 h / 2,85 days**. Historical scenario formula gives typical **118,28 h / 4,93 days** because admitted document latencies overlap in the pipeline. It is a scenario proxy, not the direct wall forecast or a confidence interval.

No benchmarks were rerun for consolidation. Historical reports preserve their original conclusions, including provisional NMT opportunities later rejected. [Reproducibility and evidence](BENCHMARK_REPRODUCIBILITY.md).
