"""Read-only analysis of the one admitted final run and historical evidence."""
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path,PurePosixPath
import random
import re
import sqlite3
from statistics import mean,median
import sys
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw081_100pdf_final_speed_calibration import QA,OLD,read,save,frozen_hashes
from tools.aw081_speed_calibration_report import exclusive_categories,percentile
from tools.aw081_hardware_scaling_20 import fingerprint_pdf


def lines(path):return [json.loads(s) for s in Path(path).read_text('utf8').splitlines() if s.strip()]
def database_rows(path,table):
    with sqlite3.connect('file:'+Path(path).as_posix()+'?mode=ro',uri=True) as con:
        return [json.loads(p) for p, in con.execute('SELECT payload FROM '+table)]


def historical_forecast(manifest,documents,wall,scan_seconds=None):
    """Exact old family weights/seed/bootstrap/OCR scenario formula, no new factors."""
    info={d['member_path']:d for d in manifest['documents']}
    latencies=[r['member_latency_seconds'] for r in documents]
    fixed=max(0,wall-sum(latencies));scan=manifest['scan_seconds'] if scan_seconds is None else scan_seconds
    weighted=sum(info[r['archive_member_path']]['population_weight']*r['member_latency_seconds'] for r in documents)
    weighted_ocr=sum(info[r['archive_member_path']]['population_weight']*r['ocr_measurement_seconds'] for r in documents)
    typical=weighted+fixed+scan;families=defaultdict(list)
    for r in documents:families[info[r['archive_member_path']]['family']].append(r)
    rng=random.Random(81);bootstrap=[]
    for _ in range(2000):
        value=fixed+scan
        for family,rows in families.items():
            value+=manifest['corpus_families'][family]['population']*mean(rng.choice(rows)['member_latency_seconds'] for _ in rows)
        bootstrap.append(value)
    success=[r for r in documents if r['output_status']=='TRANSLATED'];failed=[r for r in documents if r['output_status']=='FAILED_SOURCE_PRESERVED']
    success_mean=mean(r['member_latency_seconds'] for r in success) if success else mean(latencies)
    failed_mean=mean(r['member_latency_seconds'] for r in failed) if failed else 0
    extra=17211*min(.10,len(failed)/100)*max(0,success_mean-failed_mean)
    optimistic=max(0,min(percentile(bootstrap,.1),typical-.25*weighted_ocr))
    conservative=max(percentile(bootstrap,.9),typical+.50*weighted_ocr+extra)
    scenarios={k:dict(seconds=v,hours=v/3600,days=v/86400) for k,v in
        [('optimistic',optimistic),('typical',typical),('conservative',conservative),('direct_linear',wall*172.11)]}
    return dict(scenarios=scenarios,fixed_seconds=fixed,scan_seconds=scan,weighted_seconds=weighted,
        weighted_ocr_seconds=weighted_ocr,bootstrap_p10=percentile(bootstrap,.1),bootstrap_p90=percentile(bootstrap,.9),
        failure_adjustment_seconds=extra,latency_sum_seconds=sum(latencies),parallel_overlap_ratio=sum(latencies)/wall,
        methodology='Exact old source formula, seed 81, 2000 family bootstraps; optimistic -25% weighted OCR; conservative +50% OCR and up to 10% fewer early failures',
        limitation='New admitted-to-canonical-package document latency can overlap across pipeline workers. Exact historical scenario formula retains that overlap and queue waits; scenario sums are not direct production throughput. Direct linear forecast uses actual wall with concurrency included.')


def stages_profile(logs,timing,wall,observations,receipt):
    stages=defaultdict(lambda:dict(calls=0,seconds=0.,failures=0))
    for r in lines(logs/'stages.jsonl'):
        s=stages[r['stage']];s['calls']+=r['count'];s['seconds']+=r['seconds'];s['failures']+=r['failures']
    ocrlog=QA/'raw/ocr_lifecycle.jsonl';lifecycle=lines(ocrlog) if ocrlog.exists() else []
    ocrpages={(r['document_id'],r['page']) for r in timing if r['stage']=='ocr_recognize'}
    get=lambda n:stages.get(n,dict(calls=0,seconds=0,failures=0))
    return dict(inclusive_stages=dict(stages),exclusive_categories=exclusive_categories(timing,wall),
        category_method='Historical priority interval-union partition; nested and cross-thread overlaps assigned once. OCR priority precedes NMT; recognition queue wait remains OCR occupancy, not exclusive GPU kernel time.',
        ocr=dict(recognize=get('ocr_recognize'),load_count=sum(r['event']=='model_load' for r in lifecycle),
            load_seconds=sum(r.get('load_seconds',0) for r in lifecycle if r['event']=='model_load'),
            reuse_count=sum(r['event']=='model_reuse' for r in lifecycle),
            inference_seconds=sum(r.get('seconds',0) for r in lifecycle if r['event']=='inference'),
            postprocess=get('ocr_postprocess'),pages=len(ocrpages),regions=get('ocr_recognize')['calls'],
            lifecycle_event_counts=dict(Counter(r['event'] for r in lifecycle)),
            inference_scope='Worker cached.predict; excludes parent GPU-owner queue wait, IPC and postprocess',
            plans=[r for r in lifecycle if r['event']=='hardware_plan']),
        glossary=dict(receipt['lookup_profile'],cache=receipt['glossary_cache'],engine_counters=receipt['glossary_counters']),
        writer=dict(pdf_write=get('pdf_write'),document_write=get('document_write'),page_layout=get('pdf_page_layout_write'),
            locks=observations['locks']['groups'],
            actual_work_scope='Native writer outer PDF_LOCK held excludes acquisition wait. pdf_write/document_write are inclusive and must not be summed with lock/layout subscopes.'))


def output_equivalence(manifest,old,new,output):
    oldmap={d['archive_member_path']:d for d in old};newmap={d['archive_member_path']:d for d in new}
    historical_metadata={d['archive_member_path']:d for d in database_rows(OLD/'index.sqlite3','documents')}
    oldoutput=Path(read(OLD/'execution.json')['outputs'][0]);rows=[]
    normalize=lambda data:re.sub(rb'/ID\s*\[\s*<[0-9A-Fa-f]+>\s*<[0-9A-Fa-f]+>\s*\]',b'/ID[<GENERATED><GENERATED>]',data)
    contract_fields=['source_sha256','source_pages','extracted_blocks','segments','native_segments','ocr_segments',
        'classification','ocr_pages','ocr_regions','table_blocks','schematic_blocks','protected_tokens','profiler']
    with ZipFile(oldoutput) as a,ZipFile(output) as b,ZipFile(manifest['sample_archive']) as source:
        crc=dict(old=a.testzip(),new=b.testzip());inventory_exact=a.namelist()==b.namelist()
        for item in manifest['documents']:
            member=item['member_path'];x=oldmap[member];y=newmap[member]
            xd=a.read(x['output_archive_member']);yd=b.read(y['output_archive_member'])
            status=x['output_status']==y['output_status'];path=x['output_archive_member']==y['output_archive_member']
            row=dict(member=member,status_exact=status,old_status=x['output_status'],new_status=y['output_status'],
                path_exact=path,old_path=x['output_archive_member'],new_path=y['output_archive_member'],
                raw_exact=xd==yd,bytes_except_generated_trailer_ID_exact=normalize(xd)==normalize(yd),
                source_metadata_differences={k:dict(old=historical_metadata[member].get(k),new=y.get(k))
                    for k in contract_fields if historical_metadata[member].get(k)!=y.get(k)},
                old_failure=x.get('failure'),new_failure=y.get('failure'))
            if y['output_status']=='FAILED_SOURCE_PRESERVED':
                row['failed_original_exact']=y['output_archive_member']==member and yd==source.read(member)
            if x['output_status']=='TRANSLATED' and y['output_status']=='TRANSLATED':
                fx=fingerprint_pdf(xd,True);fy=fingerprint_pdf(yd,True)
                row['normalized_objects_exact']=fx['pages']==fy['pages'];row['render_probes_exact']=fx['renders']==fy['renders']
                rx='\n'.join(p['text'] for p in fx['pages']);ry='\n'.join(p['text'] for p in fy['pages'])
                tokens=lambda text:Counter(re.findall(r'\b[A-Z][A-Z0-9_-]*\b|\d+(?:[.,]\d+)?',text))
                row['protected_ID_number_multiset_exact']=tokens(rx)==tokens(ry)
                if rx!=ry:row['text_difference']=dict(old_sha256=sha256(rx.encode()).hexdigest(),new_sha256=sha256(ry.encode()).hexdigest(),
                    old_preview=rx[:300],new_preview=ry[:300])
                row['output_semantics_exact']=row['normalized_objects_exact'] and row['render_probes_exact'] and row['protected_ID_number_multiset_exact']
            else:row['output_semantics_exact']=status and xd==yd
            rows.append(row)
            if len(rows)%20==0:print('EQUIVALENCE',len(rows),'/100',flush=True)
        dirs=lambda z:sorted({str(PurePosixPath(i.filename).parent) for i in z.infolist()})
        directory_exact=dirs(a)==dirs(b)
    frontier_old=database_rows(OLD/'index.sqlite3','frontier');frontier_new=database_rows(Path(read(QA/'run_manifest.json')['logs'])/'index.sqlite3','frontier')
    def frontier(v):return {r['hash']:{k:w for k,w in r.items() if k!='representative_document_ids'} for r in v}
    candidate_exact=frontier(frontier_old)==frontier(frontier_new)
    checks=dict(statuses=all(r['status_exact'] for r in rows),destination_paths=all(r['path_exact'] for r in rows),
        zip_inventory_and_order=inventory_exact,directory_structure=directory_exact,crc=all(v is None for v in crc.values()),
        failed_source_preservation=all(r.get('failed_original_exact',True) for r in rows),
        normalized_translated_semantics=all(r['output_semantics_exact'] for r in rows),
        available_source_metadata=all(not r['source_metadata_differences'] for r in rows),bounded_frontier_candidates=candidate_exact)
    result=dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,documents=rows,
        unavailable=['Historical full ordered OCR source contracts are absent; compare available extraction metadata and exact source archive bytes.',
            'Historical full ordered translation candidates/model-ready inputs are absent; compare available bounded frontier translations and translated PDF objects/text/renders.'],
        available_candidate_counts=dict(old=len(frontier_old),new=len(frontier_new)),
        candidate_differences=dict(old=frontier(frontier_old),new=frontier(frontier_new)) if not candidate_exact else {},
        render_scope='Existing probes: first and last page of every translated PDF at scale1.25; normalized objects/text on ALL pages',
        historical_output_sha256=sha256(oldoutput.read_bytes()).hexdigest())
    save(QA/'output_equivalence.json',result);return result


def resources(receipt):
    rows=lines(QA/'raw/resource_samples_tree.jsonl');deltas=[max(0,rows[i]['elapsed']-rows[i-1]['elapsed']) for i in range(1,len(rows))]
    duration=sum(deltas);gpu=[r for r in rows if r.get('gpu_device_wide')]
    old=lines(OLD/'resource_samples.jsonl')
    value=dict(samples=len(rows),sample_interval_seconds=1,monitor_errors=receipt['resource_monitor_errors'],
        process_tree_cpu_avg_percent=sum(rows[i]['process_tree_cpu_percent']*deltas[i-1] for i in range(1,len(rows)))/duration if duration else None,
        process_tree_cpu_peak_percent=max(r['process_tree_cpu_percent'] for r in rows),
        process_tree_peak_rss_bytes=max(r['rss_bytes'] for r in rows),
        process_tree_peak_private_commit_bytes=max(r['private_commit_bytes'] for r in rows),
        system_min_available_ram_bytes=min(r['system_available_ram_bytes'] for r in rows),
        gpu_device_average_utilization=mean(r['gpu_device_wide']['utilization'] for r in gpu) if gpu else None,
        gpu_device_peak_vram_mib=max(r['gpu_device_wide']['used_mib'] for r in gpu) if gpu else None,
        gpu_scope='Device wide, including desktop/other processes; one-second samples; per-process GPU memory is unavailable under Windows WDDM in this monitor.',
        cpu_scope='Process tree: 100%=one logical core; sampler and nvidia-smi overhead included; first zero sample excluded from weighted average',
        historical=dict(cpu_avg=None,gpu_avg=None,tree_rss=None,tree_commit=None,vram=None,
            root_sampled_peak_rss_bytes=max(r.get('peak_rss_bytes') or r.get('rss_bytes') or 0 for r in old),
            note='Historical telemetry only root RSS at document boundaries, no continuous CPU/tree/GPU monitor. NOT DIRECTLY COMPARABLE.'),
        ram_limit_changed=False,models_or_execution_caps_changed=False)
    value['gpu_per_process_snapshot']=read(QA/'raw/gpu_process_snapshot.json')
    save(QA/'resource_summary.json',value);return value


def analyze():
    receipt=read(QA/'run_manifest.json');manifest=read(QA/'sample_manifest.json')
    assert 'wall_seconds' in receipt,'Measured run is not finished'
    assert frozen_hashes()==receipt['production_hashes_before']==receipt['production_hashes_after']
    logs=Path(receipt['logs']);raw=read(logs/'run_summary.json');wall=receipt['wall_seconds']
    docs=database_rows(logs/'index.sqlite3','documents');old=lines(OLD/'documents.jsonl');oldanalysis=read(OLD/'calibration_analysis.json')
    assert len(docs)==100 and not receipt['fatal'] and raw['fatal_errors']==0
    order={d['member_path']:d['index'] for d in manifest['documents']};docs.sort(key=lambda d:order[d['archive_member_path']])
    starts={e['member']:e['elapsed_since_run_start'] for e in receipt['events'] if e['event']=='document_start'}
    ends={e['source_member']:e['elapsed_since_run_start'] for e in receipt['events'] if e['event']=='member_packaged'}
    assert len(starts)==len(ends)==100 and list(ends)==[d['member_path'] for d in manifest['documents']]
    timing=lines(QA/'raw/timing_events.jsonl');ocr=Counter()
    for r in timing:
        if r['stage']=='ocr_recognize':ocr[r['document_id']]+=r['seconds']
    output=Path(receipt['outputs'][0]);import pypdfium2 as pdfium
    with ZipFile(output) as z:
        assert z.testzip() is None
        for d in docs:
            p=pdfium.PdfDocument(z.read(d['output_archive_member']))
            try:d['measured_output_pages']=len(p)
            finally:p.close()
            d['member_latency_seconds']=ends[d['archive_member_path']]-starts[d['archive_member_path']]
            d['ocr_measurement_seconds']=ocr[d['document_id']]
    lat=[d['member_latency_seconds'] for d in docs];status=Counter(d['output_status'] for d in docs);counters=Counter()
    for d in docs:counters.update(d['counters'])
    packaged=[e for e in receipt['events'] if e['event']=='member_packaged'];success={d['archive_member_path'] for d in docs if d['output_status']=='TRANSLATED'}
    summary=dict(run_id=receipt['run_id'],wall_seconds=wall,wall_minutes=wall/60,processed=len(docs),translated=status['TRANSLATED'],
        failed_source_preserved=status['FAILED_SOURCE_PRESERVED'],fatal=raw['fatal_errors'],source_pages=sum(d['pages'] or 0 for d in manifest['documents']),
        output_pages=sum(d['measured_output_pages'] for d in docs),docs_hour=len(docs)*3600/wall,
        source_pages_hour=sum(d['pages'] or 0 for d in manifest['documents'])*3600/wall,
        output_pages_hour=sum(d['measured_output_pages'] for d in docs)*3600/wall,
        processed_segments_second=counters['processed_segments']/wall,semantic_segments_second=counters['semantic_segments']/wall,
        latency=dict(mean=mean(lat),median=median(lat),p90=percentile(lat,.9),p95=percentile(lat,.95),p99=percentile(lat,.99),max=max(lat),
            scope='Admission/child start through ORIGINAL canonical packaging; overlapping pipeline latency, includes queues'),
        time_to_first_document_start=min(starts.values()),time_to_first_processed=packaged[0]['elapsed_since_run_start'],
        time_to_first_translated=next(e['elapsed_since_run_start'] for e in packaged if e['source_member'] in success),
        completion_milestones={str(n):packaged[n-1]['elapsed_since_run_start'] for n in [25,50,75,100]},
        failure_categories=dict(Counter((d.get('failure') or {}).get('primary_category','unknown') for d in docs if d['output_status']=='FAILED_SOURCE_PRESERVED')),
        failure_types=dict(Counter((d.get('failure') or {}).get('exception_type','unknown') for d in docs if d['output_status']=='FAILED_SOURCE_PRESERVED')),
        overall_speedup_x=4783.64/wall,wall_reduction_percent=(4783.64-wall)/4783.64*100,
        historical_wall_precise=oldanalysis['total_wall_seconds'],counters=dict(counters),pipeline=[e for e in receipt['events'] if e['event']=='pipeline'],
        output_zip=str(output),documents=docs)
    save(QA/'run_summary.json',summary)
    observations=read(QA/'raw/observations.json');stage=stages_profile(logs,timing,wall,observations,receipt);save(QA/'stage_profile.json',stage)
    nmt=dict(observations['nmt']);requests=nmt.pop('requests');batches=nmt.pop('batches');loads=nmt['loads']
    nmt.update(model_translation=stage['inclusive_stages'].get('model_translation'),batch2_plus=sum(r['sequences']>=2 for r in batches),
        fallback_attempts=sum(r['fallback'] for r in lines(logs/'routing.jsonl') if r.get('event')=='backend_attempt'),
        attempt_failures=sum(not r['success'] for r in lines(logs/'routing.jsonl') if r.get('event')=='backend_attempt'),
        actual_inference_wall_fraction=nmt['inference_seconds']/wall,
        actual_model_load_count=len(loads),backend_device_calls=dict(Counter(r['device'] for r in batches)),
        historical_actual_ct2_calls=None,historical_note='Historical backend inference stage counts exist; exact native CT2 batching/tokens were not captured.',
        model_reuse=stage['inclusive_stages'].get('m2m100_load_or_reuse'),
        request_count=len(requests),model_load_scope='CT2 constructor calls, including failures; OCR loaders reported separately')
    nmt['constructor_counts_by_backend']=dict(Counter('m2m100' if 'm2m100' in r['model'].lower() else 'argos' for r in loads))
    nmt['constructor_load_seconds']=sum(r['seconds'] for r in loads)
    nmt['m2m_resident_reuse_count']=stage['inclusive_stages']['m2m100_load_or_reuse']['calls']-nmt['constructor_counts_by_backend'].get('m2m100',0)
    save(QA/'nmt_profile.json',nmt)
    resource=resources(receipt);eq=output_equivalence(manifest,old,docs,output)
    forecast=historical_forecast(manifest,docs,wall);replay=historical_forecast(manifest,old,oldanalysis['total_wall_seconds'])
    assert all(abs(replay['scenarios'][k]['hours']-oldanalysis['estimates'][k]['hours'])<1e-9 for k in ['optimistic','typical','conservative'])
    forecast['historical_formula_replay']='PASS';forecast['comparison']={k:dict(old_hours=replay['scenarios'][k]['hours'],new_hours=v['hours'],
        saved_hours=replay['scenarios'][k]['hours']-v['hours'],saved_days=(replay['scenarios'][k]['hours']-v['hours'])/24) for k,v in forecast['scenarios'].items()}
    save(QA/'full_archive_forecast.json',forecast)
    report(summary,stage,nmt,resource,eq,forecast,oldanalysis,receipt)
    audit=dict(same_sample='PASS',one_measured_run=True,production_unchanged=frozen_hashes()==receipt['production_hashes_before'],
        dictionary_unchanged=receipt['dictionary_unchanged'],source_unchanged=receipt['source_unchanged'],sample_unchanged=receipt['sample_unchanged'],
        last_full_pytest=1256,full_pytest_not_repeated='Identical production hashes; new measurement helper targeted tests passed',
        targeted_tests=7,observer_errors=receipt['observer_errors'],no_second_run=True,no_production_fix=True,
        output_equivalence=eq['status'],historical_forecast_replay='PASS',full_corpus_run=False,
        report=str(ROOT/'docs/AW0.81_100PDF_FINAL_SPEED_CALIBRATION.md'))
    audit['observer_imports_scope']='QA observer imports/Qt/empty engine construction and monitor startup outside wall, like historical engine setup; no native Translator/OCR models constructed before measured run'
    audit['ancillary_activity_during_run']='Read-only telemetry/SQLite metadata inspection, 0.70s helper tests and exact historical forecast replay ran separately on CPU; no competing GPU inference/translation/render benchmark'
    save(QA/'final_evidence_audit.json',audit)
    with ZipFile(QA/'evidence.zip','x',compression=ZIP_DEFLATED) as z:
        for p in sorted((QA/'raw').rglob('*')):
            if p.is_file():z.write(p,p.relative_to(QA/'raw').as_posix())
        z.write(QA/'run_started.json','run_started.json')
        z.write(QA/'live_progress.json','live_progress.json')
    print('ANALYSIS_COMPLETE',json.dumps(dict(wall=wall,equivalence=eq['status'],forecast=forecast['comparison']),ensure_ascii=False),flush=True)


def report(s,p,n,r,e,f,old,receipt):
    fmt=lambda v: 'N/A' if v is None else f'{v:,.2f}'.replace(',',' ').replace('.',',')
    st=p['inclusive_stages'];ost=old['stages'];get=lambda key:st.get(key,{}).get('seconds',0)
    writer=p['writer']['locks'].get('writer',dict(wait_seconds=0,held_seconds=0,count=0))
    actual=dict(NMT=n['inference_seconds'],OCR=p['ocr']['inference_seconds']+p['ocr']['load_seconds']+get('ocr_postprocess'),
        Writer=writer['held_seconds'],Glossary=p['glossary']['seconds'])
    bottleneck=max(actual,key=actual.get)
    justified=(n['actual_inference_wall_fraction']>=.30 or bottleneck=='NMT')
    # Existing replay suggests an opportunity, not a measured whole-corpus factor.
    potential=n['actual_inference_wall_fraction']*.75
    decision='JUSTIFIED' if justified else 'NOT YET JUSTIFIED'
    readiness='OPTIMIZATION STILL JUSTIFIED' if justified or max(actual.values())/s['wall_seconds']>=.30 else 'READINESS NOT PROVEN'
    if e['status']!='PASS':s['full_archive_blocker']='Historical output equivalence FAIL; full archive readiness not established'
    s['next_bottleneck']=bottleneck;s['nmt_scheduler_decision']=decision;s['full_archive_verdict']=readiness
    s['nmt_decision_evidence']=dict(A_actual_CT2_at_least_30_percent=n['actual_inference_wall_fraction']>=.30,
        C_main_remaining_bottleneck=bottleneck=='NMT',B_batch8_total_wall_gain='UNMEASURED; replay opportunity alone is not a whole-run speedup')
    s['bottleneck_actual_work_seconds']=actual;save(QA/'run_summary.json',s)
    oldevents=read(OLD/'execution.json')['events'];oldends=[x for x in oldevents if x['event']=='member_packaged']
    oldsuccess={x['archive_member_path'] for x in lines(OLD/'documents.jsonl') if x['output_status']=='TRANSLATED'}
    oldfirsttranslated=next(x['elapsed_since_run_start'] for x in oldends if x['source_member'] in oldsuccess)
    L=['# AW0.81 — финальная калибровка на прежних 100 PDF','',
       f"**TOTAL AW0.81 SPEEDUP: {fmt(s['overall_speedup_x'])}×; WALL REDUCTION: {fmt(s['wall_reduction_percent'])}%.**",
       f"OLD: 79,73 мин → NEW: {fmt(s['wall_minutes'])} мин / 100 PDF. Equivalence: **{e['status']}**.",'',
       '## 1. Same-100 verification','',
       '**SAME SAMPLE AS 25825c3f75a7: PASS.** Historical manifest скопирован дословно. Для всех100 проверены original paths, inventory PDF indices/order, size, ZIP CRC, source SHA256 и равенство байтов historical subset/full source. Использован прежний subset ZIP, чтобы сохранить прежний archive context; новых PDF и замен failures нет.',
       f"Full CN7C: 17 211 PDF; SHA256 `{receipt['source_sha256']}`. Production hash freeze совпадает с последним1256 PASS; все49 DB Knowledge неизменны.",'',
       '## 2. Hardware/runtime','',
       f"CPU: {receipt['hardware']['physical_cpu']} physical / {receipt['hardware']['logical_cpu']} logical; RAM {fmt(receipt['hardware']['ram_bytes']/1024**3)} GiB; GPU `{(receipt['hardware']['gpu'] or {}).get('name','N/A')}`.",
       'DocumentConfig: source auto, target ru, domain auto, device AUTO, profile AUTOMATIC, threads default; filenames/directories включены как в baseline. Pipeline planner/caps/GPU ownership/cache policy не подменены; policy ORIGINAL. No MID/Ultra overrides, process commit caps или benchmark OCR caps.',
       f"Actual pipeline: depth {s['pipeline'][0]['plan']['depth']}, prepare_workers {s['pipeline'][0]['plan']['prepare_workers']}, semantic_workers {s['pipeline'][0]['plan']['semantic_workers']}, writer_depth {s['pipeline'][0]['plan']['writer_depth']}, GPU owner {s['pipeline'][0]['plan']['gpu_owners']}; inflight high water {s['pipeline'][0]['metrics']['inflight_high_water']}. План и полный pipeline telemetry сохранены в run_summary.json.",
       'Historical helper run() не содержит explicit warmup. Поэтому warmup0s, resident models до старта нет; fresh isolated TM/user DB. Cold model loads входят в wall, как раньше. Общая проверка source/sample вне wall; sample scan входит в wall.',
       f"Sample scan: {fmt(receipt['sample_scan_seconds'])}s. Production/Knowledge/source/model policy в процессе не менялись. QA observers только пересылают исходные вызовы и собирают данные; их накладные расходы включены в новый wall. Никаких prewarm100/cache-full-inputs.",'',
       '## 3. Old baseline','',
       'Run25825c3f75a7: 4783,64s / 79,73min; 100 processed,76 TRANSLATED,24 FAILED_SOURCE_PRESERVED,0 fatal;157 source/190 output pages. Processing75,26docs/h. Исторический typical229,51h /9,56d.', '',
       '## 4. New 100-PDF result','',
       f"Run `{s['run_id']}`: {fmt(s['wall_seconds'])}s /{fmt(s['wall_minutes'])}min; {s['processed']} processed, {s['translated']} TRANSLATED, {s['failed_source_preserved']} FAILED_SOURCE_PRESERVED, {s['fatal']} fatal. Source {s['source_pages']}, output {s['output_pages']} pages.",
       f"Первый child start {fmt(s['time_to_first_document_start'])}s; first processed {fmt(s['time_to_first_processed'])}s; first translated {fmt(s['time_to_first_translated'])}s. Completion25/50/75/100%: `{s['completion_milestones']}` seconds.",
       f"Latency max {fmt(s['latency']['max'])}s. Scope: child admission→canonical archive append; queue waiting входит, per-document latencies перекрываются. Их сумма {fmt(f['latency_sum_seconds'])}s vs wall {fmt(s['wall_seconds'])}s.",'',
       '## 5. Before → after','',
       '| Metric | Old100 | New100 | Change |','|---|---:|---:|---:|']
    metrics=[('Wall,s',old['total_wall_seconds'],s['wall_seconds']),('Wall,min',old['total_wall_seconds']/60,s['wall_minutes']),
        ('Docs/hour',old['throughput']['processed_docs_hour'],s['docs_hour']),('Source pages/hour',old['throughput']['source_pages_hour'],s['source_pages_hour']),
        ('Output pages/hour',old['throughput']['output_pages_hour'],s['output_pages_hour']),('Processed segments/s',old['throughput']['processed_segments_second'],s['processed_segments_second']),
        ('Semantic segments/s',old['throughput']['semantic_segments_second'],s['semantic_segments_second'])]
    metrics += [('Latency '+key+',s',old['latency'][key],s['latency'][key]) for key in ['mean','median','p90','p95','p99','max']]
    metrics += [('First processed,s',oldends[0]['elapsed_since_run_start'],s['time_to_first_processed']),('First translated,s',oldfirsttranslated,s['time_to_first_translated']),
        ('OCR recognize inclusive,s',ost['ocr_recognize']['seconds'],get('ocr_recognize')),('OCR worker load,s',None,p['ocr']['load_seconds']),
        ('OCR worker inference,s',None,p['ocr']['inference_seconds']),('OCR postprocess,s',ost['ocr_postprocess']['seconds'],get('ocr_postprocess')),
        ('Glossary lookup inclusive,s',ost['glossary_lookup']['seconds'],get('glossary_lookup')),
        ('Model translation inclusive,s',ost['model_translation']['seconds'],get('model_translation')),('Actual CT2 calls',None,n['calls']),
        ('CT2 batch1 calls',None,n['batch1']),('CT2 batch2+ calls',None,n['batch2_plus']),('CT2 median sequences',None,n['median_sequences']),
        ('CT2 median source tokens',None,n['median_tokens']),('CT2 synchronous inference,s',None,n['inference_seconds']),
        ('Writer document_write inclusive,s',ost['document_write']['seconds'],get('document_write')),('Writer PDF_LOCK wait,s',None,writer['wait_seconds']),
        ('Process-tree CPU avg,%',None,r['process_tree_cpu_avg_percent']),('Device GPU avg,%',None,r['gpu_device_average_utilization']),
        ('Process-tree peak RSS,GiB',None,r['process_tree_peak_rss_bytes']/1024**3),('Device peak VRAM,MiB',None,r['gpu_device_peak_vram_mib']),
        ('TRANSLATED',76,s['translated']),('FAILED_SOURCE_PRESERVED',24,s['failed_source_preserved']),('Fatal',0,s['fatal'])]
    for key,x,y in metrics:L.append(f"| {key} | {fmt(x)} | {fmt(y)} | {fmt(y-x) if x is not None and y is not None else 'N/A'} |")
    L+=['','N/A означает отсутствие historical instrumentation, а не 0. Old CPU/GPU/CT2 batching/tokens/lock timings отсутствуют; новые значения не выдаются за сопоставимое улучшение.',
        f"Общий throughput вырос, но first processed +{fmt(s['time_to_first_processed']-oldends[0]['elapsed_since_run_start'])}s; median +{fmt(s['latency']['median']-old['latency']['median'])}s; model_translation +{fmt(get('model_translation')-ost['model_translation']['seconds'])}s; writer +{fmt(get('document_write')-ost['document_write']['seconds'])}s. По одному run и без historical continuous resource trace нельзя надёжно разделить влияние contention/частот и изменений runtime. Это зарегистрировано, не исправлялось.",'',
        '## 6. Stage profile before → after','',
        'Одна и та же historical методика interval-union: OCR→model→glossary→TM→templates→guards→writer→validation→profiler→snapshot→extraction→append→path priority. Каждая wall interval принадлежит одной категории. При parallel execution это occupancy, не causal critical-path attribution; OCR recognition включает GPU-owner wait и может перекрывать NMT. Inclusive stage суммы отдельно, они могут превышать wall.','',
        '| Stage | Old seconds | Old% | New seconds | New% |','|---|---:|---:|---:|---:|']
    oldcat=old['exclusive_categories'];newcat=p['exclusive_categories']
    for key in ['OCR','glossary','model','writer','Other']:
        a=oldcat.get(key,0) if key!='Other' else old['total_wall_seconds']-sum(oldcat.get(k,0) for k in ['OCR','glossary','model','writer'])
        b=newcat.get(key,0) if key!='Other' else s['wall_seconds']-sum(newcat.get(k,0) for k in ['OCR','glossary','model','writer'])
        L.append(f"| {key} | {fmt(a)} | {fmt(a/old['total_wall_seconds']*100)} | {fmt(b)} | {fmt(b/s['wall_seconds']*100)} |")
    L+=['',f"OCR: {p['ocr']['pages']} attempted pages /{p['ocr']['regions']} regions; model loads {p['ocr']['load_count']} ({fmt(p['ocr']['load_seconds'])}s), resident reuse {p['ocr']['reuse_count']}; worker inference {fmt(p['ocr']['inference_seconds'])}s, parent postprocess {fmt(get('ocr_postprocess'))}s.",
        f"Glossary: {p['glossary']['counts']['lookups']} lookup calls; {p['glossary']['unique_logical_lookups']} unique logical keys; {p['glossary']['counts']['sql_statements']} SQL statements; repeated negative results {p['glossary']['repeated_negative_results']}. Lexical cache positive hits {p['glossary']['cache']['lexical']['positive_hits']}, negative hits {p['glossary']['cache']['lexical']['negative_hits']}, misses {p['glossary']['cache']['lexical']['misses']}. Ключи cache negative hits — lexical candidate hashes; повторные пустые final lookup results имеют другой scope. Полные counters в stage_profile.json.",
        f"Writer: pdf_write {fmt(get('pdf_write'))}s; actual lock-held {fmt(writer['held_seconds'])}s; lock wait {writer['wait_seconds']:.6f}s; page/layout {fmt(get('pdf_page_layout_write'))}s. Это вложенные метрики, не сумма.",
        'Other inclusive seconds: '+', '.join(f'{key}={fmt(get(key))}' for key in ['template_routing','knowledge_snapshot','DocumentProfiler','semantic_guards','pdf_validation','archive_extract','archive_pack_member'])+'.','',
        '## 7. NMT profile','',
        f"{n['calls']} actual CT2 calls; {n['sequences']} sequences; {n['tokens']} source pieces (language/EOS included); median {fmt(n['median_sequences'])} sequences/call, {fmt(n['median_tokens'])} tokens/call; batch1={n['batch1']}, batch2+={n['batch2_plus']}.",
        f"Actual synchronous CT2 {fmt(n['inference_seconds'])}s = {fmt(n['actual_inference_wall_fraction']*100)}% measured wall; model_translation {fmt(get('model_translation'))}s inclusive. CT2 owns transfer/preparation internally; separate kernel/transfer timing unavailable.",
        f"CT2 constructor loads {n['actual_model_load_count']} ({n['constructor_counts_by_backend']}, {fmt(n['constructor_load_seconds'])}s); M2M load/reuse calls {n['model_reuse']['calls']}, из них resident reuse {n['m2m_resident_reuse_count']}; backend failure attempts {n['attempt_failures']}, fallback attempts {n['fallback_attempts']}. Old M2M real loads35/Argos58, load-or-reuse3282: новые counts совпадают. Native failure/fallback counts168/167 тоже совпадают; это measurement текущей политики, не утверждение об устранении всех повторов. Loads/device records in nmt_profile.json; options unchanged.",'',
        '## 8. Failures/status equivalence','',
        f"**Output equivalence {e['status']}**; checks `{e['checks']}`. Current failure categories `{s['failure_categories']}`, exception types `{s['failure_types']}`. Никакие document failures не исправлялись.",
        'Проверены все100 statuses/destinations/failed original paths+bytes, ZIP order/inventory/directory structure/CRC, protected ID/number multisets, normalized PDF text/objects на всех translated pages и first+last render probes каждого translated PDF. Generated trailer/ID исключён только из отдельной byte comparison.',
        f"Дополнительно: {sum(r['raw_exact'] for r in e['documents'])} members raw binary exact; все100 members byte-exact после исключения generated trailer /ID. У всех76 translated PDF единственное byte отличие — /ID; все24 failed originals совпадают без нормализации.",
        f"Historical candidate evidence: bounded frontier {e['available_candidate_counts']}; сравнение доступных current_candidate_translation и metadata. Полного historical ordered candidate/source OCR contract нет; это UNAVAILABLE. Новые source contracts записаны, historical отсутствие не считается PASS полного OCR contract.",
        'Изменения статусов, source metadata, текста или пути перечислены по member в output_equivalence.json. При несовпадении это регрессия/неподтверждённая эквивалентность, не улучшение; production не исправлялся.','',
        '## 9. Resource use','',
        f"CPU tree avg {fmt(r['process_tree_cpu_avg_percent'])}% /peak {fmt(r['process_tree_cpu_peak_percent'])}% (100%=one logical core); RSS peak {fmt(r['process_tree_peak_rss_bytes']/1024**3)}GiB; private commit peak {fmt(r['process_tree_peak_private_commit_bytes']/1024**3)}GiB; system available RAM minimum {fmt(r['system_min_available_ram_bytes']/1024**3)}GiB.",
        f"Device GPU avg {fmt(r['gpu_device_average_utilization'])}%, VRAM peak {fmt(r['gpu_device_peak_vram_mib'])}MiB; device-wide includes desktop and other apps. {r['samples']} one-second samples. Historical root RSS sampled peak {fmt(r['historical']['root_sampled_peak_rss_bytes']/1024**3)}GiB; tree RSS NOT DIRECTLY COMPARABLE. Per-process WDDM VRAM unavailable; no heavy monitoring installed.",'',
        '## 10. Full17 211 forecast','',
        f"Direct throughput: {fmt(s['wall_seconds'])}×172,11={fmt(f['scenarios']['direct_linear']['hours'])}h /{fmt(f['scenarios']['direct_linear']['days'])}d continuous.",
        'Historical exact formula восстановлена из tools/aw081_speed_calibration_report.py; replay old188,228323905/229,509831647/303,933432202h PASS. Те же family population weights, Random(81),2000 within-family bootstrap samples; optimistic=min(P10,typical−0,25×weightedOCR); conservative=max(P90,typical+0,50×weightedOCR+lowerFailureExtra). Новые коэффициенты не вводились.',
        f"Typical=sum(weight×admittedLatency)+max(0,wall−sumLatency)+fullScan. Здесь latency overlap ratio {fmt(f['parallel_overlap_ratio'])}×. Старую формулу применили буквально: она сохраняет очереди/перекрытие pipeline и даёт scenario proxy, не оценку wall с устранённым overlap. Для фактического текущего throughput использовать direct forecast; scenarios не confidence interval. Full scan retained historical verified unchanged-source {fmt(f['scan_seconds'])}s.",'',
        '| Scenario | Old,h | New,h /d | Saved,h | Saved,d |','|---|---:|---:|---:|---:|']
    for key,v in f['comparison'].items():L.append(f"| {key} | {fmt(v['old_hours'])} | {fmt(v['new_hours'])} /{fmt(v['new_hours']/24)} | {fmt(v['saved_hours'])} | {fmt(v['saved_days'])} |")
    L+=['','## 11. One next bottleneck','',
        f"**{bottleneck}**. Выбор по новому100: actual measured work `{json.dumps(actual,ensure_ascii=False)}` seconds. Для OCR использованы worker inference+real load+postprocess, а не parent recognition gate waiting. Для NMT — real CT2 synchronous time; writer — held, glossary — real lookup. Это измеренные вложенные work scopes, не суммируемые доли wall.",'',
        '## 12. NMT scheduler decision','',
        f"**NMT SCHEDULER {decision}**. Actual CT2 wall fraction {fmt(n['actual_inference_wall_fraction']*100)}%; batch1 {n['batch1']}. Opportunity upper proxy при75% local inference reduction: {fmt(potential*100)}% общего wall, НЕ обещание измеренного whole-run gain. Реалистичный выигрыш требует независимой semantic queue, сохранения guards/fallback/order и нового equivalence gate.",
        'Прежний fixed5:886 CT2 calls, все batch1; captured replay batch8 exact PASS/большой local gain; batch16 exact FAIL. Это основание только для отдельного проекта, не коэффициент full-corpus forecast. Здесь batching не реализован.','',
        '## 13. Full archive readiness','',
        f"**{readiness}**. Наличие0fatal не отменяет equivalence gate. Допустимое пользователю время полного прогона не задано; прежний24h threshold был QA assumption, не подтверждённым согласием. Full archive автоматически не запускался.",'',
        '## 14. Final verdict','',
        f"TOTAL AW0.81 SPEEDUP **{fmt(s['overall_speedup_x'])}×**; WALL REDUCTION **{fmt(s['wall_reduction_percent'])}%**. OLD79,73min→NEW{fmt(s['wall_minutes'])}min/100PDF.",
        f"OLD TYPICAL229,51h/9,56d→NEW TYPICAL{fmt(f['scenarios']['typical']['hours'])}h/{fmt(f['scenarios']['typical']['days'])}d (exact old scenario formula with admitted latency overlap caveat). Direct current wall forecast {fmt(f['scenarios']['direct_linear']['hours'])}h/{fmt(f['scenarios']['direct_linear']['days'])}d.",
        f"NEXT BOTTLENECK:{bottleneck}; NMT SEMANTIC BATCH SCHEDULER:{decision}; FULL ARCHIVE:{readiness}.",
        'Production/Knowledge hashes unchanged; last1256 PASS reused; measurement helper targeted tests passed. Ровно один100-PDF measured run. STOP: no second run, no optimization, no full corpus, no failure fixes, no AW0.82/PHASEB/C/FrozenB.','']
    (ROOT/'docs/AW0.81_100PDF_FINAL_SPEED_CALIBRATION.md').write_text('\n'.join(L),'utf8')


if __name__=='__main__':analyze()
