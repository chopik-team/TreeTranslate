# AW0.81 — калибровка скорости на 100 PDF

**FULL LIVE RUN TOO SLOW / OPTIMIZATION ADVISED**. Критерий: typical ≤ 24 ч непрерывной работы. Порог 24 часа — явное рабочее допущение: пользователь ещё не указал допустимую длительность; verdict пересчитывается при выборе другого порога без нового run. Это оценка времени текущего pipeline, а не качества перевода.

Run `25825c3f75a7`: **100 processed, 76 TRANSLATED, 24 FAILED_SOURCE_PRESERVED, 0 fatal**. Wall time **4 783,64 с / 79,73 мин**. CRC итогового sample ZIP PASS; failed members имеют точные исходные пути и байты. Исходный CN7C ZIP и production-файлы неизменны.

## Выборка

Ровно 100 PDF из 17 211. Страта — второй компонент исходного пути (10 групп руководств/процедур/диагностики/электросхем). Квота: floor(N_group × 100/17211), минимум один PDF; остаток распределяется по наибольшему дефициту. В группе сортировка (size, path), позиции floor((slot+0.5) × N_group/quota). Обработка возвращена в исходный inventory order. Случайности и ручного подбора удобных PDF нет. SHA каждого member проверен; имена и байты сохранены в отдельном 100-PDF ZIP.

| Группа | В корпусе | В sample |
|---|---:|---:|
| 2022  第七代伊兰特(CN7C) G 1.4 T-GDI 部品检查流程 | 3823 | 22 |
| 2022  第七代伊兰特(CN7C) G 1.5 MPI 部品检查流程 | 3294 | 19 |
| 2022 第七代伊兰特(CN7C) G 1.4 T-GDI 故障代码维修指南 | 4033 | 23 |
| 2022 第七代伊兰特(CN7C) G 1.4 T-GDI 电路图 | 329 | 2 |
| 2022 第七代伊兰特(CN7C) G 1.4 T-GDI 维修手册 | 871 | 5 |
| 2022 第七代伊兰特(CN7C) G 1.5 MPI 故障代码维修指南 | 3440 | 20 |
| 2022 第七代伊兰特(CN7C) G 1.5 MPI 电路图 | 331 | 2 |
| 2022 第七代伊兰特(CN7C) G 1.5 MPI 维修手册 | 839 | 5 |
| 2022 第七代伊兰特(CN7C) 电路图 | 209 | 1 |
| 2022 第七代伊兰特(CN7C) 车身维修手册 | 42 | 1 |

Подготовка/scan/readonly metadata вне основного wall time: 5,06 с; scan всего источника с CRC: 3,16 с. Sample source pages: 157; output pages, включая сохранённые оригиналы: 190. Source PDF bytes: 10588668; output member bytes: 12267222; итоговый ZIP: 11342555 bytes.

Предварительная readonly-инспекция: 86 native, 14 mixed, 0 image-only. Production classification: `{'native': 71, 'mixed': 23, 'image_only': 6}`; OCR использован в 34 документах. Значение 'unknown' означает, что pipeline не успел записать классификацию до ошибки; это не native. Детальные metadata и domain/subdomain каждого PDF — в manifest; production-данные вложены отдельно, не подменяют предварительную инспекцию.

Выборка охватывает все 10 групп, размеры и несколько подсистем, но 100 PDF не гарантируют охват редких тяжёлых страниц и максимальных файлов. Предварительная классификация по наличию native текста слабее штатной классификации: production определил 6 image-only, несмотря на навигационные native-заголовки. Максимальный sample PDF — 815 081 bytes, максимальный PDF корпуса — 8 400 159 bytes; редкий большой хвост выборкой не покрыт. Native-слой сам по себе не исключает OCR vector/raster labels. Sample не использован для обучения или публикации Knowledge. TM и user glossary изолированы; builtin Knowledge и настройки pipeline штатные. Архивный контекст построен production-кодом по sample ZIP, поэтому он не побайтно равен контексту всех 17 211 member paths.

Production domains: 94 automotive, 6 general; таблицы отмечены в 78 документах. `schematic_blocks` = 0 у всех документов, хотя выборка включает исходные файлы из групп электросхем и с заголовком «示意图»: это ограничение production-разметки, а не утверждение об отсутствии схем.

## Throughput и latency

| Метрика | Значение |
|---|---:|
| processed_docs_hour | 75,26 |
| translated_docs_hour | 57,19 |
| source_pages_hour | 118,15 |
| output_pages_hour | 142,99 |
| processed_segments_second | 1,56 |
| semantic_segments_second | 0,79 |
| source_mib_hour | 7,60 |
| output_mib_hour | 8,80 |

docs/hour для прогноза включает все обработанные документы, в том числе failed originals. translated_docs_hour приведён отдельно. MB-показатели используют MiB (1 048 576 bytes). Failed originals входят в output bytes/pages.

| Latency | Секунды |
|---|---:|
| mean | 47,80 |
| median | 17,99 |
| p50 | 17,99 |
| p90 | 132,63 |
| p95 | 242,21 |
| p99 | 298,53 |
| max | 299,26 |

Latency: от child start до archive append, для успехов и failures. ZIP extraction непосредственно перед child записана отдельно. Percentiles — линейная интерполяция по 100 значениям.

## Этапы

**Inclusive:** вложенные времена ниже нельзя складывать как независимые.

| Stage | Calls | Seconds |
|---|---:|---:|
| preflight_open_extract | 100 | 3 126,69 |
| archive_extract | 102 | 0,25 |
| ocr_recognize | 120 | 3 098,42 |
| DocumentProfiler | 101 | 0,06 |
| segment_classification | 7460 | 0,37 |
| knowledge_snapshot | 101 | 5,32 |
| glossary_lookup | 24682 | 889,78 |
| translation_memory | 6602 | 14,22 |
| template_routing | 5967 | 262,18 |
| model_translation | 3597 | 497,22 |
| semantic_guards | 3637 | 34,57 |
| document_write | 93 | 177,24 |
| pdf_validation | 93 | 1,80 |
| archive_pack_member | 76 | 0,25 |
| path_translation | 256 | 69,65 |

Архивная упаковка отдельно измерена только для 76 успешных результатов. Копирование 24 failed originals штатным кодом не имеет отдельного timed stage; его время входит в total wall/member latency и остаточную категорию. Ноль в archive event не означает нулевого реального IO.

OCR: **3 098,42 с / 64,77% wall**, 90 pages, 120 regions, 34 documents. Median OCR doc: 59,91 с; p90 212,80 с; p95 227,77 с. Включены штатная загрузка OCR worker/recognition/structure и неуспешные попытки; это не только время собственно распознавания.

M2M100: real loads 35; load/reuse 3282 / 24,70 с; inference 3282 / 429,74 с. Argos loads 58 / 12,06 с. Backend attempt failures 168; devices `{'cuda': 3512, 'cpu': 85}`; backend/device `{'m2m100/cuda': 3281, 'argos/cuda': 231, 'argos/cpu': 84, 'm2m100/cpu': 1}`; fallback attempts 167, segment fallback events 127.

Path translation: 69,65 с, 256 calls, cache hits 0, misses 256, unique cached translations 255, folder components 161. Кеш учитывает контекст и язык; одинаковые слова в разных snapshots могут иметь разные ключи. Повторное использование уже созданного directory_map не считается новым вызовом кеша.

В этом sample первый child start — 1,41 с после preflight; scan 100-PDF ZIP — 0,044 с. Это отдельный малый ZIP, а не повторная проверка startup всего CN7C. Production-хэши всех 248 контролируемых файлов совпали до/после.

## TOP-5 bottlenecks

Ниже времена распределены по фактическим интервалам: вложенный OCR/model/glossary/TM исключается из родительских stages. Один участок wall time учитывается один раз; это помогает сравнить категории без суммирования inclusive parents.

| Категория | Секунды | Wall % | Возможность ускорения при сохранении качества |
|---|---:|---:|---|
| OCR | 3 098,42 | 64,77 | Потенциал есть в lifecycle/повторных загрузках, если они доминируют; требует отдельного измерения без смены моделей/параметров. Не оптимизировано. |
| glossary | 889,78 | 18,60 | Возможен анализ повторных lookup/SQL/cache; терминология и правила должны остаться теми же. |
| model | 497,22 | 10,39 | Можно изучить фактические повторные загрузки и допустимое переиспользование; менять модель/beam/параметры здесь нельзя. |
| writer | 177,24 | 3,71 | Возможен анализ повторных операций шрифтов/страниц; без изменений layout и обязательной validation. |
| other/orchestration | 57,95 | 1,21 | Категория остаточная; сначала нужна детализация, обещать ускорение по одному суммарному числу нельзя. |

Без изменения качества величина реального ускорения ещё не измерена. Для масштаба: условное сокращение OCR на 10% уменьшило бы wall примерно на 6,48%, glossary на 10% — на 1,86%; это расчёт чувствительности, не обещание безопасной оптимизации. Все реальные M2M100/Argos загрузки вместе заняли 34,76 с (0,73% wall): даже теоретическое полное устранение этой работы не решит основную проблему скорости. Writer занимает лишь 3,71%, остаточная категория — 1,21%; главный измеренный резерв находится в OCR и glossary.

## Прогноз 17 211 PDF

| Сценарий | Часы | Сутки непрерывной работы |
|---|---:|---:|
| OPTIMISTIC | 188,23 | 7,84 |
| TYPICAL | 229,51 | 9,56 |
| CONSERVATIVE | 303,93 | 12,66 |

Если workload похож на sample: typical **229,51 ч**, диапазон сценариев **188,23–303,93 ч** (−41,28 / +74,42 ч). Использованы веса N_group/sample_group, реальные document latency и OCR seconds; фиксированная часть sample 3,41 с не размножается 172 раза. Добавлен фактический scan полного источника. Прогноз weighted source pages: 26 841,34; точное количество страниц полного ZIP пока неизвестно.

Проверки по throughput: docs/hour → 228,70 ч; pages/hour → 227,18 ч; source bytes/hour → 240,17 ч. Byte proxy слабее: размер сжатого изображения не определяет число OCR regions. Это не перенос времени первого PDF на весь архив.

OPTIMISTIC: нижний p10 при стратифицированном resampling среднего (2000 повторов, seed=81) либо на 25% меньше OCR workload. TYPICAL: взвешенный средний текущей выборки. CONSERVATIVE: верхний p90 resampling либо +50% OCR workload и до 10 процентных пунктов меньше ранних failures, которые могут требовать полного writer/validation. Разница времени success/failure использована только если она положительна.

Failure rate sample **24,00%** входит в прогноз текущего поведения. Это скорость processing, не гарантия успешного перевода всех PDF. Если failures будут исправлены в будущей задаче, время может вырасти. Сценарный диапазон **не является статистическим confidence interval**: выборка детерминирована, редкие strata представлены 1–2 PDF, corpus pages/regions не подсчитаны. Heat/throttling, конкурирующие процессы, диск и редкий тяжёлый хвост могут расширить диапазон.

## Routing diagnostics и blockers

Model fallback rate 72,99%; Knowledge coverage 59,31%. Warnings 62179. Routing counters: `{'model_attempts': 3596, 'gpu_attempts': 3511, 'cpu_attempts': 85, 'gpu_fallback_events': 85, 'gpu_oom_events': 0, 'processed_segments': 7460, 'semantic_segments': 3799, 'eligible_semantic_segments': 3799, 'model_fallback_segments': 2773, 'knowledge_segments': 2253, 'direct_known_segments': 864, 'unsafe_translation_segments': 195, 'source_preserved_segments': 202, 'composition_segments': 14, 'cross_reference_segments': 5, 'model_segments': 1384, 'model_calls': 3144, 'fallback_events': 127, 'unit_guard_events': 71, 'warnings': 62155, 'negation_guard_events': 110, 'template_segments': 137, 'protected_or_noise_segments': 3661, 'glossary_segments': 2116, 'action_guard_events': 5, 'condition_guard_events': 3, 'object_guard_events': 11}`. Glossary lookup/hit counters: `{'hits': 23901, 'full_segment_hits': 825, 'constraint_hits': 2141, 'fallbacks': 247, 'placeholder_failures': 190, 'derived_fluid_constraints': 0}`. TM counters: `{'exact_hits': 0, 'normalized_hits': 0, 'placeholder_hits': 0, 'fuzzy_hits': 0, 'misses': 14695, 'reused': 0}`. Эти частоты не являются semantic quality score; MAJOR/MINOR/CATA не переоценивались.

Document failure categories `{'VALIDATION': 17, 'UNSUPPORTED_STRUCTURE': 6, 'MODEL_LIMITATION': 1}`; stages `{'validate': 17, 'TRANSLATING': 6, 'WRITING': 1}`; exceptions `{'PdfError': 17, 'IndexError': 6, 'TranslationError': 1}`.

Global fatal: 0; logging `COMPLETE`; observer errors `[]`. Ненулевой FAILED_SOURCE_PRESERVED остаётся ограничением результата полного run: оригиналы будут сохранены, но часть документов не переведётся. Неисправленные причины document failures перечислены в errors.jsonl и production summary. При слишком большом времени следующий шаг — решение пользователя об отдельной performance-задаче, без автоматической оптимизации здесь.

## Evidence и STOP

[Sample manifest — точные 100 PDF](C:/TreeTranslate/qa/aw081/speed_calibration_100/sample_manifest.json) · [Итоги и machine-readable анализ](C:/TreeTranslate/qa/aw081/speed_calibration_100/run_summary.json) · [Execution receipt](C:/TreeTranslate/qa/aw081/speed_calibration_100/execution.json).

В той же папке: stages.jsonl, documents.jsonl (финальные bindings), documents.raw.jsonl (исходные checkpoints), routing.jsonl, errors.jsonl, resource_samples.jsonl, archive_events.jsonl, warnings.jsonl, timing_events.jsonl и index.sqlite3. Original production logs сохранены в logs/<run_id>/.

**STOP.** Полный ZIP не запускался. Production code/Knowledge/NMT/Router policy/UI/OCR architecture/archive recovery не изменялись, после замера не оптимизировались. PHASE B/C, AW0.82, installer, обучение и commit не выполнялись.
