# Воспроизводимость benchmark AW0.86

Официальные compact evidence: [`qa/aw086/benchmarks`](../qa/aw086/benchmarks/evidence_index.json). Это копии уже полученных результатов, а не новые прогоны. Исторические отчёты могут ссылаться на большие локальные raw trees; их компактные эквиваленты перечислены в index с original path, SHA256 и размером.

## Source and sample

Full CN7C ZIP SHA256: `ecc0fd54bbc421af33febcb4f971e9a4735b15102aae9c451334a449c3a85330`, 17 211 PDF. Исходный ZIP/RAR не входит в Git и release assets. Используйте законно полученную локальную копию и проверьте SHA до сравнения.

[`final100/sample_manifest.json`](../qa/aw086/benchmarks/final100/sample_manifest.json) и [`run_manifest.json`](../qa/aw086/benchmarks/final100/run_manifest.json) сохраняют пути, порядок, archive PDF indices, sizes, CRC и source SHA, полную sample/config/hardware идентичность. Final100 manifest совпал с historical initial100; проверены все 100 members, включая failed cases. Не заменяйте ошибки другими PDF и не пересортировывайте sample.

Production source reference: annotated tag `AW0.86`. Старые measurements выполнены на uncommitted safe source: их собственные hashes находятся в manifests; старый Git HEAD сам по себе не воспроизводит рабочее дерево. Перед повторением в AW0.9 используйте отдельный output/logs и изолированные user/TM DB. Ничего не запускайте поверх прежнего benchmark output.

## Settings and methodology

- Same100: source Auto → RU, domain Auto, device Auto, original Automatic policy, default threads; translation of filenames/folders включена как в baseline. Pipeline depth 2, prepare 1, semantic 1, writer 1, один GPU owner.
- Same100 cold models, explicit warmup 0; sample scan входит в wall. Full-source/sample identity preflight находится вне wall. Не добавляйте prewarm, новые resource caps или full-input cache.
- Fixed20 и fixed5 имеют собственные manifests/configs/warmup contracts; они не заменяют same100.
- Сравнивайте statuses, destinations, ZIP inventory/order/CRC, failed exact bytes/path, IDs/numbers, normalized PDF text/objects и зафиксированные render probes. Единственное допускаемое byte различие translated PDF в final100 — generated trailer `/ID`; failed source bytes совпадают без нормализации.
- Inclusive stages могут перекрываться. Stage occupancy использует interval-union с историческим priority, не причинный critical path.
- Forecast formulas: [`full_archive_forecast.json`](../qa/aw086/benchmarks/final100/full_archive_forecast.json); family weights, `Random(81)`, 2000 within-family bootstrap draws. Historical optimistic/typical/conservative scenarios сохраняют latency overlap. Direct forecast = `1428.599026 × 17211 / 100 / 3600` часов.

Existing helpers сохранены в `tools/aw081_speed_calibration_100.py`, `aw081_speed_calibration_report.py`, `aw081_100pdf_final_speed_calibration.py`, `aw081_100pdf_final_calibration_report.py` и связанных support files. Эти исторические helpers используют исходные локальные QA paths; перед будущим approved run настройте отдельные paths/QA destination в копии harness, восстановите sample по manifest и соблюдайте существующие gates. Команды в данной задаче не запускают измерения.

## Research and retention

Rejected NMT prototype: [`qa/experiments/nmt_batch_scheduler`](../qa/experiments/nmt_batch_scheduler/README.md). Captured 994 native inputs и options сохранены отдельно; они не являются PDF benchmark и их inference savings нельзя переносить в whole-run forecast.

В Git сохраняются reports, manifests, summaries, hashes, compact traces, необходимые regression fixtures и маленький prototype ZIP. Полные corpus/output ZIP, model weights, environments, giant duplicate logs и rendered copies остаются локально. `tools/aw086_release_evidence.py` только копирует evidence и извлекает уже сохранённые native requests, не запускает перевод.
