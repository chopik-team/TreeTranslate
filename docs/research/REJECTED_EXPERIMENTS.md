# Отклонённые исследования AW0.8x

## NMT Semantic Batch Scheduler

Причина исследования: final100 имел 3597 CT2 calls, 3590 batch1, median 12 source tokens; synchronous CT2 inference 564,10 с. Прототип bounded semantic continuations пытался собрать совместимые routed requests с canonical commit barrier, одним semantic/GPU owner и hardware-aware ceiling до 8. Structural/unit tests прошли, но этого недостаточно для exact-output equivalence.

На 994 captured native short CUDA M2M requests при прежних model/options:

| Batch | Native inference | Output differences | Verdict |
|---|---:|---:|---|
| 1 | 118,095 с | 0 | PASS |
| 2 | 72,122 с | 26 | FAIL |
| 4 | 44,926 с | 50 | FAIL |
| 8 | 24,920 с | 78 | FAIL |

Batch shape менял native hypothesis. Точная причина на уровне CUDA kernels не установлена. Savings этого replay — не измеренный gain PDF pipeline; final PDF benchmark unsafe prototype не запускался.

**Rejected for AW0.8x under current exact-output contract/model/runtime.** Это не утверждение, что batching невозможен навсегда. Будущая работа должна заново доказать output contract на достаточном captured sample, guards/fallback/order и PDF equivalence.

Production четыре файла восстановлены точно по historical baseline SHA; добавленный runtime module удалён. Safe production затем прошёл 1269 тестов без failures/errors/skips. После этого согласованные UI/ETA изменения имеют собственную проверку и учитываются в новом AW0.86 freeze snapshot; historical global SHA не выдаётся за SHA текущего дерева.

[Исходный отчёт](../AW0.81_NMT_BATCH_SCHEDULER_5PDF.md), [архив и replay inputs](../../qa/experiments/nmt_batch_scheduler/README.md), [historical rollback](../../qa/experiments/nmt_batch_scheduler/evidence/rollback.json). Прототип лежит только в research ZIP и не импортируется из `app/`.
