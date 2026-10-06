# AW0.86 — известные ограничения

Technical alpha / development release, не 1.0. Engineering/performance freeze не означает принятие смыслового качества всего corpus.

## Final100 failures

| Category | Exception | Count |
|---|---|---:|
| VALIDATION | PdfError | 17 |
| UNSUPPORTED_STRUCTURE | IndexError | 6 |
| MODEL_LIMITATION | TranslationError | 1 |
| Total FAILED_SOURCE_PRESERVED | | **24** |

Для каждого из этих members исходный path и bytes сохранены точно, остальные members обрабатываются дальше. В final100 76 TRANSLATED / 24 preserved / 0 fatal; exact preservation, paths и CRC проверены. [Per-member evidence](../qa/aw086/benchmarks/final100/output_equivalence.json).

Эти cases не исправляются и не обещаются исправленными в AW0.86. Triage и оценка системных причин включены в preliminary AW0.9 backlog.

## Другие пределы

- Ошибка переводческого смысла возможна и при технически валидном PDF. Исторические quality findings сохраняются; freeze не переоценивает Frozen Set или semantic acceptance.
- Сложные PDF/table layouts, ограничения шрифтов, длинные инструкции и OCR могут сохранять исходные блоки, создавать продолжения либо приводить к document-level failure. Детали — в исторических PDF/quality reports.
- Входной архив runtime — ZIP. RAR/7z обозначаются как неподдерживаемые; вложенные архивы не распаковываются рекурсивно.
- Pause/cancel cooperative: текущий native inference может завершиться до остановки. Recovery повторно сканирует выбранные пути и ожидает запуска, а не возобновляет последний сегмент.
- ETA приблизительная, уточняется по сложности и фактической работе; может увеличиваться после уточнения. Большой ZIP не открывает все PDF заранее ради оценки. [ETA](AW0.81_LIVE_ETA.md).
- Модели и environments не включены в source release. Offline launch на чистой Windows, dependencies/model packaging и licensing audit — задачи AW0.9. Отдельные upstream model license entries имеют UNKNOWN status в manifest; этот release не распространяет их веса.
- Rejected NMT scheduler не включён в production. Новое исследование требует нового exact-output gate.

[AW0.9 scope](AW0.9_SCOPE.md) предварительный; реализация начнётся после отдельного утверждения roadmap.
