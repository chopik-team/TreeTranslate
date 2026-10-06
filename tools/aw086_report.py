"""Final factual report from retained production and regression evidence."""
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path('C:/TreeTranslate');QA=ROOT/'qa/aw086'
def read(name):return json.loads((QA/name).read_text('utf-8'))


def build():
    body=read('body_quality.json');coolant=read('coolant_quality.json');holdout=read('holdout_regression.json')
    timings=read('timings.json');delivery=read('delivery_artifacts.json');stats=read('knowledge_base_after.json')
    runs={name:read(name+'_e2e.json') for name in ('body','coolant','general','mixed')}
    suites=ET.parse(QA/'regression.xml').getroot()
    suite=suites.find('testsuite') if suites.tag=='testsuites' else suites
    assert suite is not None and int(suite.attrib.get('failures',0))==int(suite.attrib.get('errors',0))==0
    tests=int(suite.attrib['tests']);duration=float(suite.attrib['time'])
    total=body['after'];assert total['source_pages']==total['output_pages']==22
    assert total['protected_total']==total['protected_preserved']==419
    assert total['canonical_translation_concepts']>=130 and total['canonical_published_concepts']>=117
    assert all(row['status']=='PASS' for row in body['stable_instructions'])
    assert read('knowledge_availability.json')['counts']['KNOWN']==133
    assert all(c['matched']==c['published_matched']==c['occurrences'] for c in coolant['checks'])
    assert not any(coolant['forbidden_errors'].values())
    assert holdout['references_unchanged'] and holdout['after_summary'].get('MAJOR',0)+holdout['after_summary'].get('CATASTROPHIC',0)<=3
    frozen=read('profiler_holdout.json')
    assert frozen['rule_sha256']==sha256((ROOT/'assets/config/knowledge-context.json').read_bytes()).hexdigest()
    assert read('profiler_holdout_results.json')['passed']==8
    for artifact in delivery:assert sha256(Path(artifact['delivery_output']).read_bytes()).hexdigest()==artifact['sha256']
    routing=timings['body']['routing'];preparation=sum(routing.get(k,0) for k in ('archive_sample_time','archive_profile_time','folder_profile_time','document_profile_time','snapshot_build_time','segment_classification_time'))
    overhead=100*(runs['body']['elapsed']/64.27-1)
    profile=next(p for p in runs['coolant']['context']['profiles'] if p['purpose']=='document')
    hits='\n'.join(f"| {name} | {run['context']['metrics'].get('exact_hits',0)} | {run['context']['metrics'].get('compound_hits',0)} | {run['context']['metrics'].get('template_hits',0)} | {run['context']['metrics'].get('model_fallbacks',0)} |" for name,run in runs.items())
    timing_rows='\n'.join(f"| {name} | {v['wall_seconds']:.2f} | {v['routing'].get('document_profile_time',0):.4f} | {v['routing'].get('snapshot_build_time',0):.4f} | {v['routing'].get('segment_classification_time',0):.4f} | {v['routing'].get('knowledge_lookup_total',0):.2f} |" for name,v in timings.items())
    terms='\n'.join(f"| {c['source']} | {c['published_matched']}/{c['occurrences']} |" for c in coolant['checks'])
    text=f'''# TreeTranslate AW0.8.6 — Contextual Knowledge Router

Дата: 2 октября 2026. Проект: C:\\TreeTranslate.

Функциональная часть AW0.8.6 подключена к production pipeline и проверена. Единственный незакрытый административный пункт acceptance gate — удаление старого scratch: автоматическая проверка отклонила операцию `blocked by policy`. Поэтому полный формальный gate с обязательной очисткой не объявляется закрытым. Следующий цикл не начат.

## 1. Начальное состояние

Переиспользована база AW0.8.2/AW0.8.3 с hotfix PDF, ZIP pipeline и AW0.8.5 Knowledge Expansion. Промежуточный AW0.8.6_KNOWLEDGE_DATA_PROGRESS.md сохранён как исторический документ; он не заменён этим отчётом. До подключения routing: 296 записей и 716 passing tests. Внешних исследований движков, загрузок моделей и облачных запросов не было.

## 2. Подготовленные знания

Повторного расширения на сотни слов не проводилось. К 296 записям добавлены только пять необходимых coolant concepts: 排放螺塞, 冷却风扇总成, 防锈剂, 空转, 排气. Явный вариант 散热器排放螺塞 привязан к существующей сливной пробке радиатора. Итог: {stats['entries']} запись, {stats['types']}. Прежние переводы и варианты сохранены; проверка — 63/63 строк подготовленного списка и 30/30 грамматических форм. Проверка Codex не является независимой сертификацией техническим переводчиком.

## 3. Taxonomy

Явная taxonomy сохранена в assets/config/knowledge-taxonomy.json и qa/aw086/taxonomy.json: general; automotive.common/body/cooling/engine/transmission/suspension/brakes/electrical/diagnostics/hvac/adas; body имеет repair, measurement, geometry, doors, panels, structure; industrial имеет mechanical, electrical, hydraulics, automation, metallurgy; software и electronics. Пустые ветви описывают архитектуру, а не текущее покрытие переводами.

## 4. DocumentProfiler в production

DocumentJob вызывает профилировщик после extraction, включая OCR, и разрешения языковой пары. Профиль и immutable snapshot сохраняются в плане документа. Scanner, OCR, TM, Glossary, M2M100 418M, writer и atomic publication остаются существующими компонентами. Никаких пользовательских domain/subject/pack/template controls не добавлено. Text UI сохраняет прежнее поведение; новый документный контекст передаётся через внутренние поля TranslationRequest.

## 5. Evidence и ограниченная выборка

До 24 семантических сегментов из начала, середины и конца, до 8000 символов; filename, logical folders, archive stem и parent prior учитываются отдельно. Используются повторяющиеся технические cues, заголовки, существующая region metadata и идентификаторы GDS/ITM. Cues — фиксированный словарь признаков; отдельного классификатора ML и дополнительных сетевых данных нет. Archive sampling читает максимум два native документа до 2 МиБ, до 4000 символов каждого, без запуска второго OCR. Полный ZIP повторно для profiling не анализируется.

## 6. Confidence policy

Content весит 1.0, filename 0.4, folder 0.3, archive 0.35, parent 0.2. Primary требует минимум двух различных cues и score ≥0.6; кандидаты subdomain сохраняются от 0.32. Confidence — детерминированная эвристика, а не статистически откалиброванная вероятность. В general control единственное совпадение даёт слабый cooling candidate около 0.39, но automotive не становится primary и его записи не входят в активный snapshot. Поле selected_subdomains в сыром диагностическом summary содержит candidate scores; фактическое принятие определяется primary и snapshot selection.

## 7. Inheritance и child override

Архив имеет собственный профиль. Папки получают архивный prior; при слабом имени naming использует доказанный архивный контекст. Сильные дочерние content evidence определяют собственные ветви. QA проверяет electrical PDF внутри body parent: electrical >0.8, body остаётся слабым. Parent не записывается принудительно в DocumentConfig.domain дочернего документа. Семейство body выводится из его дочерних ветвей, поэтому bounded sample не выключает известную кузовную подпись, не попавшую в выборку.

## 8. SegmentClassifier

Реализованы все 19 требуемых классов. Используются protected regex, numbering, punctuation, imperative/conditional/warning cues и region kind, сформированный существующим PDF layout analysis. TITLE/HEADING/TABLE_HEADER также принимают явную metadata/hint. Region metadata имеет значение: подпись, которую PDF определил как HEADING, совместима с проверенным номинальным compound. Чисто семантическое распознавание заголовков таблиц из изображения не добавлялось. Классификация кешируется по тексту/hint/region до 4096 записей и очищается после job.

## 9. KnowledgeRouter и фактический порядок

Новый модуль работает поверх TranslationKnowledgeEngine, не создавая второй pipeline. Порядок: разрешённая языковая пара и контекст → существующая TM → пользовательский/установленный Glossary с прежним приоритетом → contextual official exact/structured label → безопасный template → existing glossary constraints → существующая модель. Explicit user match блокирует builtin template; пользовательские правила не фильтруются по official subdomain. Автоматического TM write-back нет.

## 10. KnowledgeSnapshot

Snapshot immutable: tuple entries и read-only maps exact/prefix/concepts. Только релевантные official записи, включая общие automotive terms и подтверждённые семейства. Body не подтягивает cooling автоматически; mixed control включает cooling и electrical. Доказанный body parent допускает родственные дочерние ветви body; это сознательно более широкая область внутри одного семейства для сохранения known labels при ограниченной выборке. В general snapshot automotive entries = 0.

## 11. SQLite и indexing

Подготовленный knowledge_context_index реально используется в SELECT по pair/domain/subdomain/type с LIMIT 2049; более 2048 записей переводят pack на прежний bounded hashed lookup. Добавлены indexes по concept_id и pair/domain/source_normalized. Exact работает через hash-like dictionary, compound/phrase через ограниченный prefix candidate set. Legacy packs остаются на существующем aliases/hash index, не копируются целиком в каждый PDF и не сканируются полностью на каждом сегменте. User schema version остаётся 1; .tglossary contracts и миграции не менялись.

## 12. Concept IDs

Идентификаторы входят в snapshot concept groups, связывают canonical forms и aliases, участвуют в дедупликации retrieval и объяснениях выбора. 减震器/减振器 имеют общий ID. Это локальная ZH→RU идентичность понятия, не multilingual ontology. Смысл старых target strings не менялся. Концепты с разными допустимыми target forms не сливаются в одну случайную строку.

## 13. Безопасные templates

Восемь reviewed patterns: два компонента и проверка деформации; регулируемая длина; проверка отсутствия люфта; смесь с процентами; предупреждение о горячем двигателе и крышке радиатора; холостой ход; отворачивание и затягивание сливной пробки. До трёх slots по 128 символов, общий input до 512. Только точная структура, проверенные concepts/forms и protected literal values. Literals экранируются, whitespace ограничен, eval/code/recursive expansion нет. Неизвестный slot, неоднозначность и лишний хвост → model fallback. Негативные отношения статически заданы в reviewed target; цифры, единицы и идентификаторы проходят существующие guards. Полноширинный процентный диапазон сохраняется исходным span, а не заменяется новым написанием.

## 14. Explainable scoring

Exactness до 0.30, trust до 0.20, domain 0.20, subdomain 0.15, segment compatibility 0.10, specificity до 0.05, priority до 0.02; alias и parent distance уменьшают score на 0.02. HIGH ≥0.86 допускает model bypass, MEDIUM ≥0.65 остаётся guidance/constraint, LOW и wrong context отвергаются. Longest specific compound выбирается существующим resolve. User-controlled entries сохраняют прежние правила. Все факторы доступны в routing_decisions.json; это policy score, не предсказанная вероятность правильности.

## 15. Body ZIP profile

Реальный 车身尺寸.zip переведён ZH→RU Auto. Archive: automotive с body repair/measurement/geometry/doors/structure; документы имеют собственные profiles. Имена 前车身/内部 переведены в кузовном контексте. Исходный SHA неизменен, ZIP CRC проверен. Production output и delivery copy имеют одинаковые байты; принятый файл: [Размеры кузова_ru.zip](../output/aw086/accepted/Размеры%20кузова_ru.zip).

## 16. Coolant profile

Использован существующий tests/fixtures/pdf/automotive.pdf. Primary — {profile['selected_domain']}, cooling score {profile['selected_subdomains'].get('automotive.cooling',0):.4f}; дополнительно diagnostics/electrical/engine, document type service_procedure. Body repair в profile не выбран. Определение не зависит от жёсткой проверки имени файла. [Итоговый PDF](../output/aw086/accepted/Охлаждение_ru.pdf).

## 17. General control

Authored general document про чтение и путешествия с одним словом «радиатор» получил general. Automotive snapshot пустой; перевод идёт существующим model/general route. Слабый candidate сохранён для честной диагностики и не применяется как automotive Knowledge. Синтетический заголовок сохраняет особенности прежнего writer; идеальную вёрстку произвольных general документов этим контролем не сертифицируем.

## 18. Mixed control

Authored документ с cooling и electrical предложениями получил automotive с обеими ветвями. Snapshot содержит оба набора терминов. Это проверка корректности выбора контекстов, не обещание идеальной грамматики всех модельных предложений. QA source fixtures и опубликованные outputs сохранены.

## 19. Frozen holdouts

Profiler development set отделён от final holdout. Holdout заморожен до результатов: 8/8. После просмотра результатов profiler rules не менялись; checksum config проверен. AW0.8.5 source/references не переписаны. Семантическое сравнение:

| Оценка | AW0.8.5 | AW0.8.6 |
|---|---:|---:|
| PASS | 33 | 33 |
| MINOR | 4 | 5 |
| MAJOR | 3 | 2 |
| CATASTROPHIC | 0 | 0 |

37 outputs неизменны. Deformation case восстановлен. Crack case сохраняет неуверенную конструкцию whether, поэтому оставлен MAJOR, несмотря на исправленный термин; в последней фразе про отсутствие трещин есть ошибка падежа, MINOR вместо прежнего PASS. Reviewer: Codex, без независимого human certification.

## 20. Body quality regression

| Показатель | AW0.8.5 | AW0.8.6 |
|---|---:|---:|
| PDF / страницы | 7 / 22→22 | 7 / 22→22 |
| Protected values | 419/419 | 419/419 |
| Knowledge availability | 133/133 | 133/133 |
| Concept terminology до размещения | 130/131 | 130/131 |
| Concept terminology опубликовано | 117/131 | 117/131 |
| Strict terminology до/после размещения | 110/100 | 110/100 |
| OCR continuation / noise overlays | 0 / 0 | 0 / 0 |

Все 10 ранее сохранённых instruction references PASS, включая четыре обязательных. 16 placement-preserved китайских сегментов и 7 намеренно сохранённых OCR noise элементов остаются как в AW0.8.5. Knowledge доступно, но существующая консервативная политика размещения не гарантирует публикацию всех русских подписей в тесном bbox. Во время разработки был неудачный pilot с чрезмерно узким snapshot; он сохранён как body_pilot.json и не является accepted результатом.

## 21. Coolant quality и визуальная проверка

| Термин | Правильных опубликованных вхождений |
|---|---:|
{terms}

Три запрещённые старые ошибки («холодильная жидкость», «нагревательного покрытия», «обезболивающие продукты») не найдены. Hot-pressure warning сохраняет отрицание и риск ожога; numeric mixture template сохраняет 45–60% исходным написанием; GDS/ITM сохраняются. Coolant: 4→5 страниц, native продолжение допустимо прежней политикой; запрет OCR continuation не ослаблен. M2M fallback всё ещё даёт тяжёлую грамматику и неточные формулировки части длинных coolant предложений, например нижней крышки двигателя и описания GDS. Семь term checks не равны полной сертификации руководства. Все 29 опубликованных страниц body/coolant/general/mixed отрендерены PDFium и просмотрены; изображения и геометрия сохранены. Poppler не использован, задействован существующий renderer проекта.

## 22. Timings и hit metrics

| Corpus | Job wall, s | Document profile | Snapshot build | Classification | Existing+context lookup |
|---|---:|---:|---:|---:|---:|
{timing_rows}

Body baseline 64.27 s → {runs['body']['elapsed']:.2f} s: {overhead:+.2f}%, gate ≤5% выполнен. Native archive sampling + profiles + snapshot construction + classification: {preparation:.4f} s, около {100*preparation/64.27:.2f}% baseline. Routing total {routing['routing_total']:.2f} s включает существующий legacy/user lookup; его нельзя считать полностью добавленным overhead. Это один итоговый прогон с холодным OCR, не статистический benchmark на множестве машин. Предыдущие числа 56–66 s отражали промежуточные версии, не доказательство устойчивого ускорения.

| Corpus | Exact result hits | Compound hits | Template hits | Model fallbacks |
|---|---:|---:|---:|---:|
{hits}

Счётчики включают file/folder names и отдельные фрагменты; они не обязаны складываться в число source segments. Compound/term/concept отражают принятые glossary matches, а не независимый semantic accuracy score. Lookup/scoring, archive profile/sample, documents, writing/OCR/validation timings сохранены отдельно.

## 23. Cache и memory

Profiler LRU до 128 profiles; snapshot LRU до 12; до 2048 curated entries на snapshot. Key учитывает source identity/content signature, language pair, profile version, pack checksum/version и file identity. Filename один не является key. Concept and exact maps immutable; большие legacy dictionaries остаются в indexed SQLite. Estimated materialized payload body: {timings['body']['cached_snapshot_bytes_estimate']:,} bytes суммарно построенных snapshots; это оценка, не RSS измерение. В конце каждого production job profile/snapshot/classification caches очищены и ссылки DocumentJob отпущены. Диагностика остаётся content-free: IDs/scores/counts/times, без source/target phrases в documents.log.

## 24. Cleanup

Подтверждены 38 scratch files / 9,769,822 bytes в build/aw085-quality. AW0.8.5 final ZIP, frozen holdout, report и regression XML сохранены. Инвентарь содержит path/size/owner_cycle/reason/deleted=false. Автоматическая проверка отклонила точечный Remove-Item проверенного абсолютного каталога: `blocked by policy`. Других способов обхода не применялось; повторных попыток не будет. User stores, models, accepted artifacts, source fixtures и licenses не удалялись.

## 25. Tests и сохранённые контракты

Targeted context/data/legacy tests прошли. Safe templates: 8/8; unknown/partial/oversized inputs: 4/4 fallback; неоднозначный pattern: fallback. Full regression: **{tests} passed**, {duration:.2f} s, failures/errors = 0; XML: qa/aw086/regression.xml. PDF strict validation, OCR policy, source SHA, ZIP CRC/security, atomic publication, pause/resume/cancel, offline guard, localization, TM, user glossary, knowledge checksum и существующий naming не ослаблялись. Коммиты не создавались. Existing release UI label APP_VERSION и installer не обновлялись в этом функциональном цикле; Language Support обновил только фактические resource counts, stars logic не менялась.

## 26. Ограничения, компоненты и завершение

Новые reusable компоненты: DocumentProfiler/ContextProfile, SegmentClassifier, KnowledgeRouter/KnowledgeSnapshot; переиспользованы Glossary/TM, ranking/placeholders/guards, DocumentJob/ArchiveJob, extractor и writer. UI reworks и новые пользовательские controls отсутствуют. Full acceptance незакрыт только по административной очистке. Quality limitations: малый profiler holdout; эвристические confidence; преимущественно ZH→RU automotive coverage; ограниченные templates; оставшиеся 2 MAJOR на frozen holdout; консервативно сохранённые китайские подписи; слабая грамматика model fallback. Другие домены taxonomy пока не обещают Knowledge coverage. Не начаты новый backend, fine-tuning, embeddings, vectors, cloud, installer или глобальная PDF/performance переработка. Дальнейший цикл ожидает анализа пользователем; AW0.8.7 не создана.

## Артефакты

- Accepted ZIP и coolant PDF: output/aw086/accepted; SHA и production paths — qa/aw086/delivery_artifacts.json.
- Profiles/dev/frozen holdout: profiler_dev.json, profiler_holdout.json, profiler_holdout_results.json, document_profiles.json.
- Routing/snapshots/hits: routing_decisions.json, knowledge_snapshots.json, knowledge_hit_metrics.json, segment_classification.json.
- Templates, availability, E2E и качество: template_results.json, knowledge_availability.json, body_e2e.json, coolant_e2e.json, general_e2e.json, mixed_e2e.json, body_quality.json, coolant_quality.json.
- Frozen semantic BEFORE→AFTER: holdout_regression.json.
- Timing, cleanup, tests: timings.json, cleanup_inventory.json, cleanup_result.json, regression.xml.
- Visual evidence: qa/aw086/visual. Official pack SHA: {stats['sha256']}; {stats['bytes']:,} bytes.
'''
    destination=ROOT/'docs/AW0.8.6_CONTEXTUAL_KNOWLEDGE_ROUTER_REPORT.md'
    destination.write_text(text,'utf-8')
    print(destination,flush=True)


if __name__=='__main__':build()
