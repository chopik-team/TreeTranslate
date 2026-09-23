# TreeTranslate AW 0.6.1 — Production PDF polish

Дата проверки: 23 сентября 2026. Реальный workspace: `C:\TreeTranslate`.

## Что исправлено

Обязательное китайское руководство `维修程序.pdf` теперь проходит весь pipeline. Первопричиной сбоя был не PDFium и не embedded font: PDF содержал отдельные CJK glyph objects, латинские обозначения GDS/ITM/IVT имели другой размер, а прежняя группировка объединяла их по слишком жёсткому размеру шрифта. После записи отдельные блоки переставлялись, поэтому validation ошибочно не находила видимый перевод.

Исправление группирует объекты сначала по физической baseline-строке с допуском относительно меньшего шрифта, затем сортирует по X. Номера процедур и абзацы больше не объединяются с соседней строкой. Дубликаты glyph paint objects сохраняются в том же segment. Реальный документ: 4 исходные страницы, 76 logical segments, запись и повторное открытие проходят; результат имеет 5 страниц из-за continuation blocks.

Дополнительно устранён источник длинной паузы на стадии `WRITING`: большой Unicode-шрифт больше не разбирается и subset-ится заново для каждого блока. Для страницы строится один объединённый subset с общей ToUnicode map. Измерение writer на automotive сократилось примерно с 13.0 до 2.2 секунды, на SilverStone — с 6.8 до 2.7 секунды.

Добавлены безопасные diagnostics: `stage`, `operation`, `page`, `object_index`, `object_type` и native error code. В лог не попадают исходный текст, перевод или содержимое блока. Пользователь получает «Не удалось обработать структуру PDF. Ошибка обработки на странице N», а технический контекст остаётся в developer log.

## Политика объектов

Каждый extracted object получает одну из политик `SUPPORTED`, `TRANSLATABLE`, `CONSERVATIVE_PRESERVE` или `UNSUPPORTED_FATAL`. Form XObjects, clipped/stroked/invisible text, skewed matrices, unsupported embedded fonts и native object errors сохраняются без перевода с предупреждением. Fatal остаётся только для невозможности безопасно открыть, записать или проверить документ.

## Layout и reflow

Для блока вычисляется `available_bbox`. Геометрический анализ учитывает соседние блоки, поля, изображения и векторные горизонтальные/вертикальные линии. Регионы классифицируются как heading, paragraph, numbered step, bullet, warning, table cell или footer. В таблицах сохраняются grid, checkmarks, background и исходные vector objects; текст получает границы ячейки. Новый текст сначала переносится в доступной области, затем используется controlled vertical flow и умеренное уменьшение до readable minimum 8 pt. Остаток помещается на continuation page с заголовком и ссылкой `Страница · блок`; PDF annotations не используются как обычный overflow.

На предоставленном automotive PDF визуальная проверка показала сохранённые изображения, предупреждающие рамки и порядок процедур. На SilverStone сетка и галочки остались видимыми, названия игр не исчезли, annotation count равен нулю.

## Fidelity policy

До публикации проверяются числовые значения, диапазоны, единицы и общие identifier/title patterns. GDS, ITM, IVT, PC, PS4, Xbox, model/version-like identifiers и короткие product/game titles не передаются как обычная проза. Если модель изменяет число или идентификатор, исходный segment сохраняется с предупреждением. В коде нет списка SilverStone titles.

Источник `Руководство_Замена_антифриза_ITM.pdf` использовался только как визуальный reference: иерархия заголовков, предупреждения, изображения рядом с шагами и читаемый размер шрифта. Его дополнительные технические сведения не копировались в перевод.

Набор `tests/fixtures/pdf/semantic-corpus.json` содержит исходные фрагменты, проверяемые invariants и запрещённые additions. Exact-string translation не требуется. Запрещённые additions включают P-OAT, этиленгликоль, дистиллированную воду, объяснения stepper/open-loop ITM, сжатый воздух, connector click и новый финальный чек-лист.

## Regression results

| Document | Pages | Segments | Continuation | Annotations | Images | Numeric/IDs | Source SHA unchanged |
|---|---:|---:|---:|---:|---:|---|---|
| automotive `维修程序.pdf` | 4 → 5 | 76 | 12 | 0 | 19 | pass | yes |
| SilverStone compatibility | 1 → 1 | 40 | 0 | 0 | 0 | pass | yes |

`docs/qa/aw061/gates.json` подтверждает одинаковые размеры страниц, byte-equivalent image data, нулевые выходы текста за страницу и отсутствие пересечений written boxes. Background-only PNG comparisons: 0.0 difference ratio on all original pages. Каждый output открывается PDFium и Poppler.

## Что осталось ограничением

OCR не внедрён. Текст внутри изображений не переводится. Вертикальный CJK, RTL, произвольный skew, tagged PDF semantics, цифровые подписи, PDF/A conformance и произвольные интерактивные формы не обещаются. Мультиязычный документ использует document-level язык по умолчанию и conservative segment routing для явно другого substantial language. Модель M2M100 всё ещё может ошибаться в технической лексике; код не подменяет перевод сведениями из стороннего русского PDF.

## Проверки и артефакты

- Полный набор тестов после оптимизации проверен отдельными процессами: **259 passed** в основном наборе (`docs/qa/aw061/final-tests-core.xml`) и **8 passed** в Qt document-service наборе (`docs/qa/aw061/document-service-tests.xml`), всего **267 passed**. Отдельный запуск document-service также проходит совместно с его соседними UI-модулями. На этом Windows-хосте редкий общий запуск всего pytest-процесса получает native access violation при переходе к Qt scanner test; это межтестовый сбой процесса, а не assertion или ошибка PDF writer.
- Реальные документы: `docs/qa/aw061/real-world.json`.
- Геометрия, изображения, числа, IDs и overlap gates: `docs/qa/aw061/gates.json`.
- Semantic corpus: `tests/fixtures/pdf/semantic-corpus.json`.
- Poppler/PDFium PNG: `docs/qa/aw061/automotive` и `docs/qa/aw061/silverstone`.
- Переведённые PDF: `output/pdf/aw061/automotive_ru (3).pdf` и `output/pdf/aw061/silverstone_en (3).pdf`.
- `python -m compileall -q app tools`: pass.
- `git diff --check`: pass.

В AW 0.6.1 изменены PDF extraction/grouping, diagnostics, fidelity guard, region/reflow writer, tests, fixtures, version/changelog и QA tooling. PaddleOCR и обучение моделей не начинались.
