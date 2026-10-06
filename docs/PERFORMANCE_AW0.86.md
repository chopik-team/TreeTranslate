# TreeTranslate AW0.86 — performance reference

Hardware: **Ryzen 7 5700X, 32 GB RAM, RTX 3080 12 GB**. Полные settings и instrumentation — в [final100 report](AW0.81_100PDF_FINAL_SPEED_CALIBRATION.md) и [manifest](../qa/aw086/benchmarks/final100/run_manifest.json).

| Same 100 PDF | Initial | AW0.86 reference |
|---|---:|---:|
| Wall | 4783,64 с / 79,73 мин | 1428,60 с / 23,81 мин |
| Processed PDF/hour | 75,26 | 252,00 |
| Source / output pages | 157 / 190 | 157 / 190 |
| TRANSLATED / FAILED_SOURCE_PRESERVED / fatal | 76 / 24 / 0 | 76 / 24 / 0 |

**Speedup 3,35×; wall reduction 70,14%; output equivalence PASS.** Benchmark already performed as run `736fc7a72805`; it was not repeated during release closure. UI/ETA changes after that measurement do not constitute a new measured benchmark.

Direct estimate for 17 211 PDF: **68,30 h / 2,85 days** continuous processing. Historical typical scenario: **118,28 h / 4,93 days**; it retains overlapping pipeline document latencies, so the direct throughput estimate is the more direct expression of current measured performance.

Corpus-specific and hardware-specific; failures are included; not a guarantee for every PDF. OCR/native/mixed composition, model cold starts and machine load affect timing. Full corpus translation was not run. [History](BENCHMARK_HISTORY.md), [reproducibility](BENCHMARK_REPRODUCIBILITY.md), [known issues](KNOWN_ISSUES.md).
