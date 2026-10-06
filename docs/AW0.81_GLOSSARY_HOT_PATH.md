# AW0.81 Glossary Hot Path

**GLOSSARY PERFORMANCE PASS**. Этап №2 завершён. Ровно один основной measured fixed20, run `07e4d3b8a299`; эталон — принятый post-OCR `2681af77e18c`, 726.26 с. Warmup исключён одинаково; sample 5/5/5/5 и MID settings сохранены.

## 1. Root cause

49 словарных DB при compiled-index capacity 8 вызывали повторные открытия, PRAGMA/BEGIN/revision/length queries и повторную нормализацию. До изменений сохранён реальный corpus из 1598 source segments принятого fixed20: 5094 lookup calls с contextual/unsnapshotted/repeat вариантами, 2044 уникальных логических запроса. Это отдельный instrumentation replay; его SQL counts не выдаются за исторические counts всего PDF run. Индексы aliases PK и entries PK уже используются; schema/index changes не понадобились (`query_plan.json`).

## 2. Optimization

Read connections переиспользуются в пределах thread; writable операции остаются отдельными транзакциями, builtins открываются mode=ro. SQLite data_version плюс revision, file identity и connection epoch инвалидируют caches при внешней записи/замене DB/reopen. BEGIN/COMMIT и rollback сохраняют прежние границы. Shutdown и отключение/удаление пакета закрывают handles текущего потока. Нормализация вычисляется по прежнему алгоритму; offsets возвращаются отдельным списком. Её функция не зависит от языка: key содержит raw text, fold и версию Unicode policy; language/domain-dependent retrieval кешируется отдельно.

## 3. Cache/prefetch architecture

Bounded byte LRU хранит immutable raw lexical rows, lengths и empty misses. Namespace включает store/data source/file identity/revision, языковую пару, domain, hash chunk и limit. Final selection cache сохраняет context/snapshot/config/segment/subdomain/facts и добавляет raw request/profile/forms identity. Фильтрация, рейтинг, grammar, placeholders и fallback выполняются прежним кодом. Prefetch использует уникальные уже известные document sources, без выбора терминов и изменения порядка; оригинальные 300-hash SQL chunks/LIMIT оставлены ради exact retrieval order. Forms уже загружены как dict: отдельный morphology cache не добавлен, поскольку CPU profile не показал там существенной стоимости.

## 4. Hardware-aware RAM policy

Reserve max(2 GiB,15% total); lexical ≤256 MiB и min(usable/32,working-set estimate,2×DB bytes); normalization ≤32 MiB/usable÷256; prefetch ≤16 MiB/lexical÷4/usable÷512, source batch ≤256. Это ceilings без предварительного выделения памяти. На этом запуске: lexical 19.61 MiB, normalization 32.00 MiB, prefetch 4.90 MiB, batch 78. Fake 8/16/32/64 GiB и pressure cases проверены; при нехватке headroom caches отключаются и lookup продолжает работать.

## 5. Before → after glossary metrics

| Показатель | До | После |
|---|---:|---:|
| Lookup replay wall, с | 236.54 | 39.15 |
| SQL statements, replay | 1832994 | 279947 |
| SQL queries, replay | 1469498 | 269489 |
| BEGIN, replay | 363479 | 10441 |
| Fetched rows, replay | 326678 | 257992 |
| Entry materializations, replay | 1813 | 1595 |
| Fixed20 glossary, с | 333.15 | 66.89 |
| Fixed20 lookup P50, мс | 29.44 | 6.78 |
| Fixed20 lookup P90, мс | 59.75 | 7.98 |
| Fixed20 wall, с | 726.26 | 451.46 |

Replay connection opens 363478 → 1 относятся только к measured replay после snapshot warmup: 49 builtin handles были открыты до таймера. В реальном fixed20 measured DB opens 0, SQL statements 518120, queries 499935, rows 487232; TM/index SQL исключены. Unique lookup queries 1509; negative calls 3689, repeated misses 3117. Cache/prefetch details и normalization computations/hit/miss/bytes записаны в `lookup_profile.json`; cache totals включают одинаковый warmup. API normalize calls в replay 340111 → 340111; uncached CPU отделён от числа обращений. SQL execute timing измеряет execute без fetch; wall охватывает весь lookup.

## 6. Fixed20 wall before → after

726.26 → **451.46 с**, wall −**37.84%**, glossary −**79.92%**. Targeted3 до/после: 430.57 → 267.28 с, SQL decrease и output/source equivalence PASS. Peak tree RSS 3.72 GiB, private commit 9.25 GiB. OCR model loads: 2 → 2; OCR code/settings/gates не менялись. Stage comparison: model_translation: 213.45 → 206.72 с; template_routing: 92.43 → 21.76 с; knowledge_snapshot: 1.11 → 0.52 с; pdf_write: 43.45 → 42.79 с; pdf_page_layout_write: 14.31 → 13.98 с. Вложенные stage times нельзя суммировать как независимые части wall.

## 7. Equivalence

**PASS**: corpus selected terms/constraints; все 9473 фактических lookup queries контрольного fixed20 проиграны по сохранённому legacy GlossaryEngine после benchmark, включая profile/snapshot signature. Совпали ordered matches и encoded placeholders/forbidden constraints. Дополнительно 2935 raw candidate calls (2299 уникальных) сверены с legacy SQL matcher до выбора термина: полные списки и порядок совпали. Все 20 source contracts (text/bbox/confidence/order/polygon/model), translation candidates, writer statuses/IDs/numbers, normalized PDF fingerprints и четыре rendered first/last probes совпали. 16 TRANSLATED / 4 FAILED_SOURCE_PRESERVED / 0 fatal; failed exact path/bytes, ZIP CRC, source SHA и directory paths PASS. QA observer исключил native archive sample.

## 8. Remaining bottleneck

Остаются обязательные snapshot/context operations, per-call invalidation checks, NMT inference и PDF writer; их processing policy не менялась. Data-version polling сохраняет безопасную видимость внешних правок, поэтому полного устранения SQL нет. Scheduler, model options, OCR и качество перевода относятся к отдельным задачам и здесь не менялись.

## 9. Full pytest

1220 passed / 0 failed / 0 errors / 0 skipped; 286.08 с. Production hashes до/после suite совпали (254 files). Diff ограничен 7 файлами glossary data access/cache и Knowledge wrapper lifecycle/prefetch; content Knowledge/TM/NMT/UI/assets и весь OCR сохранены. Frozen harness/support SHA совпали, test TM пуст, OCR workers завершены. Evidence: `qa/aw081/glossary_hot_path/`.

## 10. Verdict

**GLOSSARY PERFORMANCE PASS**, текущий этап 100%. STOP. Общая AW0.81 и semantic MAJOR ledger не переоценивались. Этап №3, 100/17211 PDF, PHASE B/C и AW0.82 не запускались. Commit не создан.
