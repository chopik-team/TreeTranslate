# NMT Semantic Batch Scheduler — rejected research artifact

Production status: **REJECTED** for AW0.8x under its current exact-output contract/model/runtime. This folder is research evidence and is not part of the runtime import graph.

Final100 showed 3590 batch1 calls out of 3597, median 12 tokens and 564.10 s CT2 synchronous time. The prototype implemented bounded intra-document continuations, immutable routed envelopes, one semantic/GPU owner, compatibility checks and canonical commit barriers. Twenty prototype scheduler tests and the broader targeted tests passed; native exact-output gate failed.

Replay of 994 captured short CUDA M2M requests: batch1 exact, batch2 26 differences, batch4 50, batch8 78. No final PDF run was admitted. This is not a claim that all future batching is impossible.

`rejected_prototype.zip` contains the inactive prototype and its tests. `summary.json` contains the verdict. `evidence/native_replay_inputs.json` contains original token arrays/options/outputs extracted from the saved baseline; no new inference was performed for archival. Canonical complete replay results are in [`qa/aw081/nmt_batch_scheduler_5pdf/batch_replay.json`](../../aw081/nmt_batch_scheduler_5pdf/batch_replay.json), retained at that original path for regression tests.

Baseline run: `2bf4fd0f345e`, NMT-heavy fixed5, indices **49,56,64,76,82**, 27 pages, 350.89 s, 3 translated / 2 preserved. Git base commit `9aa36fc327463b5ef11d6d02e40a810207bd5e8f` alone does not identify the uncommitted production tree; authoritative hashes are in `evidence/rollback.json` and `evidence/full_pytest.json`.

Four patched production files were restored byte-exact and the added runtime scheduler module removed. Historical full suite: **1269 passed, 0 failed/errors/skipped**. Later accepted UI/ETA changes are captured separately in the AW0.86 freeze receipt; the archived rollback is historical.

[Full research report](../../../docs/AW0.81_NMT_BATCH_SCHEDULER_5PDF.md), [rejected experiments](../../../docs/research/REJECTED_EXPERIMENTS.md), [benchmark history](../../../docs/BENCHMARK_HISTORY.md).
