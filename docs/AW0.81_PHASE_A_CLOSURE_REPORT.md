# TreeTranslate AW0.81 — завершение PHASE A и проверка допуска

Дата: 2026-10-04T17:04:20.311758+00:00. Текущая задача проверки завершена. **Релиз и полный большой ZIP не получили допуск: Frozen A FAIL.** Оценка Codex, без независимой человеческой сертификации.

| Gate | Результат |
|---|---|
| PHASE A, проверенный DEV acceptance scope | PASS |
| LEVEL 3, BODY/coolant regression | PASS |
| Общий pytest после GUI logging | PASS: 1138 тестов |
| Первый whole-production Frozen A | FAIL: семантика, обработка PDF, layout, независимость |
| Локальные журналы, включая обычный GUI | READY |
| Полный ZIP | Не запускался; общий допуск NOT READY |

## История и 18 фрагментов

Исторические raw-line grades **108 PASS / 31 MINOR / 18 MAJOR / 0 CATA** не изменены. Это не новая оценка целых документов. Каждый из 18 MAJOR связан с конкретным полным native parent, SHA исходника, parent/output SHA и семью условиями допустимой переклассификации. Новая классификация **NOT_EVALUABLE_FRAGMENT: 18**, не PASS. [parent_evidence.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/parents_final_fixed/parent_evidence.json).

Свежая production reconstruction/translation проверила **16 полных parent blocks: 16 PASS, 0 MAJOR/CATA**, без вызова модели. Общий pytest проверил операции, вопросы, отрицания, электрические величины, условия, сравнения и ограничения контекста. Дополнительный полный exhaust PDF: **7 semantic PASS**, 2 защищённых WCC/UCC label; одна операция REMOVE для узла «каталитический нейтрализатор и центральный глушитель в сборе». Компоненты остаются отдельными concepts. [semantic_review.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/exhaust_assembly/semantic_review.json).

Не объединяем старые 157 raw fragments, новые 16 parents, BODY labels и whole-PDF semantic blocks в искусственный общий процент качества. Остальные исторические 31 MINOR не объявляются автоматически свежими whole-PDF PASS. PHASE A PASS относится к ранее принятому DEV scope и проверенным полным parents; это не обещание корректного перевода любого OEM документа.

## LEVEL 3

Свежий BODY: **7 PDF, 22→22 страницы, 365 segments, 419/419 protected values**, 10/10 известных инструкций PASS. Canonical concept translation 130/131, publication 117/131; strict совпадения 110/131 и 100/131. **23 старых Chinese residue labels сохранены**; новые изменения semantic output относительно принятой BODY baseline — 0. Исходный ZIP immutable, итоговый CRC PASS. Время 176,60 s не является logging overhead: исторический запуск имел другое состояние runtime/OCR caches.

Свежий coolant: реальный native+OCR PDF **4→5 страниц, 108 segments**. Семантическая оценка: **84 PASS / 5 MINOR / 0 MAJOR / 0 CATA**, denominator 89; отдельно **4 SOURCE_AMBIGUOUS, 1 SOURCE_DAMAGED, 14 OCR-noise exclusions**. Неоднозначные units/thresholds не названы PASS. Оборванная cross-reference восстановлена через явное пользовательское OEM-уточнение и остаётся SOURCE_DAMAGED в учёте.

Четыре cross references и три EVAP/GPF candidate translations исправлены. **Две длинные EVAP подписи не публикуются внутри изображения: source сохранён из-за нехватки места.** Всего восемь компактных OCR labels имеют эту publication limitation. Поэтому публикация, отдельно от смыслового candidate result: **76 PASS / 13 MINOR**, те же source/noise exclusions. GPF label опубликован. Предупреждения, отрицания, последовательность операций, числа и continuation page проверены.

Poppler отрендерил все **27 output pages**, сравнение с 26 source pages просмотрено на 11 sheets; новый layout damage в BODY/coolant не обнаружен. Также просмотрен полный exhaust output. [visual_review.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/level3/visual_review.json), [coolant_semantic_review.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/level3/coolant_semantic_review.json), [execution.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/level3/execution.json).

Эта production LEVEL 3 предшествовала только подключению уже проверенного observer к кнопке GUI и записи времени scan. Translation/segmentation/OCR/writer поведение после неё не менялось. Затем повторены весь pytest и logging equivalence benchmark на текущем коде. Нет заявления о новом полном LEVEL 3 после GUI wiring.

## Общий pytest и logging

**1138 passed**, 0 failed/error/skipped; pytest 266,18 s, wrapper 267.29 s. Два исторических падения исправлены и проходят именно в общей suite. Git HEAD/status, staged/unstaged diff, JUnit, stdout/stderr, timing и production hashes сохранены. Никаких commits/reset. [execution.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/full_pytest_final_gui/execution.json), [junit.xml](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/full_pytest_final_gui/junit.xml).

Обычный GUI run испытан на ZIP с двумя DOCX: source SHA unchanged, final archive CRC, два document records, sample manifest, scan link и content-safe logs. Совместно 14 GUI/service/observer tests PASS. Пять пар logging off/on: median overhead **1.51%**, цель <5% выполнена. PDF text, normalized objects и pixel rendering совпадают; raw PDF SHA отличаются только случайными PDFium trailer IDs и записаны отдельно. [benchmark.json](C:/TreeTranslate/qa/aw081/local_metrics_self_test/5982cc3d7e2e411aa263d8564433be65/benchmark.json).

## Frozen A — результаты первого полного production прогона

Все **46 PDF / 46 groups / 2651 historical native-line strings** обработаны отдельными обычными DocumentJobs; переведены только эти 46 выбранных PDF, не архив из 17k PDF. Source 69 pages. Из **46** документов writer validation прошли **35**, упали **11**. Для успешных документов **52 source pages →77 validated output pages**; validation не равен semantic/layout PASS. Четыре selected output pages дополнительно отрендерены и просмотрены: таблицы PDF 24/25 имеют наложения текста и порогов. Все 77 output pages визуально не просмотрены.

| Semantic grade, опубликованные successful-document blocks | Число |
|---|---:|
| PASS | 342 |
| MINOR | 512 |
| MAJOR | 361 |
| CATA | 4 |
| SOURCE_AMBIGUOUS | 3 |
| SOURCE_DAMAGED | 3 |
| NOT_EVALUABLE_FRAGMENT | 0 |
| Protected identifiers/values и OCR noise, вне denominator | 562 |

Semantic denominator **1219**; 11 failed documents не названы PASS и не включены в этот denominator. Предварительный мини-отчёт содержал 360 MAJOR/513 MINOR; после render подтверждена дополнительная ошибка читаемости порога: итог **361 MAJOR/512 MINOR**. Предварительная версия сохранена.

CATA evidence: PDF 5 теряет домкрат/правильную поддержку двигателя и трансмиссии перед снятием опор; PDF 9 заменяет затяжку bleed screw на нажимание и нажатие/удержание педали на её поднятие. MAJOR: wrong ground/relay/valve nouns, неверные quantity relations, dropped diagnostic questions/No, source-preserved whole prose, split source sentences, writer overlap. Ошибки обработки: 3 TranslationError (negative-sign guard), 7 PdfError и 1 IndexError. Причины PdfError ещё не установлены; публичное сообщение «файл повреждён» не доказывает SOURCE_DAMAGED.

Проверка независимости обнаружила **1 exact source overlap** с BODY: PDF 13. Поэтому утверждение «все 46 полностью untouched» неверно. По данному audit независимый subset **45 PDF**; его grade counts: `{'PASS': 329, 'MAJOR': 361, 'EXCLUDED_PROTECTED_OR_OCR_NOISE': 497, 'MINOR': 508, 'SOURCE_DAMAGED': 3, 'CATA': 4, 'SOURCE_AMBIGUOUS': 3}`. Это не исчерпывающий audit всех исторических источников. [independence_audit.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/independence_audit.json).

Logs: model fallback **1349/1950 = 69.18%**; materially knowledge-constrained **786/1950 = 40.31%**. Direct known 321, glossary 702, templates 84, composition 2, model calls 1544; route counts могут пересекаться. Эти denominators включают completed segments failed documents и отличаются от ручного published-block denominator; **не являются качеством**. Warnings 3592, protected/noise 519, unit guards 51, negation guards 40, object guards 26, action guards 1; некоторые показатели detectors unavailable, не ноль. Время выбранного QA прогона **1294.11 s** не прогноз большого ZIP и не GUI benchmark.

[final_evaluation.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/final_evaluation.json), [semantic_review.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/semantic_review.json), [execution.json](C:/TreeTranslate/qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/execution.json).

## Решение

**PHASE A DEV и LEVEL 3 regression приняты; общий release/large ZIP quality gate FAIL.** A переведён в роль Diagnostic A, manifest/history не изменены. Никаких исправлений из A в текущей задаче; следующий цикл исправлений потребует нового untouched Frozen B. PHASE B/C не начинались, AW0.82 не создан, NMT не заменён, UI screens не переделаны, installer не добавлен. Текущая задача остановлена после отчётов; большой ZIP не запускался.
