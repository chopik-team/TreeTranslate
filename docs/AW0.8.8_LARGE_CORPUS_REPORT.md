# TreeTranslate AW0.8.8 — Large Corpus & Knowledge Scale-Up

## 1. Результат и граница готовности

Большой ZIP проходит scanner READY; база и контрольный эталон созданы. **Полное качество автоматического перевода корпуса не принято.** Новых моделей, обучения весов, установщика, AW0.8.9 и автоматического commit нет. Полный regression: 809 passed.

## 2. Подлинность источника

Пользовательский источник — RAR5, 1,782,746,690 bytes, SHA256 `d0707abd8b2b8564a0c704a5e6b7d6e8971c1c991d09db093976afa016034c98`. Оригинал не менялся до/после конверсии и в финале. Источник USER_PROVIDED, corpus permission CANDIDATES_ONLY; независимые русские цели AUTHORED. Корпус не помещён в assets и не опубликован.

## 3. Инвентаризация

22,836 entries, 17 211 PDF, 3 JSON, 5 622 directories. Unpacked 1,933,957,260 bytes; largest member 8,400,159. Native inventory: 27 732 pages, 17 199 documents with native text; отсутствие native-текста не всегда означает скан.

## 4. RAR → ZIP

Локальная утилита UnRAR читала один stdout-поток; границы членов заданы метаданными, ошибка/CRC обязательны. ZIP_STORED + force ZIP64. Сохранён `C:\Users\PC\Downloads\2022_USER_REPAIR_MAINTENANCE_DISASSEMBLE_(CN7C)_CHINA_koreacustom.ru.zip`. rarfile 4.5 установлен только для developer intake; production RAR не добавлен. Ни одна команда из архива не выполнялась.

## 5. Лимиты большого ZIP

Compressed 4 GiB; unpacked 16 GiB; 100 000 members; 2 GiB/member; ratio 200; path 1024; depth 32. Это ограничения входа. Trusted generated output имеет отдельные bounds 32 GiB / 4 GiB per member, без обхода containment/composition/CRC.

## 6. Защита имён

Сохранены traversal, absolute/drive/UNC, ADS, обратные слеши, reserved devices, trailing spaces/dots, Unicode NFC/casefold duplicates, file/directory conflicts, link/special/reparse, encryption and containment guards. Реальный архив прошёл; небезопасные fixtures отклоняются.

## 7. ZIP64 и CRC

Тест генерирует реальный ZIP64 с локальными заголовками, central directory и ZIP64 EOCD, проверяет CRC; для граничных размеров используются также metadata fixtures. Scanner делает полный CRC-read с checkpoint по членам; выбранные члены вновь читаются при переводе.

## 8. Потоковая обработка

Один открытый input ZIP и output ZIP. По одному документу: extract → штатный DocumentJob → append → удалить исходник и временный перевод. Assets передаются потоком. В RAM остаются метаданные, а не содержимое архива. Нет распаковки всех 16 GiB и повторного открытия central directory на каждый member.

## 9. Дисковый бюджет

Preflight: оценка результата 1.5× input archive bytes + 128 KiB/document + 1 KiB/member, один largest member, rendering max(256 MiB, 2×largest), reserve 512 MiB. Для разных volumes бюджеты раздельны. Это оценка, не жёсткая гарантия роста перевода: ENOSPC остаётся atomic failure.

## 10. Отмена и публикация

Cancel проверяется при metadata/CRC/copy/extract/pack. Финальный архив публикуется только после composition/CRC/source-hash validation. При ошибке/cancel финальный partial ZIP не появляется. Resume внутри архива не реализован: retry начинает архив заново; это явно сохранённая граница цикла.

## 11. Scanner и UX

На настоящем ZIP 17,211 PDF достигли READY за 3.79s; progress (0,0) → (22836,22836). Использован существующий progress panel, без нового компонента/редизайна. Во время исходного hash — indeterminate; затем реальные CRC members. Две новые status/error строки добавлены во все 8 UI catalogs.

## 12. Карта корпуса

Сохранена карта по реальным папкам/нативному тексту. Старая конфигурация дала automotive 14 015 / general 3 196; это не ручная классификация каждого файла. Реальные steering/fuel/emissions/restraint/interior families дали новые cues. Нельзя подменять исходные strata задним числом или считать весь general automotive без доказательств.

## 13. Development / holdout

13,717 development / 3,494 held (20.30%). 6 800 logical groups. Полные документы с одинаковыми PDF SHA или нормализованным текстом сгруппированы до builds; hash/text overlap=0. Native-cache SHA привязан к immutable manifests; development Harvester не принимает held documents.

## 14. Candidate intake

Существующий Knowledge Harvester расширен, второго pipeline/UI нет. 40 561 raw monolingual hypotheses из 13 717 development documents; doc/total/subdomain frequency, segment context, evidence SHA/offset and explainable priority factors. Raw candidates не bilingual assertions; automatic VERIFIED=0.

## 15. Верификация и provenance

Русские targets и полные формы написаны независимо. Developer reviewer=Codex, не human-certified и не OEM-certified. Старые rejected/deprecated revisions сохранены в отдельных reviewer stores. NMT output и OCR suggestions не верифицировались автоматически; неоднозначные cap/left-right wheel/transaxle assertions отложены.

## 16. Рост Knowledge

Entries 494 → 1405: +911, 1401 concept identifiers, 49 aliases. Никакого заполнения квоты до 1500/3000 декартовыми комбинациями. Production DB 2,117,632 bytes.

| Тип entries | После |
|---|---:|
| term | 323 |
| compound | 974 |
| full_segment | 12 |
| phrase | 96 |

## 17. Области Knowledge

Counts пересекаются по scope и не равны числу уникальных слов.

| Scope | Entries |
|---|---:|
| body.body_measurement | 72 |
| body.body_repair | 100 |
| common | 213 |
| body.panels | 24 |
| body.structure | 21 |
| body.doors | 27 |
| suspension | 69 |
| engine | 121 |
| cooling | 70 |
| electrical | 297 |
| diagnostics | 79 |
| transmission | 58 |
| brakes | 54 |
| hvac | 59 |
| steering | 15 |
| body | 9 |
| fuel | 37 |
| emissions | 28 |
| adas | 19 |
| restraint | 39 |
| interior | 51 |

## 18. Concept-first, aliases, polysemy

Одинаковые meaning+context объединены в concept с aliases. Прежние 494 assertions сохранены. Different overlapping targets fail closed/defer; body не получает engine/brakes/HVAC-specific rows без body scope. Две старые engine/body shared assertions легитимно остаются. Неоднозначная 冷却水箱盖 исключена вместо принудительной крышки расширительного бачка.

## 19. Actions и шаблоны

157 → 179 verified templates (+22 evidence-backed patterns). Новые actions/предметы допускаются закрытыми whitelist; negative relation и safety conditions проверяются. Diagnostic labels отдельно от prose; FULL_SEGMENT осталось 12, не главный путь покрытия. Actions/templates лежат в существующих configs, не искусственно прибавлены к entries.

## 20. Grammar forms

236 → 1113 reviewed source forms с полными NOM/GEN/ACC. Позиционные определения привязаны к двери/сиденью/стойке, а не к головному слову облицовка. Исправлены спинка заднего сиденья, преднатяжитель заднего ремня со стороны водителя. 拆下 не создает «нижний»; частичный 下散热器 перед 软管 исключён.

## 21. References, labels, units

Cross-reference classification выделен; closed references связывают два известных объекта. DOT/ID/torque numbers сохраняются. Capacity parser не выдумывает conversion для 美升 и 加仑/夸脱: оставляет исходное число с annotation. Numeric unit-only ranges protected. Unit-map content исключён из UI catalog discovery как перевод документа, не строка интерфейса.

## 22. Выборочная pre-holdout проверка

353 новые surfaces: deterministic random 25/domain или все при меньшем числе, 16 domains. Проверены noun meanings/полные case forms; есть MINOR style issues. До финального holdout удалены unsafe abstract composition, verb-position collision, remote-wheel truncation, cap ambiguity and transaxle ambiguity. Это sampling, не сертификация каждой строки корпуса.

## 23. Native / OCR probe

Native-first весь corpus inventory; OCR ограничен двумя development PDFs через production Auto/region policy. Один EMPTY_PDF, второй low-confidence OCR: structure/GPU route и load/inference metadata сохранены; network attempts=0. Распознанный ненадёжный текст не обучал Knowledge. Нет заявления, что все сканы корпуса теперь читаются.

## 24. Holdout: методика

18 целых коротких held PDFs / 157 native text lines заморожены до build. Первоначальная line-engine диагностика сохранена отдельно: она не воспроизводила numbered PDF normalization. Корректное сравнение before_production/after_production использует штатный PDF translation helper и исходную domain profile. Baseline реконструирован из prebuild 494-pack/config snapshots; код PDF/units текущий. Отдельно проведён реальный writer-run, результаты нельзя смешивать со строковыми оценками.

## 25. Holdout: покрытие и смысл

В production-normalized line benchmark bare model 95 → 75, glossary 49 → 60, template 1 → 10, protected 12 → 12. После: {'MAJOR': 77, 'MINOR': 40, 'PASS': 38, 'CATASTROPHIC': 2}. Две CATASTROPHIC — старое «снять ремень → отрезать», new CATA=0. Это не успешный semantic gate. Ошибки final holdout не использованы для дообучения. Duplicate held documents присутствуют в representative set; это не 18 независимых уникальных text groups.

## 26. Эталон и реальные PDF

Авторский PDF-эталон: 18 pages; TSV содержит все 157 source/reference/output/grade. Gold никогда не импортируется в production/TM. Production writer сохранил 16/18 PDFs. Два blockers: нечитабельная native схема и discontiguous preserved table labels. Первоначальный ZIP18 был корректно отклонён без финального partial output. Native bullet ↔ middle-dot visual equivalence исправлена; другие символы не ослаблены.

Пакет: `C:\TreeTranslate\output\aw088\comparison\CN7C_эталон_и_тесты.zip`.

## 27. Старые holdout regressions

AW085/AW086 40: {'PASS': 32, 'MINOR': 5, 'MAJOR': 3}, все outputs неизменны от AW087. AW087 120: {'PASS': 104, 'MINOR': 9, 'MAJOR': 7}; одно улучшение imperative водяного насоса. Profiler 8/8. Ошибка pretensioner старого prose-06 не обучалась по held source. Все frozen references SHA сохранены.

## 28. Body regression

22 → 22 pages, 419/419 protected values, 10/10 reviewed instructions PASS, 0 OCR continuation. Геометрия/изображения сохранены, canonical published concepts 117/131. Wall 185.49s получен при параллельных тяжёлых QA jobs: не сравнивать как чистый speed benchmark и не включать в ETA calibration.

## 29. Coolant regression

4 → 5 pages; bare fallback осталось 5. Полная semantic review: {'PASS': 79, 'MAJOR': 9, 'MINOR': 6, 'EXCLUDED_OCR_NOISE': 14} → {'PASS': 78, 'MAJOR': 7, 'MINOR': 9, 'EXCLUDED_OCR_NOISE': 14}. Две source-unit MAJOR стали MINOR с ambiguity annotation; один старый запрет ITM получил MINOR из-за русского падежа. CATA=0. Это небольшая грамматическая регрессия, не замалчиваемая как «не ухудшилось». Whole-file perfection не достигнута.

## 30. Snapshots и scale

314 development snapshots; max entries 1068, body 419, forbidden specific terms=0. Actual production SQL benchmark [(1405, 283, 14.89), (5000, 283, 14.48), (10000, 283, 15.65), (25000, 283, 15.84)] (total, active, ms). Inactive synthetic scale rows не затронули source pack; это benchmark индекса, не NMT throughput и не реальная база 25k approved terms.

## 31. Тесты, visual QA и времена

809 passed, regression.xml. Новые archive/Knowledge/PDF tests; строгие CRC/layout validators не отключены. Rendered все 24 machine PDFs + 18-page gold; просмотрены contact sheets и gold pages. Видимы intentionally preserved Chinese и continuation pages; это quality limitations, не пустые страницы без причины. Timings содержит run/stage/process. Concurrent QA wall times не подходят для калибровки ETA. Старый historical test исправлен: frozen AW087 reference проверяется по своему SHA, а не требует вечного совпадения нового production DB.

## 32. Ограничения и завершение цикла

Не готово: безошибочный сплошной перевод длинной prose/conditions, две формы PDF, полное OCR corpus coverage, archive resume, human/OEM certification. База заметно расширена, локальный эталон и набор для прогона готовы. AW0.8.8 implementation проверена; semantic acceptance всего корпуса НЕ пройдена. AW0.8.9 и новые модели не начаты. Старые cleanup файлы не удалялись; transient failed scale DB не является runtime dependency. Commit не сделан.
