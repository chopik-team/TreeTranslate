"""Read-only analysis of a completed calibration; never changes production code."""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import sqlite3
import sys
from statistics import mean
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.aw081_speed_calibration_100 import QA, save, frozen_hashes
from app.documents.run_metrics import file_hash


def percentile(values, q):
    if not values:return None
    ordered=sorted(values);position=(len(ordered)-1)*q
    low=math.floor(position);high=math.ceil(position)
    return ordered[low]+(ordered[high]-ordered[low])*(position-low)


GROUPS=[
    ('OCR',{'ocr_recognize'}),
    ('model',{'model_translation'}),
    ('glossary',{'glossary_lookup'}),
    ('TM',{'translation_memory'}),
    ('templates',{'template_routing'}),
    ('guards',{'semantic_guards'}),
    ('writer',{'document_write'}),
    ('validation',{'pdf_validation'}),
    ('profiler/classification',{'DocumentProfiler','segment_classification'}),
    ('knowledge snapshot',{'knowledge_snapshot'}),
    ('extraction',{'preflight_open_extract','native_text_extract','archive_extract'}),
    ('archive append',{'archive_pack_member'}),
    ('path other',{'path_translation'}),
]


def exclusive_categories(events, wall):
    # Sweep actual time intervals; nested stages occupy the wall only once.
    endpoints=[]
    for event in events:
        priority=next((i for i,(_,names) in enumerate(GROUPS) if event['stage'] in names),None)
        if priority is None:continue
        end=min(wall,event['elapsed_since_run_start']);start=max(0,end-event['seconds'])
        if end>start:
            endpoints.extend(((start,priority,1),(end,priority,-1)))
    active=Counter();times=Counter();previous=0.0
    for point,priority,delta in sorted(endpoints):
        if active:
            owner=min(i for i,count in active.items() if count>0)
            times[GROUPS[owner][0]]+=point-previous
        active[priority]+=delta
        if active[priority]<=0:del active[priority]
        previous=point
    times['other/orchestration']=max(0,wall-sum(times.values()))
    return dict(times)


def generate(acceptable_hours=24):
    execution=json.loads((QA/'execution.json').read_text('utf8'))
    manifest=json.loads((QA/'sample_manifest.json').read_text('utf8'))
    before=json.loads((QA/'production_before.json').read_text('utf8'))
    assert frozen_hashes()==before and execution['production_unchanged']
    raw=json.loads((QA/'run_summary.json').read_text('utf8'))
    with sqlite3.connect(QA/'index.sqlite3') as database:
        documents=[json.loads(payload) for payload, in database.execute('SELECT payload FROM documents')]
    assert len(documents)==100 and execution['documents_packaged']==100 and raw['fatal_errors']==0
    info={row['member_path']:row for row in manifest['documents']}
    doc_by_member={row['archive_member_path']:row for row in documents}
    assert set(doc_by_member)==set(info)
    stages=defaultdict(lambda:dict(calls=0,seconds=0.0,failures=0))
    for line in (QA/'stages.jsonl').read_text('utf8').splitlines():
        row=json.loads(line);bucket=stages[row['stage']]
        bucket['calls']+=row['count'];bucket['seconds']+=row['seconds'];bucket['failures']+=row['failures']
    timing=[json.loads(line) for line in (QA/'timing_events.jsonl').read_text('utf8').splitlines()]
    starts={event['member']:event['elapsed_since_run_start'] for event in execution['events'] if event['event']=='document_start'}
    ends={event['source_member']:event['elapsed_since_run_start'] for event in execution['events'] if event['event']=='member_packaged'}
    ocr_by_doc=Counter();ocr_pages=set();ocr_regions=Counter()
    for event in timing:
        if event['stage']=='ocr_recognize':
            ocr_by_doc[event['document_id']]+=event['seconds']
            ocr_pages.add((event['document_id'],event['page']))
            ocr_regions[event['document_id']]+=1
    output=Path(execution['outputs'][0])
    import pypdfium2 as pdfium
    processed=[];source_pages=output_pages=output_bytes=source_bytes=0
    with ZipFile(output) as archive,ZipFile(manifest['sample_archive']) as source:
        assert archive.testzip() is None
        names=archive.namelist()
        assert sum(name.endswith('.pdf') for name in names)==100 and len(names)==len(set(names))
        for member,item in info.items():
            row=doc_by_member[member]
            entry=row['output_archive_member']
            data=archive.read(entry)
            digest=__import__('hashlib').sha256(data).hexdigest()
            assert digest==row['output_sha256']
            if row['output_status']=='FAILED_SOURCE_PRESERVED':
                assert entry==member and data==source.read(member)
            pdf=pdfium.PdfDocument(data)
            try:pages=len(pdf)
            finally:pdf.close()
            row.update(source_pages=item['pages'],output_pages=pages,output_size=len(data),
                member_latency_seconds=ends[member]-starts[member],ocr_measurement_seconds=ocr_by_doc[row['document_id']],
                measured_ocr_pages=len([pair for pair in ocr_pages if pair[0]==row['document_id']]),
                measured_ocr_regions=ocr_regions[row['document_id']],original_corpus_archive=manifest['input_archive'])
            processed.append(row)
            source_pages+=item['pages'] or 0;output_pages+=pages;source_bytes+=item['source_size'];output_bytes+=len(data)
            item['production']=dict(output_status=row['output_status'],classification=row.get('classification','unknown'),
                domain=(row.get('profiler') or {}).get('selected_domain','unknown'),
                subdomains=(row.get('profiler') or {}).get('selected_subdomains',{}),ocr_used=bool(ocr_regions[row['document_id']]),
                table_blocks=row.get('table_blocks'),schematic_blocks=row.get('schematic_blocks'),
                latency_seconds=row['member_latency_seconds'],output_archive_member=entry,output_pages=pages)
    processed.sort(key=lambda row:info[row['archive_member_path']]['index'])
    # Raw JSONL checkpoints use staging bindings. Keep them, and emit final
    # SQLite bindings plus measured page metadata in the requested flat file.
    shutil=__import__('shutil')
    shutil.copy2(QA/'documents.jsonl',QA/'documents.raw.jsonl')
    (QA/'documents.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in processed),'utf8')
    save(QA/'sample_manifest.json',manifest)
    wall=execution['wall_seconds'];latencies=[row['member_latency_seconds'] for row in processed]
    success=[row for row in processed if row['output_status']=='TRANSLATED'];failed=[row for row in processed if row['output_status']=='FAILED_SOURCE_PRESERVED']
    routing=[json.loads(line) for line in (QA/'routing.jsonl').read_text('utf8').splitlines()]
    attempts=[row for row in routing if row.get('event')=='backend_attempt']
    counters=Counter()
    for row in processed:counters.update(row['counters'])
    types=Counter(row.get('classification','unknown') for row in processed)
    exclusive=exclusive_categories(timing,wall)
    weighted=sum(info[row['archive_member_path']]['population_weight']*row['member_latency_seconds'] for row in processed)
    weighted_ocr=sum(info[row['archive_member_path']]['population_weight']*row['ocr_measurement_seconds'] for row in processed)
    fixed=max(0,wall-sum(latencies))
    typical=weighted+fixed+manifest['scan_seconds']
    families=defaultdict(list)
    for row in processed:families[info[row['archive_member_path']]['family']].append(row)
    randomizer=random.Random(81);bootstrap=[]
    for _ in range(2000):
        value=fixed+manifest['scan_seconds']
        for family,rows in families.items():
            value+=manifest['corpus_families'][family]['population']*mean(randomizer.choice(rows)['member_latency_seconds'] for _ in rows)
        bootstrap.append(value)
    failure_rate=len(failed)/100
    success_mean=mean(row['member_latency_seconds'] for row in success) if success else mean(latencies)
    failed_mean=mean(row['member_latency_seconds'] for row in failed) if failed else 0
    lower_failure_extra=17211*min(.10,failure_rate)*max(0,success_mean-failed_mean)
    optimistic=max(0,min(percentile(bootstrap,.10),typical-.25*weighted_ocr))
    conservative=max(percentile(bootstrap,.90),typical+.50*weighted_ocr+lower_failure_extra)
    weighted_pages=sum(info[row['archive_member_path']]['population_weight']*(row['source_pages'] or 0) for row in processed)
    estimates={name:dict(seconds=value,hours=value/3600,continuous_days=value/86400)
        for name,value in [('optimistic',optimistic),('typical',typical),('conservative',conservative)]}
    verdict='FULL LIVE RUN TIME ACCEPTABLE' if estimates['typical']['hours']<=acceptable_hours else 'FULL LIVE RUN TOO SLOW / OPTIMIZATION ADVISED'
    result=dict(schema=1,scope='100_PDF_SPEED_CALIBRATION_ONLY',run_id=raw['run_id'],status=raw['status'],
        total_wall_seconds=wall,production_job_wall_seconds=raw['total_wall_seconds'],preparation_seconds=manifest['preparation_seconds'],
        processed=100,translated=len(success),failed_source_preserved=len(failed),fatal=raw['fatal_errors'],
        source_bytes=source_bytes,output_bytes=output_bytes,source_pages=source_pages,output_pages=output_pages,
        output_zip=str(output),output_zip_sha256=file_hash(output),output_zip_bytes=output.stat().st_size,crc='PASS',
        throughput=dict(processed_docs_hour=100*3600/wall,translated_docs_hour=len(success)*3600/wall,
            source_pages_hour=source_pages*3600/wall,output_pages_hour=output_pages*3600/wall,
            processed_segments_second=counters['processed_segments']/wall,semantic_segments_second=counters['semantic_segments']/wall,
            source_mib_hour=source_bytes/1048576*3600/wall,output_mib_hour=output_bytes/1048576*3600/wall),
        latency=dict(mean=mean(latencies),median=percentile(latencies,.50),p50=percentile(latencies,.50),
            p90=percentile(latencies,.90),p95=percentile(latencies,.95),p99=percentile(latencies,.99),max=max(latencies),
            scope='child start through archive append; source ZIP extraction immediately before child tracked separately'),
        document_types=dict(types),ocr_used_count=len(ocr_by_doc),stages=dict(stages),exclusive_categories=exclusive,
        top5=sorted([dict(category=key,seconds=value,wall_share=value/wall) for key,value in exclusive.items()],key=lambda row:-row['seconds'])[:5],
        model=dict(m2m100_real_loads=stages['m2m100_model_load']['calls'],m2m100_load_or_reuse=stages['m2m100_load_or_reuse'],
            m2m100_inference=stages['m2m100_inference'],argos_loads=stages['argos_model_load'],argos_inference=stages['argos_inference'],
            attempts=len(attempts),attempt_failures=sum(not row['success'] for row in attempts),
            actual_devices=dict(Counter(row['device'] for row in attempts)),backend_devices=dict(Counter(row['backend']+'/'+row['device'] for row in attempts)),
            fallback_attempts=sum(row['fallback'] for row in attempts),segment_fallback_events=counters['fallback_events']),
        ocr=dict(seconds=sum(ocr_by_doc.values()),wall_share=sum(ocr_by_doc.values())/wall,pages=len(ocr_pages),regions=sum(ocr_regions.values()),
            documents=len(ocr_by_doc),median_document_seconds=percentile(list(ocr_by_doc.values()),.5),
            p90_document_seconds=percentile(list(ocr_by_doc.values()),.9),p95_document_seconds=percentile(list(ocr_by_doc.values()),.95),
            scope='ocr_recognize wall includes existing worker load/recognition/structure; OCR-attempt pages/regions including failures'),
        path=dict(seconds=stages['path_translation']['seconds'],calls=stages['path_translation']['calls'],**execution['path_cache']),
        routing_diagnostic=dict(counters),model_fallback_rate=raw['model_fallback_rate'],knowledge_coverage=raw['knowledge_coverage'],
        glossary_counters=execution['glossary_counters'],tm_counters=execution['tm_counters'],quality_score=None,
        warning_count=len((QA/'warnings.jsonl').read_text('utf8').splitlines()),failure_rate=failure_rate,
        failure_categories=dict(Counter((row.get('failure') or {}).get('primary_category','unknown') for row in failed)),
        failure_exceptions=dict(Counter((row.get('failure') or {}).get('exception_type','unknown') for row in failed)),
        failure_stages=dict(Counter((row.get('failure') or {}).get('stage','unknown') for row in failed)),
        estimates=estimates,forecast_method=dict(family_weighted_latency=True,fixed_seconds=fixed,
            full_scan_seconds=manifest['scan_seconds'],weighted_source_pages_estimate=weighted_pages,
            docs_hour_proxy_hours=17211/(100*3600/wall),pages_hour_proxy_hours=weighted_pages/(source_pages*3600/wall),
            bytes_hour_proxy_hours=manifest['inventory_pdf_bytes']/source_bytes*wall/3600,
            resampling_seed=81,resampling_repetitions=2000,bootstrap_p10_seconds=percentile(bootstrap,.1),bootstrap_p90_seconds=percentile(bootstrap,.9),
            optimistic_ocr_assumption='25% less OCR work than weighted sample',conservative_ocr_assumption='50% more OCR work and up to 10 percentage points fewer early failures',
            inference_limit='scenario band, not a confidence interval: deterministic size quantiles, rare strata with 1-2 PDFs and unmeasured corpus page/region count'),
        verdict=verdict,acceptable_typical_hours=acceptable_hours,source_immutable=execution['full_source_immutable'],
        production_unchanged=execution['production_unchanged'],logging_status=raw['logging_status'],observer_errors=execution['observer_errors'],
        semantic_regrade=False,training=False,full_corpus_run=False)
    save(QA/'run_summary.production.json',raw)
    save(QA/'run_summary.json',dict(raw,speed_calibration=result))
    save(QA/'calibration_analysis.json',result)
    report(result,manifest)
    assert frozen_hashes()==before
    print('REPORT_COMPLETE',verdict,estimates,flush=True)


def report(d,m):
    number=lambda value:f'{value:,.2f}'.replace(',',' ').replace('.',',')
    lines=['# AW0.81 — калибровка скорости на 100 PDF','',f"**{d['verdict']}**. Критерий: typical ≤ {d['acceptable_typical_hours']} ч непрерывной работы. Это оценка времени текущего pipeline, а не качества перевода.",'',
        f"Run `{d['run_id']}`: **100 processed, {d['translated']} TRANSLATED, {d['failed_source_preserved']} FAILED_SOURCE_PRESERVED, {d['fatal']} fatal**. Wall time **{number(d['total_wall_seconds'])} с / {number(d['total_wall_seconds']/60)} мин**. CRC итогового sample ZIP PASS; failed members имеют точные исходные пути и байты. Исходный CN7C ZIP и production-файлы неизменны.",'',
        '## Выборка','',
        'Ровно 100 PDF из 17 211. Страта — второй компонент исходного пути (10 групп руководств/процедур/диагностики/электросхем). Квота: floor(N_group × 100/17211), минимум один PDF; остаток распределяется по наибольшему дефициту. В группе сортировка (size, path), позиции floor((slot+0.5) × N_group/quota). Обработка возвращена в исходный inventory order. Случайности и ручного подбора удобных PDF нет. SHA каждого member проверен; имена и байты сохранены в отдельном 100-PDF ZIP.','',
        '| Группа | В корпусе | В sample |','|---|---:|---:|']
    for name,v in m['corpus_families'].items():lines.append(f"| {name} | {v['population']} | {v['sample']} |")
    lines+=['',f"Подготовка/scan/readonly metadata вне основного wall time: {number(m['preparation_seconds'])} с; scan всего источника с CRC: {number(m['scan_seconds'])} с. Sample source pages: {d['source_pages']}; output pages, включая сохранённые оригиналы: {d['output_pages']}. Source PDF bytes: {d['source_bytes']}; output member bytes: {d['output_bytes']}; итоговый ZIP: {d['output_zip_bytes']} bytes.",'',
        f"До OCR признаки native/raster: `{m['classification_counts']}`. Production classification: `{d['document_types']}`; OCR использован в {d['ocr_used_count']} документах. Значение 'unknown' означает, что pipeline не успел записать классификацию до ошибки; это не native. Детальные metadata и domain/subdomain каждого PDF — в manifest; production-данные вложены отдельно, не подменяют предварительную инспекцию.",'',
        'Выборка охватывает все 10 групп, размеры и несколько подсистем, но 100 PDF не гарантируют охват редких тяжёлых страниц и максимальных файлов. Image-only может отсутствовать: некоторые сканы/схемы имеют native навигационные заголовки. Native-слой сам по себе не исключает OCR vector/raster labels. Sample не использован для обучения или публикации Knowledge. TM и user glossary изолированы; builtin Knowledge и настройки pipeline штатные. Архивный контекст построен production-кодом по sample ZIP, поэтому он не побайтно равен контексту всех 17 211 member paths.','',
        '## Throughput и latency','', '| Метрика | Значение |','|---|---:|']
    for name,value in d['throughput'].items():lines.append(f'| {name} | {number(value)} |')
    lines+=['','docs/hour для прогноза включает все обработанные документы, в том числе failed originals. translated_docs_hour приведён отдельно. MB-показатели используют MiB (1 048 576 bytes). Failed originals входят в output bytes/pages.','',
        '| Latency | Секунды |','|---|---:|']
    for name,value in d['latency'].items():
        if isinstance(value,(int,float)):lines.append(f'| {name} | {number(value)} |')
    lines+=['','Latency: от child start до archive append, для успехов и failures. ZIP extraction непосредственно перед child записана отдельно. Percentiles — линейная интерполяция по 100 значениям.','',
        '## Этапы','', '**Inclusive:** вложенные времена ниже нельзя складывать как независимые.','', '| Stage | Calls | Seconds |','|---|---:|---:|']
    names=['preflight_open_extract','archive_extract','ocr_recognize','DocumentProfiler','segment_classification','knowledge_snapshot','glossary_lookup','translation_memory','template_routing','model_translation','semantic_guards','document_write','pdf_validation','archive_pack_member','path_translation']
    for name in names:
        v=d['stages'].get(name,dict(calls=0,seconds=0));lines.append(f"| {name} | {v['calls']} | {number(v['seconds'])} |")
    o=d['ocr'];model=d['model'];path=d['path']
    lines+=['',f"OCR: **{number(o['seconds'])} с / {number(o['wall_share']*100)}% wall**, {o['pages']} pages, {o['regions']} regions, {o['documents']} documents. Median OCR doc: {number(o['median_document_seconds'] or 0)} с; p90 {number(o['p90_document_seconds'] or 0)} с; p95 {number(o['p95_document_seconds'] or 0)} с. Включены штатная загрузка OCR worker/recognition/structure и неуспешные попытки; это не только время собственно распознавания.",'',
        f"M2M100: real loads {model['m2m100_real_loads']}; load/reuse {model['m2m100_load_or_reuse']['calls']} / {number(model['m2m100_load_or_reuse']['seconds'])} с; inference {model['m2m100_inference']['calls']} / {number(model['m2m100_inference']['seconds'])} с. Argos loads {model['argos_loads']['calls']} / {number(model['argos_loads']['seconds'])} с. Backend attempt failures {model['attempt_failures']}; devices `{model['actual_devices']}`; backend/device `{model['backend_devices']}`; fallback attempts {model['fallback_attempts']}, segment fallback events {model['segment_fallback_events']}.",'',
        f"Path translation: {number(path['seconds'])} с, {path['calls']} calls, cache hits {path['hits']}, misses {path['misses']}, unique cached translations {path['entries']}, folder components {path['folder_components']}. Кеш учитывает контекст и язык; одинаковые слова в разных snapshots могут иметь разные ключи. Повторное использование уже созданного directory_map не считается новым вызовом кеша.",'',
        '## TOP-5 bottlenecks','',
        'Ниже времена распределены по фактическим интервалам: вложенный OCR/model/glossary/TM исключается из родительских stages. Один участок wall time учитывается один раз; это помогает сравнить категории без суммирования inclusive parents.','',
        '| Категория | Секунды | Wall % | Возможность ускорения при сохранении качества |','|---|---:|---:|---|']
    opportunities={'OCR':'Потенциал есть в lifecycle/повторных загрузках, если они доминируют; требует отдельного измерения без смены моделей/параметров. Не оптимизировано.',
        'model':'Можно изучить фактические повторные загрузки и допустимое переиспользование; менять модель/beam/параметры здесь нельзя.',
        'writer':'Возможен анализ повторных операций шрифтов/страниц; без изменений layout и обязательной validation.',
        'glossary':'Возможен анализ повторных lookup/SQL/cache; терминология и правила должны остаться теми же.',
        'validation':'Допустимы только устранение дублированной работы или IO; обязательные проверки сохраняются.',
        'other/orchestration':'Категория остаточная; сначала нужна детализация, обещать ускорение по одному суммарному числу нельзя.'}
    for row in d['top5']:lines.append(f"| {row['category']} | {number(row['seconds'])} | {number(row['wall_share']*100)} | {opportunities.get(row['category'],'Требует отдельного анализа повторной работы; в этой задаче не оптимизировалось.')} |")
    lines+=['','## Прогноз 17 211 PDF','', '| Сценарий | Часы | Сутки непрерывной работы |','|---|---:|---:|']
    for name,value in d['estimates'].items():lines.append(f"| {name.upper()} | {number(value['hours'])} | {number(value['continuous_days'])} |")
    f=d['forecast_method'];t=d['estimates']['typical']['hours'];low=d['estimates']['optimistic']['hours'];high=d['estimates']['conservative']['hours']
    lines+=['',f"Если workload похож на sample: typical **{number(t)} ч**, диапазон сценариев **{number(low)}–{number(high)} ч** (−{number(t-low)} / +{number(high-t)} ч). Использованы веса N_group/sample_group, реальные document latency и OCR seconds; фиксированная часть sample {number(f['fixed_seconds'])} с не размножается 172 раза. Добавлен фактический scan полного источника. Прогноз weighted source pages: {number(f['weighted_source_pages_estimate'])}; точное количество страниц полного ZIP пока неизвестно.",'',
        f"Проверки по throughput: docs/hour → {number(f['docs_hour_proxy_hours'])} ч; pages/hour → {number(f['pages_hour_proxy_hours'])} ч; source bytes/hour → {number(f['bytes_hour_proxy_hours'])} ч. Byte proxy слабее: размер сжатого изображения не определяет число OCR regions. Это не перенос времени первого PDF на весь архив.",'',
        'OPTIMISTIC: нижний p10 при стратифицированном resampling среднего (2000 повторов, seed=81) либо на 25% меньше OCR workload. TYPICAL: взвешенный средний текущей выборки. CONSERVATIVE: верхний p90 resampling либо +50% OCR workload и до 10 процентных пунктов меньше ранних failures, которые могут требовать полного writer/validation. Разница времени success/failure использована только если она положительна.','',
        f"Failure rate sample **{number(d['failure_rate']*100)}%** входит в прогноз текущего поведения. Это скорость processing, не гарантия успешного перевода всех PDF. Если failures будут исправлены в будущей задаче, время может вырасти. Сценарный диапазон **не является статистическим confidence interval**: выборка детерминирована, редкие strata представлены 1–2 PDF, corpus pages/regions не подсчитаны. Heat/throttling, конкурирующие процессы, диск и редкий тяжёлый хвост могут расширить диапазон.",'',
        '## Routing diagnostics и blockers','',
        f"Model fallback rate {number((d['model_fallback_rate'] or 0)*100)}%; Knowledge coverage {number((d['knowledge_coverage'] or 0)*100)}%. Warnings {d['warning_count']}. Routing counters: `{d['routing_diagnostic']}`. Glossary lookup/hit counters: `{d['glossary_counters']}`. TM counters: `{d['tm_counters']}`. Эти частоты не являются semantic quality score; MAJOR/MINOR/CATA не переоценивались.",'',
        f"Document failure categories `{d['failure_categories']}`; stages `{d['failure_stages']}`; exceptions `{d['failure_exceptions']}`.",'',
        f"Global fatal: {d['fatal']}; logging `{d['logging_status']}`; observer errors `{d['observer_errors']}`. Ненулевой FAILED_SOURCE_PRESERVED остаётся ограничением результата полного run: оригиналы будут сохранены, но часть документов не переведётся. Неисправленные причины document failures перечислены в errors.jsonl и production summary. При слишком большом времени следующий шаг — решение пользователя об отдельной performance-задаче, без автоматической оптимизации здесь.",'',
        '## Evidence и STOP','',
        '[Sample manifest — точные 100 PDF](C:/TreeTranslate/qa/aw081/speed_calibration_100/sample_manifest.json) · [Итоги и machine-readable анализ](C:/TreeTranslate/qa/aw081/speed_calibration_100/run_summary.json) · [Execution receipt](C:/TreeTranslate/qa/aw081/speed_calibration_100/execution.json).','',
        'В той же папке: stages.jsonl, documents.jsonl (финальные bindings), documents.raw.jsonl (исходные checkpoints), routing.jsonl, errors.jsonl, resource_samples.jsonl, archive_events.jsonl, warnings.jsonl, timing_events.jsonl и index.sqlite3. Original production logs сохранены в logs/<run_id>/.','',
        '**STOP.** Полный ZIP не запускался. Production code/Knowledge/NMT/Router policy/UI/OCR architecture/archive recovery не изменялись, после замера не оптимизировались. PHASE B/C, AW0.82, installer, обучение и commit не выполнялись.']
    (ROOT/'docs/AW0.81_100PDF_SPEED_CALIBRATION.md').write_text('\n'.join(lines)+'\n','utf8')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--acceptable-hours',type=float,default=24)
    args=parser.parse_args();generate(args.acceptable_hours)
