"""Preserve delivery hashes, review evidence and a concrete completion report."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw087_build import QA,PACK,save

def read(path):return json.loads((ROOT/path).read_text('utf-8'))

def artifacts():
    directory=ROOT/'output/aw087/accepted';directory.mkdir(exist_ok=True)
    delivery=[]
    for corpus,name in [('body','Размеры кузова_ru.zip'),('coolant','Охлаждение_ru.pdf')]:
        result=read('qa/aw087/'+corpus+'_e2e.json');source=Path(result['outputs'][0]);destination=directory/name
        shutil.copy2(source,destination)
        assert sha256(source.read_bytes()).hexdigest()==sha256(destination.read_bytes()).hexdigest()
        assert result['source_hash_before']==result['source_hash_after']
        delivery.append(dict(corpus=corpus,path=str(destination),production_path=str(source),bytes=destination.stat().st_size,
            sha256=sha256(destination.read_bytes()).hexdigest(),source_sha256=result['source_hash_after']))
    save('delivery_artifacts.json',delivery)
    old=read('qa/aw086/holdout_regression.json');current=read('qa/aw087/holdout_regression.json');counts=Counter();changes=[]
    for previous,row in zip(old['rows'],current['rows']):
        changed=previous['after']!=row['after'];grade='MAJOR' if row['id']=='prose-06' and changed else previous['after_status']
        reason='Wrong pretensioner entity; prohibition retained' if row['id']=='prose-06' and changed else 'Russian phrasing changed; condition/entity retained' if changed else 'Unchanged from AW086 semantic review'
        row.update(before_aw086=previous['after'],before_aw086_grade=previous['after_status'],after_status=grade,review_reason=reason)
        counts[grade]+=1
        if changed:changes.append(row)
    current.update(before_aw086_summary=old['after_summary'],after_summary=dict(counts),changed_from_aw086=changes,reviewer='Codex explicit source/output review; not independent human certification')
    save('holdout_regression.json',current)
    from tools.knowledge_harvester.storage import Store
    from tools.knowledge_harvester.corpus import candidate,review
    from tools.knowledge_harvester.provenance import digest_json
    store=Store(QA/'harvester.db');uid=candidate(store,source='排气',target='выпуск отработавших газов',domain='automotive',subdomains=['engine'],origin='AUTHORED',
        provenance=dict(source='AW087 authored contextual sense',permission='AUTHORED_FOR_PROJECT'))
    with store.connect() as con:row=json.loads(con.execute('SELECT payload FROM candidates WHERE id=?',(uid,)).fetchone()[0])
    if row['status']!='VERIFIED':
        for state in ['REVIEWED','VERIFIED']:review(store,uid,state,reviewer='Codex',reason='Reviewed engine exhaust sense; cooling air-bleeding sense remains separate',evidence_sha256=digest_json(row['provenance']))
    reviewed=read('qa/aw087/candidate_review.json')
    if not any(r['candidate_id']==uid for r in reviewed):reviewed.append(dict(candidate_id=uid,source='排气',target='выпуск отработавших газов',subdomains=['engine'],review_state='VERIFIED',provenance='AUTHORED',reviewer='Codex'))
    save('candidate_review.json',reviewed)
    with Store(QA/'intake.db').connect() as con:
        candidates=[json.loads(r[0]) for r in con.execute('SELECT payload FROM candidates ORDER BY id')]
    save('candidate_phrases.json',[r for r in candidates if r['type']=='PHRASE'])
    save('candidate_extraction_metrics.json',dict(types=dict(Counter(r['type'] for r in candidates)),states=dict(Counter(r['status'] for r in candidates)),verified_from_raw_documents=0,
        ocr_policy='Native intake by default; production-captured OCR segments can be supplied through the same candidate API with provenance. Automatic extra OCR intake not enabled.'))
    # Preserve development sources/results separately from new holdout references.
    coolant=read('qa/aw087/coolant_e2e.json')
    save('semantic_dev.json',dict(source='Existing coolant fixture and procedure tests, used for development before new holdout evaluation',
        source_sha256=coolant['source_hash_before'],rows=[dict(source=s['text'],output=s['translated']) for s in coolant['documents'][0]['segments']]))
    inventory=read('qa/aw087/cleanup_inventory.json')
    for row in inventory:row.update(deleted=False,deletion_status='blocked_by_policy')
    old_dir=ROOT/'build/aw085-quality';old_files=[p for p in old_dir.rglob('*') if p.is_file()] if old_dir.exists() else []
    inventory.extend(dict(path=str(p),size=p.stat().st_size,owner_cycle='AW0.8.5',reason='Previously inventoried scratch; accepted evidence retained',deleted=False,deletion_status='blocked_by_policy') for p in old_files if str(p) not in {r['path'] for r in inventory})
    save('cleanup_inventory.json',inventory)
    save('cleanup_result.json',dict(status='blocked_by_policy',old_files=len(old_files),old_bytes=sum(p.stat().st_size for p in old_files),
        new_scratch_files=sum(r['owner_cycle']=='AW0.8.7' for r in inventory),new_scratch_bytes=sum(r['size'] for r in inventory if r['owner_cycle']=='AW0.8.7'),
        attempted_old_once=True,attempted_new_once=True,no_workaround=True))
    # Required metadata fields include zero counters, rather than silently omitting them.
    metrics={}
    for name in ['body','coolant']:
        result=read('qa/aw087/'+name+'_e2e.json');m=result['context']['metrics'];segments=[s for d in result['documents'] for s in d['segments']]
        availability=read('qa/aw087/knowledge_availability.json')['counts'] if name=='body' else None
        coolant_rows=read('qa/aw087/coolant_before_after.json')['segments'] if name=='coolant' else []
        metrics[name]=dict(context=result['context'],semantic_segments=availability['KNOWN']+availability.get('UNKNOWN',0) if availability else sum(s['text']!='目' for s in segments),
            knowledge_available=availability['KNOWN'] if availability else sum(r['category'] in {'EXACT_KNOWN','TEMPLATE_KNOWN','DIRECT_KNOWN'} for r in coolant_rows),
            unknown_concepts=availability.get('UNKNOWN',0) if availability else sum(r['category']=='UNKNOWN_CONCEPT' for r in coolant_rows),
            exact_hits=m.get('exact_hits',0),compound_hits=m.get('compound_hits',0),phrase_hits=m.get('phrase_hits',0),template_hits=m.get('template_hits',0),
            term_guidance=m.get('term_hits',0),model_fallbacks=m.get('model_fallbacks',0),model_router_calls=len(result['model_calls']),
            unknown_slot_candidates=m.get('unknown_slot',0),ambiguous_concepts=m.get('ambiguous_concepts',0))
    save('knowledge_metrics.json',metrics)
    return delivery

def report():
    before=read('qa/aw087/knowledge_before.json');after=read('qa/aw087/knowledge_after.json')
    body=read('qa/aw087/body_regression.json');coolant=read('qa/aw087/coolant_before_after.json');quality=read('qa/aw087/coolant_semantic_review.json')
    held=read('qa/aw087/semantic_holdout_results.json');old=read('qa/aw087/holdout_regression.json');scale=read('qa/aw087/scale_benchmark.json')
    timings=read('qa/aw087/timings.json');cleanup=read('qa/aw087/cleanup_result.json');delivery=read('qa/aw087/delivery_artifacts.json')
    suite=ET.parse(QA/'regression.xml').getroot().find('testsuite');assert suite.get('errors')==suite.get('failures')=='0'
    metrics=read('qa/aw087/knowledge_metrics.json');profile=read('qa/aw087/profiler_holdout_results.json')
    assert body['after']['protected_preserved']==419 and body['after']['output_pages']==22 and all(r['status']=='PASS' for r in body['stable_instructions'])
    assert profile['passed']==8 and held['grades'].get('CATASTROPHIC',0)==0
    templates=read('assets/config/knowledge-templates.json')['templates'];forms=read('assets/config/automotive-slot-forms.json')['forms'];actions=read('assets/config/technical-actions.json')['actions']
    sections=[]
    def section(title,body):sections.append('## '+str(len(sections)+1)+'. '+title+'\n\n'+body)
    section('Исходная база',f'AW0.8.6: {before["entries"]} ZH→RU automotive entries, M2M100 418M/Argos/PaddleOCR, TM/Glossary и Contextual Router. Body: 22 страницы, 419/419 protected. Coolant: исторический счётчик 37 model fallback, девять template hits, 4→5 страниц. Новый NMT backend не создавался.')
    section('Зачем расширять Knowledge', 'Контекстный поиск уже ограничивает область словаря. Полезнее добавлять короткие понятия и структуры действий, чем сохранять целые руководства. Процедура связывает действие, объект и падеж; неизвестный свободный текст остаётся модели. Coverage и semantic quality оцениваются отдельно.')
    section('Архитектура Harvester', 'Переиспользованы tools/knowledge_harvester: Store/SQLite, provenance/digest, normalization, candidate/alias/conflict/review tables и существующий app.glossary.packs.build_pack. Новый corpus.py — document adapter внутри того же инструмента, не второй engine. Additive corpus_documents/document_evidence не меняют пользовательский Schema 1. Существующий source ingest/link/build workflow сохранён; corpus workflow использует отдельную dev DB.')
    section('Corpus intake', 'CLI: `python -m tools.knowledge_harvester.cli --db qa/corpora/incoming/harvest.db corpus-intake PATH --corpus-id ID --language zh --origin USER_PROVIDED --permission REVIEW_REQUIRED`. Поддерживаются PDF, DOCX, ZIP и папки; TXT/TSV также доступны для authored inputs. Сохранены ID, path/member, language, domain/subdomains, type, SHA256 контейнера и члена, permission, timestamp/version. ZIP проходит существующие path/CRC/size checks; чтение последовательное, source SHA проверяется после обработки. В проверочном inventory восемь документов. Native intake не выполняет дополнительный OCR: это явное ограничение; OCR evidence текущего production capture можно передать через candidate API. Original user files не копируются в assets.')
    section('Provenance и права', 'AUTHORED, USER_PROVIDED, EXISTING_PROJECT_FIXTURE, LICENSED_OPEN_SOURCE, MODEL_SUGGESTED и DERIVED_FROM_EXISTING_KNOWLEDGE доступны как типы происхождения. Новый pack состоит из коротких авторских концептов; review выполнен Codex, не независимым человеком. Сырые модели и copyrighted paragraphs не объявлены VERIFIED. Official pack adapter допускает только review с неизменным digest и разрешением AUTHORED_FOR_PROJECT/APPROVED_FOR_REDISTRIBUTION. Permission REVIEW_REQUIRED/CANDIDATES_ONLY не разрешает redistribution.')
    section('Candidate pipeline', 'Intake → normalized candidates → exact/declared-alias dedup → context conflict detection → REVIEWED → VERIFIED/REJECTED/AMBIGUOUS/DEPRECATED. Повторный corpus id/hash не плодит записи. Изменение evidence инвалидирует verification. TERM/COMPOUND/PHRASE/TEMPLATE/ABBREVIATION извлекаются из коротких текстов и действий; ALIAS/FULL_SEGMENT/CONCEPT_RELATION поддержаны в candidate API и review, но не обещают автоматический discovery всех видов. `corpus-export` экспортирует JSONL, `corpus-review` принимает explicit review, `corpus-build-pack` адаптирует только eligible records к существующему writer. Model output не может автоматически стать VERIFIED.')
    section('DB BEFORE',f'{before["entries"]} записей; {before["bytes"]:,} bytes. Types: '+json.dumps(before['types'],ensure_ascii=False)+'. SHA256: `'+before['sha256']+'`. Снимок сохранён до расширения.')
    section('DB AFTER',f'{after["entries"]} записей (**+{after["entries"]-before["entries"]}**, без искусственного потолка); {after["bytes"]:,} bytes. Types: '+json.dumps(after['types'],ensure_ascii=False)+f'. Concepts: {after["concepts"]}; aliases: {after["aliases"]}; review states: '+json.dumps(after['review_states'])+'. FULL_SEGMENT остались 12: снижение fallback не получено копированием длинных предложений. SHA256: `'+after['sha256']+'`.')
    section('Домены и поддомены', '| Subdomain | Entries (multi-label) |\n|---|---:|\n'+'\n'.join(f'| {k} | {v} |' for k,v in sorted(after['subdomains'].items()))+'\n\nСодержательно расширены cooling/engine/electrical/diagnostics, transmission/brakes/HVAC, suspension, body repair/measurement и common. Другие языки поддержаны intake metadata; массовое новое multilingual покрытие не обещано.')
    section('Действия и семантические отношения', f'{len(actions)} action records: '+', '.join(sorted({a['semantic_id'] for a in actions}))+'. Они связываются с template action IDs; не применяются как глобальная подстановка глаголов. Шесть лёгких reviewed relations IS_A/PART_OF/RELATED_TO/ACTION_ON/USED_WITH сохранены в существующей SQLite relations для review; graph database не добавлена. Нет нового универсального morphology engine.')
    section('Шаблоны',f'{len(templates)} VERIFIED bounded templates, включая прежние восемь; разные imperative/heading и punctuation варианты считаются отдельными rules. Literal structure, максимум 512 characters/3 slots по 128, explicit whitelist и known forms. Unknown/ambiguous slot, чужой context, protected mismatch и неизвестный хвост дают NMT. Полное exact TM/User Glossary и известный compound сохраняют приоритет. Максимум три complete sentence templates могут быть соединены только если каждая часть подтверждена; partial composition не публикуется. General technical templates переиспользуют forms без domain-specific runtime code; отдельный тест подтвердил industrial «Затяните болт» через добавление только данных.')
    section('Русские формы и negation', f'{len(forms)} explicit slot-form records: base/nominative, accusative, genitive; instrumental/prepositional только для нужных конструкций. «Снимите крышку радиатора», «Установите узел вентилятора охлаждения», «Долейте охлаждающую жидкость» проходят реальные template paths. negative_relation — консервативный счётчик отрицательных смысловых маркеров для curated structures, не универсальная логическая модель. Signed slots/known clauses не допускают произвольный отрицательный текст. Guards усилены распознаванием ASCII identifiers и чисел на границе китайской письменности: GDS/VIN и 20分钟 сохраняются, исчезновение/замена отклоняются.')
    section('Аудит исторических 37 fallback', 'В AW0.8.6 сохранён aggregate counter 37, но нет source-level route trace. Проведена явная реконструкция с исходными 301 rows и legacy templates: 39 raw records; два дополнительных idle вызова объясняются новым warning-region typing. Raw39 сохранены, а список без этих двух содержит 37 записей с source/type/context/reason/concepts/pattern/model-required. Это реконструкция, не выданные за исторические логи. Counter includes filename. Модель с glossary constraints также делает запрос к router; поэтому bare fallback и model router calls не смешиваются.')
    section('Coolant BEFORE→AFTER', '| Metric | AW0.8.6 | AW0.8.7 |\n|---|---:|---:|\n'+f'| Bare model fallback | 37 | {coolant["after"]["model_fallbacks"]} |\n| Template hits | 9 | {coolant["after"]["template_hits"]} |\n| Pages | 5 | {coolant["after"]["pages"]} |\n| Job seconds | 67.82 | {coolant["after"]["wall_seconds"]:.2f} |\n'+f'\nModel router calls: reconstructed baseline {coolant["reconstruction"]["model_router_calls"]} → {coolant["after"]["model_router_calls"]}; это requests к router, не измерение translator.translate_batch и не число cache misses. Семь критических term checks сохранили все occurrences. Заголовок исправлен, imperative/connector/GDS/ITM/fill/drain/negation/pressure warning стабилизированы. Native продолжения сохранены, четыре страницы искусственно не навязывались. Source SHA неизменен.')
    section('Полный semantic review coolant', '| Grade | BEFORE | AFTER |\n|---|---:|---:|\n'+'\n'.join(f'| {g} | {quality["before_grades"].get(g,0)} | {quality["after_grades"].get(g,0)} |' for g in ['PASS','MINOR','MAJOR','CATASTROPHIC','EXCLUDED_OCR_NOISE'])+'\n\nПросмотрен каждый опубликованный semantic block. Остаются девять MAJOR: четыре повреждённые cross-references, три неоднозначные diagnostic labels и две строки объёма с ненадёжным переводом imperial units. Все числа сохранены, но это не доказывает смысл единиц. Шесть MINOR отмечают неоднозначные исходные формулировки концентрации. 14 «目» исключены как preserved OCR noise. Это review Codex, не полная OEM/человеческая сертификация; ещё нельзя считать руководство безошибочным.')
    section('Body regression', '22→22 страницы; 419/419 protected; 130/131 concepts до placement, 117/131 published; strict 110/100, как раньше. Knowledge availability 133/133, 232 protected. OCR continuations/noise overlays = 0/0; 16 китайских placement-preserved блоков и семь noise elements остаются по прежней политике. Все десять instruction references PASS; ZIP CRC и source SHA проверены. Все 22 страницы и пять страниц coolant отрендерены PDFium и просмотрены; глобальный writer/layout не менялся.')
    section('Новый holdout и freeze', '| Grade | Count |\n|---|---:|\n'+'\n'.join(f'| {g} | {held["grades"].get(g,0)} |' for g in ['PASS','MINOR','MAJOR','CATASTROPHIC'])+'\n\n120 authored examples, восемь областей, новые комбинации action/object и 16 свободных prose cases. Синтетический набор проверяет композицию, не заменяет unseen user/OEM documents. References заморожены до evaluation и не переписаны. После freeze исправлены только targets двух старых drain templates по уже известному coolant development corpus («вода»→«жидкость»). Это прозрачное изменение knowledge revision после freeze: исходный template JSON/hash, correction ledger и предыдущие outputs сохранены. Повторная оценка дала все 120 outputs неизменными. Никаких новых entries/patterns по failed holdout не добавлено. В некоторых prose references есть неверное родовое согласование; errata указана отдельно, исходный файл сохранён.')
    section('Старый holdout, конфликты и неоднозначность', f'Frozen40 AW0.8.6 → AW0.8.7: PASS {old["before_aw086_summary"].get("PASS",0)}→{old["after_summary"].get("PASS",0)}, MINOR {old["before_aw086_summary"].get("MINOR",0)}→{old["after_summary"].get("MINOR",0)}, MAJOR {old["before_aw086_summary"].get("MAJOR",0)}→{old["after_summary"].get("MAJOR",0)}, CATA 0→0. Есть реальная регрессия: «преднатяжитель ремня» стал «защитные пояса»; запрет повреждения сохранён. Она не исправлена добавлением knowledge по holdout. На новом наборе семь MAJOR связаны с неверным объектом в свободной условной фразе; условия остановки сохранены. Profiler frozen holdout 8/8. Context-specific 排气 cooling/engine не схлопываются; strongest context разрешает sense, равные конкурирующие смыслы отклоняются. Existing synonym/alias duplicates объединяются, conflicting existing stable-rod target сохранён, новая альтернатива отложена.')
    section('Scale benchmark', '| DB rows | Active snapshot | Median snapshot, ms | Candidate lookup, µs |\n|---:|---:|---:|---:|\n'+'\n'.join(f'| {r["total_entries"]} | {r["active_snapshot_entries"]} | {r["snapshot_median_seconds"]*1000:.2f} | {r["candidate_lookup_seconds"]*1e6:.2f} |' for r in scale['rows'])+'\n\nSynthetic inactive metadata, actual production SQL/candidates, seven cold snapshot trials. UNION по доменам использует полный context_selection index; EXPLAIN подтверждает SEARCH, не metadata full scan. Active snapshot постоянный; исследование не доказывает постоянное время для 25k одновременно релевантных concepts. Сохраняются bounds 2048 active entries/12 snapshots и существующий indexed fallback. Scale rows не попали в production pack.')
    section('Время и размер', '| Corpus | Wall, s | Profile, s | Snapshot, s | Lookup, s | Templates, s |\n|---|---:|---:|---:|---:|---:|\n'+'\n'.join(f'| {name} | {r["wall_seconds"]:.2f} | {r["routing"].get("document_profile_time",0):.4f} | {r["routing"].get("snapshot_build_time",0):.4f} | {r["routing"].get("knowledge_lookup_total",0):.2f} | {r["routing"].get("template_time",0):.3f} |' for name,r in timings.items())+f'\n\nPack {before["bytes"]:,}→{after["bytes"]:,} bytes. Lookup включает legacy/user SQLite, не только новый overhead. Counters включают names и попытки direct lookup; не складываются механически в segment count. Это измерения одной машины/итоговых runs, не статистическое обещание скорости. process timings/source type/profile/snapshot/lookup/template/model route counters сохранены отдельно. Runtime logs не содержат developer history или raw source/target.')
    section('Очистка', f'Automatic approval review отклонила обе точечные операции: old build/aw085-quality ({cleanup["old_files"]} files/{cleanup["old_bytes"]:,} bytes) и confirmed build/aw087-scale ({cleanup["new_scratch_files"]} files/{cleanup["new_scratch_bytes"]:,} bytes): `blocked by policy`. Инвентарь сохранён, deleted=false. Обходов/повторных попыток нет. Corpora/gold/holdout/reports/accepted outputs/production DB/models/licenses не удалялись. Административная очистка остаётся открытой.')
    section('Regression и контракты', f'Full pytest: **{suite.get("tests")} passed**, {float(suite.get("time")):.2f} s, failures/errors=0. Harvester tests: extraction/idempotence/SHA/review/digest/model prohibition/permissions/alias/conflicts/languages/unsafe ZIP. Procedure tests: imperative/heading/grammar/unknown/negation/composition/protected IDs/numbers/industrial reuse. Existing TM/User Glossary priority, source immutability, PDF/OCR policy, ZIP/cancel/pause/resume/atomic publication/offline/localization/naming не ослаблялись. Language Support обновил только actual counters; stars/history и UI version/installer не переработаны. Коммитов нет.')
    section('Ограничения и завершение', 'Функциональный цикл AW0.8.7 реализован. Ограничения: review не независимый; native-only intake; heuristic candidate extraction и negation counter; фиксированные safe forms; synthetic holdout и reference errata; семь MAJOR на новом holdout; регрессия одного старого unseen warning; девять MAJOR блоков coolant; консервативные китайские подписи body; незавершённая policy-blocked cleanup. No blanket quality guarantee. Никаких новых UI controls, NMT backend, cloud, vectors/embeddings, fine-tuning, installer или stars recalculation. После доставки цикл остановлен; новые пользовательские файлы идут отдельным corpus с baseline ДО расширения данных и untouched документами для holdout.')
    sections[21]+='\n\nОдин промежуточный полный прогон дал 769 passed/1 failed: существующий Qt animation test не увидел кадр в фиксированном таймерном окне. Isolated оба animation tests прошли; финальный полный прогон прошёл без изменений UI или ослабления теста. Исходный failed XML сохранён как regression_timer_failure.xml.'
    text='# TreeTranslate AW0.8.7 — Technical Knowledge Harvester & Procedure Language\n\nДата: 02.10.2026. Проект: C:\\TreeTranslate.\n\n'+'\n\n'.join(sections)+'\n\n## Артефакты\n\n'
    text+='- [Индекс QA](../qa/aw087/FINAL_RESULTS.md)\n- [ZIP](../output/aw087/accepted/Размеры кузова_ru.zip)\n- [PDF](../output/aw087/accepted/Охлаждение_ru.pdf)\n'
    (ROOT/'docs/AW0.8.7_TECHNICAL_KNOWLEDGE_HARVESTER_REPORT.md').write_text(text,'utf-8')
    required=['corpus_inventory.json','knowledge_before.json','knowledge_after.json','candidate_terms.json','candidate_compounds.json','candidate_phrases.json','candidate_templates.json','candidate_conflicts.json','candidate_review.json','concept_relations.json','coolant_fallback_audit.json','coolant_before_after.json','body_regression.json','semantic_dev.json','automotive_semantic_holdout.json','semantic_holdout_results.json','knowledge_metrics.json','template_metrics.json','scale_benchmark.json','timings.json','cleanup_inventory.json','regression.xml']
    assert all((QA/name).exists() for name in required)
    index='# AW0.8.7 — результаты и файлы\n\n'+f'Knowledge {before["entries"]}→{after["entries"]}; bare coolant fallback 37→{coolant["after"]["model_fallbacks"]}; body 22→22/419 protected; full pytest {suite.get("tests")} passed.\n\n'
    index+='[Подробный отчёт](../../docs/AW0.8.7_TECHNICAL_KNOWLEDGE_HARVESTER_REPORT.md) · [ZIP](../../output/aw087/accepted/Размеры кузова_ru.zip) · [PDF](../../output/aw087/accepted/Охлаждение_ru.pdf)\n\n'
    index+='\n'.join('- ['+name+']('+name+')' for name in [*required,'coolant_semantic_review.json','holdout_regression.json','profiler_holdout_results.json','post_freeze_development_correction.json','delivery_artifacts.json','cleanup_result.json'])
    index+='\n\nОстаются semantic errors; старый holdout MAJOR 2→3, новый MAJOR 7/CATA0. Cleanup blocked by policy. Подробности и correction ledger приведены в отчёте.\n'
    (QA/'FINAL_RESULTS.md').write_text(index,'utf-8')
    print('Report',ROOT/'docs/AW0.8.7_TECHNICAL_KNOWLEDGE_HARVESTER_REPORT.md')

if __name__=='__main__':artifacts();report()
