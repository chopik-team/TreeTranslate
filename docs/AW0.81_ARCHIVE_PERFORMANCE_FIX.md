# AW0.81 — исправление подготовки архива

**PERFORMANCE FIX PASS.** Реальный CN7C smoke `348ec1dddc71`: первый child DocumentJob стартовал через **3,19 с после обязательного preflight**, при цели `<10 с`. Обработаны ровно первые пять PDF: **3 TRANSLATED, 2 FAILED_SOURCE_PRESERVED, 0 fatal**. Полный архив не переводился и итоговый ZIP не публиковался: после упаковки пятого документа выполнена контролируемая отмена. Это проверка производительности и восстановления, а не новая оценка качества перевода.

## Причина и исправление

Run `60176d6968b2` был отменён через 997,12 с до завершения первого документа. Подготовка заранее переводила все каталоги, создавала для каждого DocumentProfiler/Knowledge snapshot и запускала обычный семантический конвейер. Runtime при смене backend выгружал предыдущую модель даже внутри `keep_warm`; Argos дополнительно выгружал переводчики при переключении CUDA/CPU.

Теперь на старте резервируются только строки исходных путей файлов и каталогов с прежней нормализацией NFC/casefold. Каталоги и имена переводятся при обработке конкретного member; для документа — при выборе пути результата. Записи каталогов не запускают перевод до документов; явные пустые каталоги сохраняются в конце. Имя итогового ZIP определяется перед публикацией.

Для путей используется отдельный лёгкий вход: существующие Knowledge/glossary, защита кодов и чисел, прежний model router. Он не запускает TM, DocumentProfiler, шаблоны процедур или полный семантический конвейер документа. Общий кеш компонентов ограничен 4096 результатами на архив; ключ учитывает язык, домен, контекст/snapshot и настройки inference. Существующий кеш имён каталогов также сохранён.

Во время `keep_warm` переключение между backend больше не выгружает рабочую модель. Argos сохраняет переводчики отдельно для пары языков/device/compute type/threads. M2M100 переиспользует модель при изменении только beam/batch/лимитов декодирования; эти параметры по-прежнему передаются в каждый inference. Idle shutdown, полный shutdown и освобождение моделей перед OCR сохранены.

Circuit breaker действует в пределах одного run для подтверждённых ошибок модели/устройства; учитывает backend, пару языков, route, device, compute type и threads. Следующий run снова пробует загрузку. Обычная ошибка перевода конкретной строки не отключает backend: это могло бы изменить результаты других документов.

## Замеры

Реальный источник: `2022_USER_REPAIR_MAINTENANCE_DISASSEMBLE_(CN7C)_CHINA_koreacustom.ru.zip`, **17 211 PDF**, SHA-256 `ecc0fd54bbc421af33febcb4f971e9a4735b15102aae9c451334a449c3a85330`. Настройки smoke: auto→ru, Auto device, Automatic profile, auto domain, перевод папок и имён включён; TM/user glossary изолированы в QA.

| Метрика | Результат |
|---|---:|
| Обязательный scan с CRC | **3,10 с**; прежний GUI scan 3,26 с |
| Preflight от запуска job | 3,43 с |
| Первый document start после preflight | **3,19 с** |
| Первый document start от запуска job | 6,62 с |
| Первый document complete после preflight | **101,25 с** |
| OCR первого PDF | 86,69 с, 3 вызова |
| Перевод путей первых пяти PDF | **1,99 с**, 8 вызовов |
| Загрузки Argos | **2**, суммарно 0,43 с: CUDA/CPU |
| Реальные загрузки M2M100 | **1**, 0,69 с |
| M2M100 load-or-reuse | 31 вызов, всего **0,75 с** |
| M2M100 inference | 31 вызов, 5,62 с |
| Model attempt failures | **4**: Argos CUDA 2, CPU 2, `TranslationError` |
| Исходный ZIP неизменён / staging удалён | **PASS** |

Первый PDF действительно использует OCR. Ускорение подготовки не устраняет время OCR или ошибки качества. В исходном run по сохранившимся текстовым timing logs было 582 загрузки Argos (124,62 с), а M2M100 load-or-reuse занимал 210,00 с против 25,31 с inference. Текстовые журналы ротируются; эти числа относятся к сохранившимся строкам, не к гарантированно полному log.

| Вызовы | Старый run: до первого child | Smoke: до первого child | Smoke: всего на пяти PDF |
|---|---:|---:|---:|
| DocumentProfiler | 2053 | **1** — общий профиль архива | 6 |
| knowledge_snapshot | 2053 | **1** — общий snapshot | 6 |
| translation_memory | 2052 | **0** | 50 |
| glossary_lookup | 8032 | **0** | 223 |
| template_routing | 2052 | **0** | 50 |
| engine_translation | 2052 | **0** | 30 |
| model_translation | 2632 | **0** | 42 |
| path_translation | ранее отдельного этапа не было | **0** | 8 |

Третья колонка показывает отсутствие массового перевода путей до начала документа. Последняя включает нормальную обработку документов и их путей; это другой объём работы. Счётчики рассчитаны как сумма `count` в stages.jsonl, а не число агрегированных JSONL-строк. Создано 5 уникальных переводов компонентов каталогов; остальные обращения к уже созданным путям обходят перевод. LRU cache: 8 misses, 0 hits в этой маленькой выборке; отдельный regression подтверждает повторное использование одинаковых компонентов между child jobs.

## Проверки и границы

**Full pytest: 1185 passed, 0 failures/errors/skipped**, 325,18 с по pytest. Production hashes до/после suite совпали. Перед этим прошли 77 точечных проверок архива/runtime/router и 8 проверок performance/lightweight naming.

Synthetic ZIP содержит **2000 записей: 1000 каталогов перед 1000 документами**. На входе в первый child нет ни одного перевода имени/папки и ни одного созданного каталога результата. Проверены резервирование исходных путей, столкновения переведённых папок/файлов, точные исходные пути и байты failed members, продолжение после ошибки документа, отмена, CRC/security/source-change/disk-full/validate/publish failures и атомарная публикация. Политика восстановления остаётся прежней.

Семантические функции `_pdf_translation`, `_run_documents`, Knowledge `translate/_translate/_ensure_safe/_template/lookup_direct` совпадают с состоянием до правки по AST. Существующие 62 конфигурационных/Knowledge файла совпадают по SHA-256. Аргументы native model constructor и inference совпадают по AST; модели, routing policy, терминология и UI-дизайн не изменялись. Имена используют новый лёгкий путь, как предусмотрено задачей. Полный корпус семантически не переоценивался.

Два `IndexError` возникли в существующем Knowledge template matching у PDF с B100352/B100355; исходники добавлены в staging по оригинальным путям и отмечены `FAILED_SOURCE_PRESERVED`. Их исправление не входит в performance-задачу. Сохранение этих ошибок не означает успешный перевод. Три нормальных child PDF прошли штатную writer validation и сохранены отдельно как QA evidence.

Первый измерительный запуск `d7f7d457abe0` **не принят**: ошибка скрипта захвата метрик дублировала аргумент `seconds`, fail-open logging пропустил callback остановки. Запуск был принудительно остановлен после **8 child starts**, источник проверен по SHA-256, staging очищен. Этот запуск не используется для итоговых замеров. В исправленном скрипте выборка жёстко ограничена пятью PDF независимо от callback; принятый повтор остановился после ровно пяти.

## Evidence

- [Принятый smoke и замеры](C:/TreeTranslate/qa/aw081/iterations/16_archive_performance/smoke_bounded/execution.json)
- [Полные журналы smoke](C:/TreeTranslate/qa/aw081/iterations/16_archive_performance/smoke_bounded/logs/348ec1dddc71/run_summary.json)
- [Full pytest receipt](C:/TreeTranslate/qa/aw081/iterations/16_archive_performance/full_pytest/execution.json)
- [Сохранность семантического кода, конфигурации и inference](C:/TreeTranslate/qa/aw081/iterations/16_archive_performance/semantic_scope_checks.json)
- [Анализ старого run](C:/TreeTranslate/qa/aw081/iterations/16_archive_performance/baseline_live_log_analysis.json)
- [Непринятый запуск измерителя](C:/TreeTranslate/qa/aw081/iterations/16_archive_performance/smoke/invalid_execution.json)
- [Ограниченный smoke script](C:/TreeTranslate/tools/aw081_archive_performance_smoke.py)

**STOP.** Только AW0.81 performance fix. Полного перевода CN7C, новой оценки MAJOR/CATA, AW0.82, PHASE B/C, Frozen B, installer или commit нет.
