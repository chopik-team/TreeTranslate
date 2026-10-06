# TreeTranslate AW0.8.7 — Technical Knowledge Harvester & Procedure Language

Дата: 02.10.2026. Проект: C:\TreeTranslate.

## 1. Исходная база

AW0.8.6: 301 ZH→RU automotive entries, M2M100 418M/Argos/PaddleOCR, TM/Glossary и Contextual Router. Body: 22 страницы, 419/419 protected. Coolant: исторический счётчик 37 model fallback, девять template hits, 4→5 страниц. Новый NMT backend не создавался.

## 2. Зачем расширять Knowledge

Контекстный поиск уже ограничивает область словаря. Полезнее добавлять короткие понятия и структуры действий, чем сохранять целые руководства. Процедура связывает действие, объект и падеж; неизвестный свободный текст остаётся модели. Coverage и semantic quality оцениваются отдельно.

## 3. Архитектура Harvester

Переиспользованы tools/knowledge_harvester: Store/SQLite, provenance/digest, normalization, candidate/alias/conflict/review tables и существующий app.glossary.packs.build_pack. Новый corpus.py — document adapter внутри того же инструмента, не второй engine. Additive corpus_documents/document_evidence не меняют пользовательский Schema 1. Существующий source ingest/link/build workflow сохранён; corpus workflow использует отдельную dev DB.

## 4. Corpus intake

CLI: `python -m tools.knowledge_harvester.cli --db qa/corpora/incoming/harvest.db corpus-intake PATH --corpus-id ID --language zh --origin USER_PROVIDED --permission REVIEW_REQUIRED`. Поддерживаются PDF, DOCX, ZIP и папки; TXT/TSV также доступны для authored inputs. Сохранены ID, path/member, language, domain/subdomains, type, SHA256 контейнера и члена, permission, timestamp/version. ZIP проходит существующие path/CRC/size checks; чтение последовательное, source SHA проверяется после обработки. В проверочном inventory восемь документов. Native intake не выполняет дополнительный OCR: это явное ограничение; OCR evidence текущего production capture можно передать через candidate API. Original user files не копируются в assets.

## 5. Provenance и права

AUTHORED, USER_PROVIDED, EXISTING_PROJECT_FIXTURE, LICENSED_OPEN_SOURCE, MODEL_SUGGESTED и DERIVED_FROM_EXISTING_KNOWLEDGE доступны как типы происхождения. Новый pack состоит из коротких авторских концептов; review выполнен Codex, не независимым человеком. Сырые модели и copyrighted paragraphs не объявлены VERIFIED. Official pack adapter допускает только review с неизменным digest и разрешением AUTHORED_FOR_PROJECT/APPROVED_FOR_REDISTRIBUTION. Permission REVIEW_REQUIRED/CANDIDATES_ONLY не разрешает redistribution.

## 6. Candidate pipeline

Intake → normalized candidates → exact/declared-alias dedup → context conflict detection → REVIEWED → VERIFIED/REJECTED/AMBIGUOUS/DEPRECATED. Повторный corpus id/hash не плодит записи. Изменение evidence инвалидирует verification. TERM/COMPOUND/PHRASE/TEMPLATE/ABBREVIATION извлекаются из коротких текстов и действий; ALIAS/FULL_SEGMENT/CONCEPT_RELATION поддержаны в candidate API и review, но не обещают автоматический discovery всех видов. `corpus-export` экспортирует JSONL, `corpus-review` принимает explicit review, `corpus-build-pack` адаптирует только eligible records к существующему writer. Model output не может автоматически стать VERIFIED.

## 7. DB BEFORE

301 записей; 479,232 bytes. Types: {"term": 133, "compound": 121, "full_segment": 12, "phrase": 35}. SHA256: `73ac69302a29f7f0358dc398fcf659288291a47500466f0cb7403f2d55a9d072`. Снимок сохранён до расширения.

## 8. DB AFTER

494 записей (**+193**, без искусственного потолка); 753,664 bytes. Types: {"term": 199, "compound": 248, "full_segment": 12, "phrase": 35}. Concepts: 491; aliases: 22; review states: {"VERIFIED": 494}. FULL_SEGMENT остались 12: снижение fallback не получено копированием длинных предложений. SHA256: `835993c6136b80db1fbc006a712611d96283d9287dfe18522d28347f2e7284a3`.

## 9. Домены и поддомены

| Subdomain | Entries (multi-label) |
|---|---:|
| body.body_measurement | 72 |
| body.body_repair | 100 |
| body.doors | 27 |
| body.panels | 24 |
| body.structure | 21 |
| brakes | 17 |
| common | 72 |
| cooling | 56 |
| diagnostics | 26 |
| electrical | 30 |
| engine | 41 |
| hvac | 12 |
| suspension | 37 |
| transmission | 16 |

Содержательно расширены cooling/engine/electrical/diagnostics, transmission/brakes/HVAC, suspension, body repair/measurement и common. Другие языки поддержаны intake metadata; массовое новое multilingual покрытие не обещано.

## 10. Действия и семантические отношения

24 action records: ADJUST, ALIGN, AVOID, CHECK, CLEAN, CONNECT, DISCONNECT, DO_NOT, DRAIN, ENSURE, FILL, IDLE, INSPECT, INSTALL, LOOSEN, MEASURE, REMOVE, REMOVE_AIR, REPLACE, START, STOP, TIGHTEN, VERIFY, WAIT. Они связываются с template action IDs; не применяются как глобальная подстановка глаголов. Шесть лёгких reviewed relations IS_A/PART_OF/RELATED_TO/ACTION_ON/USED_WITH сохранены в существующей SQLite relations для review; graph database не добавлена. Нет нового универсального morphology engine.

## 11. Шаблоны

157 VERIFIED bounded templates, включая прежние восемь; разные imperative/heading и punctuation варианты считаются отдельными rules. Literal structure, максимум 512 characters/3 slots по 128, explicit whitelist и known forms. Unknown/ambiguous slot, чужой context, protected mismatch и неизвестный хвост дают NMT. Полное exact TM/User Glossary и известный compound сохраняют приоритет. Максимум три complete sentence templates могут быть соединены только если каждая часть подтверждена; partial composition не публикуется. General technical templates переиспользуют forms без domain-specific runtime code; отдельный тест подтвердил industrial «Затяните болт» через добавление только данных.

## 12. Русские формы и negation

236 explicit slot-form records: base/nominative, accusative, genitive; instrumental/prepositional только для нужных конструкций. «Снимите крышку радиатора», «Установите узел вентилятора охлаждения», «Долейте охлаждающую жидкость» проходят реальные template paths. negative_relation — консервативный счётчик отрицательных смысловых маркеров для curated structures, не универсальная логическая модель. Signed slots/known clauses не допускают произвольный отрицательный текст. Guards усилены распознаванием ASCII identifiers и чисел на границе китайской письменности: GDS/VIN и 20分钟 сохраняются, исчезновение/замена отклоняются.

## 13. Аудит исторических 37 fallback

В AW0.8.6 сохранён aggregate counter 37, но нет source-level route trace. Проведена явная реконструкция с исходными 301 rows и legacy templates: 39 raw records; два дополнительных idle вызова объясняются новым warning-region typing. Raw39 сохранены, а список без этих двух содержит 37 записей с source/type/context/reason/concepts/pattern/model-required. Это реконструкция, не выданные за исторические логи. Counter includes filename. Модель с glossary constraints также делает запрос к router; поэтому bare fallback и model router calls не смешиваются.

## 14. Coolant BEFORE→AFTER

| Metric | AW0.8.6 | AW0.8.7 |
|---|---:|---:|
| Bare model fallback | 37 | 5 |
| Template hits | 9 | 64 |
| Pages | 5 | 5 |
| Job seconds | 67.82 | 50.01 |

Model router calls: reconstructed baseline 99 → 15; это requests к router, не измерение translator.translate_batch и не число cache misses. Семь критических term checks сохранили все occurrences. Заголовок исправлен, imperative/connector/GDS/ITM/fill/drain/negation/pressure warning стабилизированы. Native продолжения сохранены, четыре страницы искусственно не навязывались. Source SHA неизменен.

## 15. Полный semantic review coolant

| Grade | BEFORE | AFTER |
|---|---:|---:|
| PASS | 25 | 79 |
| MINOR | 6 | 6 |
| MAJOR | 63 | 9 |
| CATASTROPHIC | 0 | 0 |
| EXCLUDED_OCR_NOISE | 14 | 14 |

Просмотрен каждый опубликованный semantic block. Остаются девять MAJOR: четыре повреждённые cross-references, три неоднозначные diagnostic labels и две строки объёма с ненадёжным переводом imperial units. Все числа сохранены, но это не доказывает смысл единиц. Шесть MINOR отмечают неоднозначные исходные формулировки концентрации. 14 «目» исключены как preserved OCR noise. Это review Codex, не полная OEM/человеческая сертификация; ещё нельзя считать руководство безошибочным.

## 16. Body regression

22→22 страницы; 419/419 protected; 130/131 concepts до placement, 117/131 published; strict 110/100, как раньше. Knowledge availability 133/133, 232 protected. OCR continuations/noise overlays = 0/0; 16 китайских placement-preserved блоков и семь noise elements остаются по прежней политике. Все десять instruction references PASS; ZIP CRC и source SHA проверены. Все 22 страницы и пять страниц coolant отрендерены PDFium и просмотрены; глобальный writer/layout не менялся.

## 17. Новый holdout и freeze

| Grade | Count |
|---|---:|
| PASS | 103 |
| MINOR | 10 |
| MAJOR | 7 |
| CATASTROPHIC | 0 |

120 authored examples, восемь областей, новые комбинации action/object и 16 свободных prose cases. Синтетический набор проверяет композицию, не заменяет unseen user/OEM documents. References заморожены до evaluation и не переписаны. После freeze исправлены только targets двух старых drain templates по уже известному coolant development corpus («вода»→«жидкость»). Это прозрачное изменение knowledge revision после freeze: исходный template JSON/hash, correction ledger и предыдущие outputs сохранены. Повторная оценка дала все 120 outputs неизменными. Никаких новых entries/patterns по failed holdout не добавлено. В некоторых prose references есть неверное родовое согласование; errata указана отдельно, исходный файл сохранён.

## 18. Старый holdout, конфликты и неоднозначность

Frozen40 AW0.8.6 → AW0.8.7: PASS 33→32, MINOR 5→5, MAJOR 2→3, CATA 0→0. Есть реальная регрессия: «преднатяжитель ремня» стал «защитные пояса»; запрет повреждения сохранён. Она не исправлена добавлением knowledge по holdout. На новом наборе семь MAJOR связаны с неверным объектом в свободной условной фразе; условия остановки сохранены. Profiler frozen holdout 8/8. Context-specific 排气 cooling/engine не схлопываются; strongest context разрешает sense, равные конкурирующие смыслы отклоняются. Existing synonym/alias duplicates объединяются, conflicting existing stable-rod target сохранён, новая альтернатива отложена.

## 19. Scale benchmark

| DB rows | Active snapshot | Median snapshot, ms | Candidate lookup, µs |
|---:|---:|---:|---:|
| 1000 | 128 | 9.32 | 15.69 |
| 5000 | 128 | 9.62 | 15.41 |
| 10000 | 128 | 10.32 | 15.64 |
| 25000 | 128 | 10.73 | 16.21 |

Synthetic inactive metadata, actual production SQL/candidates, seven cold snapshot trials. UNION по доменам использует полный context_selection index; EXPLAIN подтверждает SEARCH, не metadata full scan. Active snapshot постоянный; исследование не доказывает постоянное время для 25k одновременно релевантных concepts. Сохраняются bounds 2048 active entries/12 snapshots и существующий indexed fallback. Scale rows не попали в production pack.

## 20. Время и размер

| Corpus | Wall, s | Profile, s | Snapshot, s | Lookup, s | Templates, s |
|---|---:|---:|---:|---:|---:|
| body | 62.59 | 0.0039 | 0.4175 | 14.67 | 0.009 |
| coolant | 50.01 | 0.0015 | 0.0438 | 14.58 | 0.467 |

Pack 479,232→753,664 bytes. Lookup включает legacy/user SQLite, не только новый overhead. Counters включают names и попытки direct lookup; не складываются механически в segment count. Это измерения одной машины/итоговых runs, не статистическое обещание скорости. process timings/source type/profile/snapshot/lookup/template/model route counters сохранены отдельно. Runtime logs не содержат developer history или raw source/target.

## 21. Очистка

Automatic approval review отклонила обе точечные операции: old build/aw085-quality (38 files/9,769,822 bytes) и confirmed build/aw087-scale (4 files/31,068,160 bytes): `blocked by policy`. Инвентарь сохранён, deleted=false. Обходов/повторных попыток нет. Corpora/gold/holdout/reports/accepted outputs/production DB/models/licenses не удалялись. Административная очистка остаётся открытой.

## 22. Regression и контракты

Full pytest: **770 passed**, 236.31 s, failures/errors=0. Harvester tests: extraction/idempotence/SHA/review/digest/model prohibition/permissions/alias/conflicts/languages/unsafe ZIP. Procedure tests: imperative/heading/grammar/unknown/negation/composition/protected IDs/numbers/industrial reuse. Existing TM/User Glossary priority, source immutability, PDF/OCR policy, ZIP/cancel/pause/resume/atomic publication/offline/localization/naming не ослаблялись. Language Support обновил только actual counters; stars/history и UI version/installer не переработаны. Коммитов нет.

Один промежуточный полный прогон дал 769 passed/1 failed: существующий Qt animation test не увидел кадр в фиксированном таймерном окне. Isolated оба animation tests прошли; финальный полный прогон прошёл без изменений UI или ослабления теста. Исходный failed XML сохранён как regression_timer_failure.xml.

## 23. Ограничения и завершение

Функциональный цикл AW0.8.7 реализован. Ограничения: review не независимый; native-only intake; heuristic candidate extraction и negation counter; фиксированные safe forms; synthetic holdout и reference errata; семь MAJOR на новом holdout; регрессия одного старого unseen warning; девять MAJOR блоков coolant; консервативные китайские подписи body; незавершённая policy-blocked cleanup. No blanket quality guarantee. Никаких новых UI controls, NMT backend, cloud, vectors/embeddings, fine-tuning, installer или stars recalculation. После доставки цикл остановлен; новые пользовательские файлы идут отдельным corpus с baseline ДО расширения данных и untouched документами для holdout.

## Артефакты

- [Индекс QA](../qa/aw087/FINAL_RESULTS.md)
- [ZIP](../output/aw087/accepted/Размеры кузова_ru.zip)
- [PDF](../output/aw087/accepted/Охлаждение_ru.pdf)
