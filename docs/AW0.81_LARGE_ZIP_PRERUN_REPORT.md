# TreeTranslate AW0.81 — LARGE ZIP PRE-RUN REPORT

**DIAGNOSTIC LIVE RUN READY.** Цель этой итерации — первый живой диагностический прогон через GUI с сохранением результатов и данных при ошибке отдельного PDF. Это не semantic quality PASS, не исправление 361 MAJOR, не Frozen B PASS и не release-ready translation.

## Изменение относительно предыдущего отчёта

Историческая первая оценка A сохранена: 342 PASS, 512 MINOR, 361 MAJOR, 4 CATA, 11 document processing failures; один exact BODY overlap. После разрешения пользователя A используется как development/diagnostic data. Исправлены только четыре известные CATA через проверяемые действия, объекты и отношения; полный semantic review 1219 блоков не повторялся. Старый pre-run отчёт сохранён в `qa/aw081/iterations/15_diagnostic_live_readiness/before/docs/`.

PHASE A DEV / LEVEL 3 сохраняют прежние результаты. Текущий full pytest: **1177 PASS**, 0 failures/errors; 306.79 seconds. Production hashes до/после совпали, и совпадают с текущим кодом. [execution.json](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/full_pytest_final/execution.json).

## Четыре известных CATA

Системные причины: потеря домкрата и пространственного отношения при поддержке агрегата; потеря затяжки винта прокачки; инверсия нажатия/удержания педали. Расширен существующий closed-directives composer: проверенные полные noun slots, отдельные падежные формы, повторное действие, максимальная отметка жидкости и последовательность действий одного помощника. Неизвестные объекты, хвосты, условия и разные педали отклоняются целиком. Guards отвергают утрату инструмента, отношения «под», затяжки и удержания нажатой педали. Не добавлены полные предложения в Knowledge и не изменён NMT.

Добавлены два терминологических concepts — домкрат и винт прокачки; существующие concepts поддона, transaxle и бачка переиспользованы. `油盘` ограничен контекстом домкрата; `储液箱` — контекстом тормозной жидкости. Automatic frontier остаётся unverified, автоматически Knowledge не меняет.

Итог: **из четырёх известных CATA осталось 0**. Проверены реальные полные PDF и видимость опубликованных действий/объектов. Это проверка известных случаев, не гарантия отсутствия других CATA. [publication review](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/operational/cata_publication_review.json).

## Archive error policy

Внутри обработки одного member ошибки перевода, PDF parsing/extraction/OCR, writer/validation, IndexError и иная неподдерживаемая структура сохраняют оригинальный member **с точным исходным путём и байтами**. Статус `FAILED_SOURCE_PRESERVED`; ошибка записывается, следующий member обрабатывается. Успешные документы имеют `TRANSLATED`; failed не передаются callback, помечающему файл переведённым. Права на исходные имена/вложенные каталоги резервируются заранее, чтобы перевод имени не занял путь сохранения оригинала.

Фатальными остаются archive security/unsafe path, input CRC/integrity, изменение source/member, OSError (включая ENOSPC), критическая ошибка archive writer, финальная валидация и публикация. Отмена остаётся отменой. Archive failures дают `FATAL_ARCHIVE_FAILURE`, отмена `CANCELLED`. Временные файлы убираются; результат публикуется атомарно и без перезаписи только после полного CRC/inventory/source immutability checks. Hard crash может оставить staging/temp; automatic retry/resume нет.

При хотя бы одном сохранённом ошибочном документе run = `COMPLETED_WITH_FAILURES`, а не SUCCESS. Summary содержит `total_documents`, `translated_documents`, `failed_documents`, `source_preserved_documents`, `skipped_non_documents`, `fatal_errors`, `document_error_categories`; для завершённого archive selected-documents `translated + source_preserved = total`. Все выбранные 46 PDF проверены этой инвариантой.

## Реальный operational regression: 46 PDF

Normal scanner, DocumentJob, ArchiveJob, production router/NMT/PDF writer; изолированные пользовательские базы QA, только 46 ранее выделенных PDF из Diagnostic A. Подготовленный ZIP из этих документов — не большой архив 17 211 PDF. Полный semantic review не проводился.

Processed **46**, translated **35**, failed/source-preserved **11**, fatal **0**. Run status `COMPLETED_WITH_FAILURES`, logging `COMPLETE`; время 1350.15 seconds. Итоговый ZIP существует и открывается, CRC PASS, содержит ровно 46 PDF и вспомогательный JSON; каждый failed PDF побайтно совпадает с входным member, source archive SHA неизменен. Byte SHA всех успешных members совпадает с нормальным результатом child DocumentJob: политика recovery и упаковка не меняют успешный PDF. Targeted A/B test дополнительно сравнил текст и pixels следующего успешного PDF с/без предшествующей ошибки, logging on/off — те же content/pixels.

Предыдущие 11 failures, индексы нулевые:

| Index A | До | Сейчас |
|---|---|---|
| 2 | TranslationError | FAILED_SOURCE_PRESERVED |
| 3 | TranslationError | FAILED_SOURCE_PRESERVED |
| 15 | PdfError | FAILED_SOURCE_PRESERVED |
| 17 | PdfError | FAILED_SOURCE_PRESERVED |
| 19 | IndexError | FAILED_SOURCE_PRESERVED |
| 23 | PdfError | FAILED_SOURCE_PRESERVED |
| 27 | PdfError | FAILED_SOURCE_PRESERVED |
| 32 | PdfError | FAILED_SOURCE_PRESERVED |
| 36 | PdfError | FAILED_SOURCE_PRESERVED |
| 41 | TranslationError | FAILED_SOURCE_PRESERVED |
| 42 | PdfError | FAILED_SOURCE_PRESERVED |

Сопоставление с первой оценкой A: 32 предыдущих успешных документов имеют одинаковые candidate translations, 3 имеют изменения. Это **не новый semantic grade**: CATA grammar/guards и обычный archive context отличаются от прежних отдельных jobs. Список различий сохранён в execution.json и не использован для исправления остальных MAJOR. Проверка неизменности на границе archive policy выполнена отдельно по точным SHA успешных child outputs и targeted A/B tests.

ZIP: `C:\TreeTranslate\output\aw081\diagnostic-live-readiness\Diagnostic A_ru.zip`. SHA: `fcce98d93edf4bf2eaca066e2641156082e872ac049d0e68cd164796dc43c29c`.

Logs QA: `C:\TreeTranslate\qa\aw081\iterations\15_diagnostic_live_readiness\operational\logs\eaa3f9880650`. [Operational evidence](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/operational/execution.json).

QA receipt восстанавливался из final SQLite bindings: первоначальный postprocessor ошибочно ожидал final member path в раннем JSONL checkpoint. Исходный stderr сохранён; processing run завершился штатно, translation не повторялся. Все CRC/байтовые/SHA проверки выполнены повторно по финальным привязкам. Это ошибка QA postprocessing, не дополнительный document/archive failure.

## Layout остаётся открытым

Известные table overlap документов A 24/25 занесены в source-SHA advisory registry. В GUI run warnings и `quality_sample_manifest.json/known_layout_overlap` сохраняют связь с final member, layout = `WARNING_KNOWN_OVERLAP`. Registry не является detector остальных страниц. Structural PDF validation PASS не превращается в layout PASS; прочие документы имеют `NOT_EVALUATED`. Переписывание layout и исправления всех наложений не выполнялись.

## Logging

Offline local JSONL и SQLite WAL; flush после документа и регулярные checkpoints. Failed document: document_id, member path, source SHA, stage, primary/secondary categories, exception type, elapsed, preserved yes/no, безопасные stack locations и числовые PDF diagnostics. Полный document text, exception messages и locals не записываются в application logs. QA captures/reference PDFs для регрессии хранятся отдельно от production logs.

Статусы `TRANSLATED`, `FAILED_SOURCE_PRESERVED`, `FATAL_ARCHIVE_FAILURE` и run `COMPLETED_WITH_FAILURES` проверены. Sample включает failed documents и known overlap, а также прежние random/domain/model/unknown/warnings/OCR/table/slow/page changes. Frontier автоматически не публикуется. Coverage и model fallback не являются quality score. Peak VRAM остаётся unavailable, если существующий allocator не инициализирован.

`TRANSLATED` означает успешно созданный и структурно проверенный документ, не semantic/layout acceptance всех блоков: отдельные unsafe blocks могут сохранить китайский source. Legacy `translated_mb_per_hour` использует общий output_bytes, включая original-preserved bytes; точную скорость только переведённых PDF следует вычислять по размерам записей со статусом `TRANSLATED`. При ручном выборе части архива `skipped_non_documents` включает невыбранные members; при выбранном целом CN7C ZIP это три JSON assets. Эти поля не следует использовать как доказательство полного перевода.

Исторический benchmark предыдущей итерации: median logging overhead **1,51%** на двух небольших DEV native PDF. Это не свежая оценка стоимости нового archive recovery и не прогноз скорости 17k mixed/OCR corpus. В этой итерации logging on/off проверен по semantic text и pixel output, без повторного большого performance benchmark.

## Большой CN7C ZIP: только preflight

Источник: `C:\Users\PC\Downloads\2022_USER_REPAIR_MAINTENANCE_DISASSEMBLE_(CN7C)_CHINA_koreacustom.ru.zip`. SHA `ecc0fd54bbc421af33febcb4f971e9a4735b15102aae9c451334a449c3a85330`. Размер 1,945,071,930 bytes; members 22,836, directories 5,622, files 17,214, **17 211 PDF +3 JSON**. Полное число страниц неизвестно. Security central-directory PASS; полный input CRC **NOT RUN** и будет проверен обычным GUI scan.

Disk budget: production 6,010,578,678 bytes; logs allowance 4,511,760,384 bytes. Оценки — не hard upper bounds. Combined C: need 10,522,339,062 bytes; free 156,875,190,272 bytes. Disk READY, CUDA available; Auto может использовать CPU fallback. Temp хранит только текущий member/результат и растущий staging ZIP; external OCR caches учитываются отдельно. [Fresh preflight](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/large_zip_preflight.json).

## Ваш ручной запуск

Откройте текущую рабочую версию через `C:\TreeTranslate\run_dev.bat`, выберите большой ZIP, Chinese→Russian, обычный device/threads и папку результата; запустите обычной кнопкой. Старый exe/другая копия могут не содержать изменений. Прогон через Codex или CLI не нужен. GUI использует обычные пользовательские базы, в operational QA они были изолированы.

Результат — выбранная GUI output folder либо папка source ZIP; collision-safe имя покажет приложение. Полные GUI logs: `C:\Users\PC\AppData\Local\CHOPIK Team\TreeTranslate\logs\document_runs\<run_id>\`. Один translation run_id связывает весь archive; предварительный scan имеет отдельный связанный scan_run_id и scan_seconds, время ожидания кнопки не включается в translation wall time.

После своего запуска передайте итоговый ZIP, всю папку run_id журналов, выбранные настройки и наблюдения о скорости/зависаниях/подозрительных страницах. На этой машине достаточно абсолютных путей. При глобальном сбое final ZIP может отсутствовать — журналы всё равно пригодны для анализа.

**STOP: большой ZIP не запускался.** Изменены только AW0.81, четыре известных CATA, archive failure policy и диагностика/тесты. Новых экранов/компонентов и UI redesign нет; существующая progress panel получила честный статус завершения с ошибками. AW0.82, PHASE B/C, Frozen B, installer и остальные MAJOR не выполнялись.
