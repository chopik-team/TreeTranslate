# TreeTranslate

**AW0.86 — technical alpha / development release.** Consolidated best known production в конце engineering cycle AW0.8x. Это source freeze, не 1.0; Windows installer и веса моделей в этот release не входят.

> Your PC. Your files. Your rules.

TreeTranslate — offline-first и privacy-first приложение CHOPIK Team для локального перевода текста, DOCX, текстовых PDF, сканов, папок и ZIP. Argos и M2M100 / CTranslate2 работают локально; PaddleOCR распознаёт изображения. Подтверждённые Knowledge/glossary и translation memory помогают сохранять терминологию. Доступны Auto/CPU/GPU; обязательного облака и runtime telemetry нет. Модели готовятся отдельно, приложение не скачивает их при переводе.

Оригиналы не изменяются. ZIP обрабатывается по members без полной распаковки corpus; имена переводятся lazy, коллизии разрешаются безопасно. Failed documents сохраняются по исходным paths и bytes, остальные members продолжают обработку. Итог проверяется и публикуется без перезаписи. RAR/7z и рекурсивная распаковка вложенных архивов не поддерживаются.

## Официальный benchmark

Same 100 PDF на Ryzen 7 5700X / 32 GB / RTX 3080 12 GB: **79,73 → 23,81 мин**, **3,35×**, **−70,14% wall**, около **252 обработанных PDF/час**. 76 переведены / 24 исходника сохранены / 0 fatal; output equivalence PASS. Скорость включает failures и зависит от corpus/hardware. Benchmark уже измерен, при release closure не повторялся.

Direct estimate для 17 211 PDF: **68,30 часа** непрерывной обработки. Это прогноз, полный корпус не прогонялся. [Performance](docs/PERFORMANCE_AW0.86.md), [benchmark history](docs/BENCHMARK_HISTORY.md), [reproducibility](docs/BENCHMARK_REPRODUCIBILITY.md).

## Запуск из исходников

Windows, Python 3.12. Установщик пока не предоставляется. Dependencies и model/data manifests находятся в repository; model binaries, большая lexicon database, environments и corpus остаются локальными. Подготовка словарных данных описана в developer instructions; reference SHA сохранены в freeze evidence.

```powershell
python -m venv .venv
.venv\Scripts\python tools/install_runtime.py
# Дополнительные GPU dependencies при необходимости:
.venv\Scripts\python -m pip install -r requirements-gpu.txt
.venv\Scripts\python tools/verify_models.py
.venv\Scripts\python main.py
```

До запуска подготовьте локальные модели по manifests в `vendor/models/` и developer instructions в [историческом техническом README](docs/README_AW0.8x_HISTORY.md). Argos устанавливается штатным `install_runtime.py` с предусмотренной dependency policy; обычная установка всех его upstream dependencies не является инструкцией этого проекта. Model licensing и чистая установка будут отдельно проверены в AW0.9. [Third-party notices](THIRD_PARTY_NOTICES.md).

## Состояние и документы

- [CHANGELOG: milestones 0.81–0.86](CHANGELOG.md)
- [AW0.86 release notes](docs/releases/AW0.86.md)
- [Freeze receipt](docs/AW0.86_FREEZE_RECEIPT.md) и [closure report](docs/AW0.86_RELEASE_CLOSURE_REPORT.md)
- [Known issues](docs/KNOWN_ISSUES.md): 24 preserved failures не исправлены этим release; техническая целостность не гарантирует смысловое качество каждого перевода.
- [Rejected NMT research](docs/research/REJECTED_EXPERIMENTS.md): prototype изолирован и не активен в production.
- [AW0.9 preliminary scope](docs/AW0.9_SCOPE.md): stabilization/release preparation; roadmap утверждается отдельно.

Для разработчика: `python -X utf8 -m pytest -q`. Full-suite baseline, актуальные SHA и static checks перечислены в freeze receipt. Исторические отчёты не переименованы; большие raw QA paths в них относятся к локальному архиву. Компактные manifests/summaries и нужные regression fixtures сохранены в Git. Не добавляйте corpus ZIP, translated outputs, model weights или environments в repository.

AW0.86 закрывает engineering cycle 0.8; AW0.9 готовит релиз; 1.0 будет первой полноценной публичной Windows version. Последующие 1.1+ могут улучшать качество, совместимость, производительность и UX.
