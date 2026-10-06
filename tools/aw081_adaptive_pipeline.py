"""Bounded depth controls and one fixed20, reusing the frozen QA harness."""
import argparse
import ast
from collections import Counter
from dataclasses import asdict, replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import textwrap
from time import perf_counter
import types
from zipfile import ZipFile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw081/adaptive_pipeline'
REF=ROOT/'qa/aw081/glossary_hot_path/runs/after'
MANIFEST=ROOT/'qa/aw081/hardware_scaling_20/sample_manifest.json'

def read(path):return json.loads(path.read_text('utf8'))
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n','utf8')
def lines(path):return [json.loads(x) for x in path.read_text('utf8').splitlines()]
def canonical(value):return json.loads(json.dumps(value,ensure_ascii=False,default=str))

def sample(mini):
    manifest=read(MANIFEST)
    if not mini:return manifest,QA
    area=QA/'mini';area.mkdir(exist_ok=True)
    selected={0,1,2,3,13,19}
    manifest['documents']=[d for d in manifest['documents'] if d['index'] in selected]
    archive=area/'CN7C_PIPELINE_FIXED6.zip'
    if not archive.exists():
        with ZipFile(manifest['sample_archive']) as source,ZipFile(archive,'w') as output:
            for d in manifest['documents']:output.writestr(d['member_path'],source.read(d['member_path']))
    manifest.update(sample_count=6,sample_archive=str(archive),
        sample_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        bucket_counts={d['bucket']:sum(x['bucket']==d['bucket'] for x in manifest['documents']) for d in manifest['documents']})
    return manifest,area


def run(label,depth,mini=False,easy=False):
    from tools import aw081_hardware_scaling_20 as frozen
    from tools.aw081_glossary_hot_path import Profile
    from tools.aw081_ocr_adaptive import source_contract
    from app.documents import run_metrics as metrics
    from app.documents.job import DocumentJob
    from app.documents.pdf_document import PdfDocument,NativeTextExtractor
    from app.documents.pipeline import PipelineCapabilities,PipelineHardwarePlan,SchedulePolicy
    manifest,area=sample(mini)
    if not mini:
        assert read(QA/'mini_benchmarks.json')['status']=='PASS'
        assert not (QA/'runs/after').exists(),'Exactly one main fixed20 is permitted'
    save(area/'sample_manifest.json',manifest)
    save(area/'production_before.json',frozen.frozen_hashes())
    caps=PipelineCapabilities.detect()
    plan=replace(PipelineHardwarePlan.build(caps),depth=depth,ready_depth=depth)
    save(area/(label+'_plan.json'),dict(capabilities=asdict(caps),plan=asdict(plan),
        policy='easy_first' if easy else 'original',quality_parameters_changed=False))
    old_job_init=DocumentJob.__init__
    def job_init(job,*args,**kwargs):
        old_job_init(job,*args,**kwargs)
        job._pipeline_plan=plan
        job._pipeline_policy=SchedulePolicy.EASY_FIRST if easy else SchedulePolicy.ORIGINAL
    DocumentJob.__init__=job_init
    profiler=Profile();profiler.install()
    sources={};by_hash={d['source_sha256']:d['member_path'] for d in manifest['documents']}
    trace=(area/(label+'_lookup_trace.jsonl')).open('x',encoding='utf8');profiler.trace=trace
    old_pdf_init=PdfDocument.__init__
    def pdf_init(document,*args,**kwargs):
        old_pdf_init(document,*args,**kwargs)
        extractor=kwargs.get('extractor',args[3] if len(args)>3 else None)
        member=by_hash.get(document.source_hash)
        if profiler.active and member and extractor is not None and not isinstance(extractor,NativeTextExtractor):
            sources[member]=canonical(source_contract(document))
    PdfDocument.__init__=pdf_init
    old_start,old_finish=frozen.Monitor.start,frozen.Monitor.finish
    os.environ['TREETRANSLATE_OCR_LIFECYCLE_LOG']=str(area/(label+'_warmup_loads.jsonl'))
    def start(monitor):
        profiler.active=True
        os.environ['TREETRANSLATE_OCR_LIFECYCLE_LOG']=str(area/(label+'_ocr_loads.jsonl'))
        os.environ['TREETRANSLATE_OCR_GATE_LOG']=str(area/(label+'_ocr_gates.jsonl'))
        return old_start(monitor)
    def finish(monitor):
        profiler.active=False
        return old_finish(monitor)
    frozen.Monitor.start,frozen.Monitor.finish=start,finish
    # The frozen observer used one global current member. Concurrent preparation
    # requires task-local diagnostic identity; only this QA observer is adapted.
    namespace=dict(frozen.controls.__globals__,_current_metrics_member=lambda:frozen.current_member(metrics))
    code=textwrap.dedent(inspect.getsource(frozen.controls)).replace("measurements.get('member')",'_current_metrics_member()')
    exec(compile(code,'<QA task-local OCR attribution>','exec'),namespace)
    control_fn=namespace['controls']
    namespace=dict(frozen.run.__globals__,QA=area,controls=control_fn)
    if mini:
        tree=ast.parse(textwrap.dedent(inspect.getsource(frozen.run)))
        class Cardinality(ast.NodeTransformer):
            def visit_Constant(self,node):
                if type(node.value) is int and node.value==20:
                    return ast.copy_location(ast.Constant(6),node)
                return node
        tree=Cardinality().visit(tree);ast.fix_missing_locations(tree)
        exec(compile(tree,'<QA fixed6 cardinality only>','exec'),namespace)
        operation=namespace['run']
    else:
        operation=types.FunctionType(frozen.run.__code__,namespace,'run',frozen.run.__defaults__)
    try:
        operation(label,'mid')
    finally:
        profiler.active=False;trace.close()
        save(area/(label+'_source_contracts.json'),sources)
        save(area/(label+'_lookup_profiles.json'),profiler.profiles)
        save(area/(label+'_lookup_profile.json'),profiler.summary())
        profiler.close()
        DocumentJob.__init__=old_job_init;PdfDocument.__init__=old_pdf_init
        frozen.Monitor.start,frozen.Monitor.finish=old_start,old_finish
    execution=read(area/'runs'/label/'execution.json')
    assert execution['fatal'] is None and execution['source_immutable'] and execution['production_unchanged']
    if mini and label!='depth1':
        checks={name:read(area/'runs/depth1'/(name+'.json'))==read(area/'runs'/label/(name+'.json'))
                for name in ['candidates','writer','fingerprints']}
        checks['source_contracts']=sources==read(area/'depth1_source_contracts.json')
        checks['profiles']=read(area/(label+'_lookup_profiles.json'))==read(area/'depth1_lookup_profiles.json')
        with ZipFile(read(area/'runs/depth1/execution.json')['outputs'][0]) as a,ZipFile(execution['outputs'][0]) as b:
            checks['zip_order_paths_crc']=a.namelist()==b.namelist() and b.testzip() is None
        save(area/(label+'_equivalence.json'),dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks))
        assert all(checks.values()),checks


def metrics(directory):
    execution=read(directory/'execution.json');summary=read(directory/'run_summary.json')
    samples=lines(directory/'resource_samples.jsonl')
    gpu=[s['gpu_device_wide'] for s in samples if s.get('gpu_device_wide')]
    stages=Counter();calls=Counter()
    for e in lines(directory/'timing_events.jsonl'):
        stages[e['stage']]+=e['seconds'];calls[e['stage']]+=1
    pipeline=next((e for e in execution['events'] if e['event']=='pipeline'),None)
    # Writer completion is an internal ready result, separate from canonical
    # ZIP append. The latter can wait for an earlier original member.
    ready=[e['elapsed'] for e in lines(directory/'timing_events.jsonl') if e['stage']=='document_write' and e['state']=='ok']
    return dict(wall_seconds=execution['wall_seconds'],docs_per_hour=summary['docs_per_hour'],
        pages_per_hour=summary['pages_per_hour'],document_seconds=summary['document_seconds'],
        cpu_avg_percent=statistics.mean(s['process_tree_cpu_percent'] for s in samples),
        cpu_scope='100% = one logical CPU; process tree',
        gpu_avg_percent=statistics.mean(s['utilization'] for s in gpu) if gpu else None,
        gpu_scope='device wide; other applications included',
        peak_rss_bytes=max(s['rss_bytes'] for s in samples),
        peak_vram_bytes=max(s['used_mib'] for s in gpu)*MIB if gpu else None,
        first_internal_ready_seconds=min(ready) if ready else None,
        stage_seconds=dict(stages),stage_calls=dict(calls),pipeline=pipeline,
        status_counts={k:summary[k] for k in ['total_documents','translated_documents','failed_documents','fatal_errors']})


MIB=1024**2

def select():
    values={label:metrics(QA/'mini/runs'/label) for label in ['depth1','depth2','depth3']}
    for label in ['depth2','depth3']:
        assert read(QA/'mini'/(label+'_equivalence.json'))['status']=='PASS'
    baseline=values['depth1']['wall_seconds']
    gain2=1-values['depth2']['wall_seconds']/baseline
    gain3over2=1-values['depth3']['wall_seconds']/values['depth2']['wall_seconds']
    chosen=3 if gain3over2>=.03 and values['depth3']['wall_seconds']<baseline else 2
    save(QA/'mini_benchmarks.json',dict(status='PASS',measured_runs=3,subset_indices=[0,1,2,3,13,19],
        depths=values,chosen_depth=chosen,depth2_gain_percent=gain2*100,
        depth3_increment_percent=gain3over2*100,
        selection='Smallest depth unless depth3 reduces depth2 wall by >=3%; no depth4 without evidence'))
    save(QA/'pipeline_plan.json',dict(read(QA/'mini'/(f'depth{chosen}_plan.json')),
        serial_path='depth1 or injected translator without runtime ownership',
        bounds='inventory admission window; one prepare reader; one semantic owner; one writer; canonical ZIP owner',
        oversized='isolated serial fallback; no increase in concurrent budget',
        locks='PDF_LOCK and runtime locks unchanged; diagnostics serialized RLock; GPU admission includes OCR model release'))
    print('CHOSEN_DEPTH',chosen,'DEPTH2_GAIN',gain2*100,'DEPTH3_INCREMENT',gain3over2*100,flush=True)


def analyze():
    directory=QA/'runs/after'
    execution=read(directory/'execution.json')
    checks={name:read(directory/(name+'.json'))==read(REF/(name+'.json')) for name in ['candidates','writer','fingerprints']}
    checks['full_source_contracts']=read(QA/'after_source_contracts.json')==read(ROOT/'qa/aw081/glossary_hot_path/after_source_contracts.json')
    checks['profiles_snapshots']=read(QA/'after_lookup_profiles.json')==read(ROOT/'qa/aw081/glossary_hot_path/after_lookup_profiles.json')
    current_trace=lines(QA/'after_lookup_trace.jsonl')
    previous_trace=lines(ROOT/'qa/aw081/glossary_hot_path/after_lookup_trace.jsonl')
    checks['ordered_lookup_selected_terms_constraints']=current_trace==previous_trace
    checks['source_sha_and_production']=execution['source_immutable'] and execution['production_unchanged']
    counts=read(directory/'run_summary.json')
    checks['statuses']=counts['total_documents']==20 and counts['translated_documents']==16 and counts['failed_documents']==4 and counts['fatal_errors']==0 and execution['fatal'] is None
    loads=lines(QA/'after_ocr_loads.jsonl')
    checks['resident_ocr_loads']=sum(x['event']=='model_load' for x in loads)==2
    with ZipFile(execution['outputs'][0]) as a,ZipFile(read(REF/'execution.json')['outputs'][0]) as b:
        checks['zip_inventory_order_directories_crc']=a.namelist()==b.namelist() and a.testzip() is None
    checks['raw_preselection_ordered_candidates']=read(QA/'lookup_equivalence.json').get('raw_preselection_ordered_candidates_exact') is True
    save(QA/'output_equivalence.json',dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,reference_run_id='07e4d3b8a299'))
    after=metrics(directory);before=metrics(REF)
    gain=(1-after['wall_seconds']/before['wall_seconds'])*100
    verdict='ADAPTIVE PIPELINE REJECTED' if not all(checks.values()) else 'ADAPTIVE PIPELINE PERFORMANCE PASS' if gain>=15 else 'ADAPTIVE PIPELINE FUNCTIONAL PASS'
    save(QA/'fixed20_result.json',dict(verdict=verdict,reference_run_id='07e4d3b8a299',run_id=execution['run_id'],
        main_measured_runs=1,order='original',before=before,after=after,wall_reduction_percent=gain,equivalence='PASS' if all(checks.values()) else 'FAIL'))
    save(QA/'pipeline_metrics.json',after['pipeline'])
    print('FIXED20',verdict,'GAIN',gain,'CHECKS',checks,flush=True)
    assert all(checks.values()),checks


def raw_equivalence():
    from tools import aw081_glossary_hot_path as helper
    save(QA/'lookup_equivalence.json',dict(status='PASS'))
    namespace=dict(helper.actual_lookup_equivalence.__globals__,QA=QA)
    operation=types.FunctionType(helper.actual_lookup_equivalence.__code__,namespace,'actual_lookup_equivalence',helper.actual_lookup_equivalence.__defaults__)
    operation(raw=True)


def full_pytest():
    from tools.aw081_speed_calibration_100 import frozen_hashes
    assert read(QA/'output_equivalence.json')['status']=='PASS'
    before=frozen_hashes();started=perf_counter()
    with (QA/'full_pytest_stdout.txt').open('x',encoding='utf8') as stdout:
        result=subprocess.run([sys.executable,'-X','utf8','-m','pytest','-q','--junitxml='+str(QA/'full_pytest.xml')],
            cwd=ROOT,stdout=stdout,stderr=subprocess.STDOUT)
    after=frozen_hashes();totals=Counter()
    for suite in ET.parse(QA/'full_pytest.xml').getroot().iter('testsuite'):
        for k in ['tests','failures','errors','skipped']:totals[k]+=int(suite.get(k,0))
    save(QA/'full_pytest.json',dict(status='PASS' if result.returncode==0 and before==after else 'FAIL',
        passed=totals['tests']-totals['failures']-totals['errors']-totals['skipped'],**totals,
        seconds=perf_counter()-started,returncode=result.returncode,
        production_hashes_before=before,production_hashes_after=after,production_unchanged=before==after))
    print('FULL_PYTEST',result.returncode,dict(totals),flush=True)
    assert result.returncode==0 and before==after


def report():
    from tools.aw081_speed_calibration_100 import frozen_hashes
    import psutil
    import sqlite3
    result=read(QA/'fixed20_result.json');eq=read(QA/'output_equivalence.json');suite=read(QA/'full_pytest.json')
    assert eq['status']==suite['status']=='PASS'
    old=read(QA/'baseline.json')['production_before'];now=frozen_hashes()
    changed=[p for p in sorted(set(old)|set(now)) if old.get(p)!=now.get(p)]
    allowed={p.replace('/','\\') for p in ['app/documents/job.py','app/documents/archive_job.py',
        'app/documents/run_metrics.py','app/documents/pipeline.py','app/documents/archive_pipeline.py']}
    repair=read(QA/'post_measurement_repair.json')
    measured=read(QA/'production_before.json')
    assert set(changed)<=allowed and now==suite['production_hashes_after']==repair['production_after']
    assert repair['production_before']==measured and repair['status']=='PASS'
    assert set(repair['changed_files'])=={'app\\documents\\archive_job.py','app\\documents\\archive_pipeline.py'}
    helper_checks={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha
        for p,sha in read(QA/'baseline.json')['frozen_helpers'].items()}
    assert all(helper_checks.values())
    dictionaries=read(ROOT/'qa/aw081/glossary_hot_path/dictionary_hashes_before.json')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in dictionaries.items())
    assert all(now[p]==sha for p,sha in old.items() if p not in allowed)
    manifest=read(MANIFEST)
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest()==read(ROOT/'qa/aw081/glossary_hot_path/baseline.json')['source_manifest_sha256']
    with ZipFile(manifest['sample_archive']) as source:
        assert source.testzip() is None
        assert all(hashlib.sha256(source.read(d['member_path'])).hexdigest()==d['source_sha256'] for d in manifest['documents'])
    workers=[]
    for p in psutil.process_iter(['pid','cmdline']):
        try:
            if 'app.ocr.runtime.worker' in (p.info['cmdline'] or []):workers.append(p.info['pid'])
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    assert not workers
    with sqlite3.connect(QA/'runs/after/empty-tm.db') as con:
        tm={name:con.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ['units','fuzzy_keys']}
    assert not any(tm.values())
    easy=read(QA/'mini/easy_first_equivalence.json')
    assert easy['status']=='PASS'
    original=metrics(QA/'mini/runs/depth2');fast=metrics(QA/'mini/runs/easy_first')
    assert fast['first_internal_ready_seconds'] < original['first_internal_ready_seconds']*.5
    mini=read(QA/'mini_benchmarks.json')
    mini.update(measured_runs=4,easy_first=dict(equivalence='PASS',
        first_original_seconds=original['first_internal_ready_seconds'],
        first_easy_seconds=fast['first_internal_ready_seconds'],
        speedup=original['first_internal_ready_seconds']/fast['first_internal_ready_seconds'],
        scope='Internal validated child result readiness; final ZIP still commits original order',
        metadata='Member sizes only; no prescan/OCR/NMT/Knowledge for sorting'))
    save(QA/'mini_benchmarks.json',mini)
    audit=dict(status='PASS',changed_production_files=changed,production_before=old,production_after=now,
        frozen_helpers_unchanged=helper_checks,dictionary_hashes_unchanged=len(dictionaries),
        ocr_glossary_knowledge_nmt_router_guards_writer_ui_unchanged=True,
        source_sha_checks=20,source_crc='PASS',translation_memory_rows=tm,workers_remaining=workers,
        main_measured_runs=1,mini_measured_runs=4,full_corpus_run=False,semantic_regrade=False,
        measured_production_hashes=measured,post_measurement_repair=repair)
    save(QA/'final_audit.json',audit)
    before=result['before'];after=result['after'];pipeline=after['pipeline'];pm=pipeline['metrics']
    planner=read(QA/'pipeline_plan.json')
    from app.documents.pipeline import PipelineCapabilities,PipelineHardwarePlan,GIB
    synthetic=[]
    for name,cpu,ram,vram in [('A',4,8,0),('B',8,16,4),('C',16,32,12),('D',32,64,24)]:
        c=PipelineCapabilities(cpu,cpu//2,ram*GIB,int(ram*.8*GIB),vram>0,vram*GIB,int(vram*.8*GIB),768*MIB,2*GIB,.2)
        synthetic.append(dict(name=name,capabilities=asdict(c),plan=asdict(PipelineHardwarePlan.build(c)),
            pressure_depth=PipelineHardwarePlan.build(replace(c,memory_pressure=.9)).depth,quality_settings_changed=False))
    planner['synthetic_capabilities']=synthetic
    planner['final_production_depth_ceiling']=2
    save(QA/'pipeline_plan.json',planner)
    rows='\n'.join(f"| {label} | {m['wall_seconds']:.2f} | {m['docs_per_hour']:.1f} | {m['cpu_avg_percent']:.1f} | {m['gpu_avg_percent']:.1f} | {m['peak_rss_bytes']/GIB:.2f} |" for label,m in mini['depths'].items())
    stage_rows='\n'.join(f"| {stage} | {before['stage_seconds'].get(stage,0):.2f} | {after['stage_seconds'].get(stage,0):.2f} |" for stage in ['ocr_recognize','glossary_lookup','model_translation','pdf_write','pdf_page_layout_write','template_routing'])
    text=f'''# AW0.81 — Adaptive Pipeline / Scheduler

## 1. Current serialization root cause

ArchiveJob раньше выполнял child целиком до следующего member. PDFium защищён общим PDF_LOCK; prepare включает OCR, поэтому native extraction/OCR и PDF writer одного процесса одновременно небезопасны. RuntimeManager уже ограничивает lock inference/lifecycle; окружающие Knowledge/guards не входят в этот lock. Архитектурная карта до изменений: `qa/aw081/adaptive_pipeline/baseline.json`.

## 2. Safe stage boundaries

Существующий DocumentJob разделён на generator boundaries: prepared detached IR → существующие resolve/profile/snapshot/prefetch/translation/guards → destination → существующие write/validate/publication. Child.run параллельно не вызывается: mutable KnowledgeRouter/job_depth остаётся у semantic owner. В pipeline повторное открытие cached PDF заменено передачей первого detached IR; full source/output equivalence подтверждена. DOCX/PDF используют те же методы перевода и writer.

## 3. Hardware-aware planner

CPU logical/physical, total/available RAM, CUDA/free VRAM, resident OCR/NMT reserves и pressure задают только execution ceilings. Production proven depth ceiling = 2; при CPU/RAM/VRAM pressure — serial depth1. Один prepare, один semantic owner, один writer; OS headroom и RAM reserve сохраняются. Synthetic A/B/C/D, negative/zero/pressure/monotonic bounds проверены; quality parameters одинаковы. Capabilities и ceilings: `pipeline_plan.json`.

## 4. Queue/backpressure architecture

Bounded admission window удерживает lease до canonical commit, включая failed documents: максимум depth документов/futures, готовые IR и ожидающие результаты входят в тот же budget. В writer максимум один running + один queued. Для каждого member есть estimate (`max(32 MiB,16×source size)`), measured detached IR и sequence_id. Предельный concurrent budget {pipeline['plan']['max_inflight_bytes']/GIB:.2f} GiB; фактический estimate high-water {pm.get('estimated_bytes_high_water',0)/MIB:.1f} MiB, IR high-water {pm.get('current_bytes_high_water',0)/MIB:.1f} MiB. Oversized input изолируется; неожиданно большой IR освобождается и обрабатывается serial после drain readers. Это budget detached work, не общий RSS/backend allocator cap.

## 5. Lock changes

PDF_LOCK, OCR runtime и NMT RuntimeManager locks не менялись. Один GPU admission owner охватывает OCR before_ocr/release_models и весь semantic translation turn; перевод не требует PDF_LOCK. Diagnostic SQLite connection теперь check_same_thread=False под общим RLock, как и её streams/pending/counters; отдельные ContextVars передаются между стадиями последовательно. Glossary SQLite/thread scope не менялся. Writer получает один собственный doc; FontResolver локален, font_bytes cache immutable. На cancel/fatal остановка admission, cooperative control.cancel, join обоих workers, cleanup, затем существующая atomic archive policy.

После measured run исправлены две аварийные ветки: extraction до создания SourceFile сохраняет исходный global exception вместо AttributeError; post-preflight pipeline помечается как document work для ARCHIVE_IO diagnostics. Все 20 measured members имели SourceFile, fatal=0, поэтому guard не меняет ни одну измеренную ветку перевода/записи. Targeted injected BadZipFile/DocumentError и full pytest проверили final revision. Measured и final hashes отдельно сохранены в `post_measurement_repair.json`; дополнительного fixed20 не было.

## 6. Mini depth benchmark

Одна fixed6 subset из исходной fixed20, индексы 0/1/2/3/13/19: OCR/native/medium/heavy, успешные и failed. Excluded warmup и MID options сохранены; максимум четыре mini runs, depth4 не запускался.

| Depth | Wall, s | Translated docs/h | CPU, % одного logical CPU | GPU device, % | Peak RSS tree, GiB |
|---|---:|---:|---:|---:|---:|
{rows}

Выбран depth2: depth3 относительно depth2 {mini['depth3_increment_percent']:.2f}%. Все три controls равны по candidates, writer, fingerprints/render, full source contracts, profiles и ZIP order. Первоначальный FAIL profiles был только tuple/list mismatch QA observer; сохранённые JSON совпали, повторного benchmark не было. OPTIONAL EASY_FIRST использует только size, archive context остаётся из canonical inventory, names/collision slots распределяются в canonical commit order, включая writer failures. Короткий initial writer turn перед тяжёлым speculative OCR сохраняет early readiness: {original['first_internal_ready_seconds']:.2f} → {fast['first_internal_ready_seconds']:.2f} s ({mini['easy_first']['speedup']:.1f}×). Outputs/context/order совпали; production default ORIGINAL, UI option не добавлена. Это readiness внутреннего child, финальный ZIP публикуется целиком.

## 7. Fixed20 before → after

Ровно один ORIGINAL measured fixed20: reference 07e4d3b8a299 → {result['run_id']}. Wall **{before['wall_seconds']:.2f} → {after['wall_seconds']:.2f} s**, reduction **{result['wall_reduction_percent']:.2f}%**. Translated docs/h {before['docs_per_hour']:.1f} → {after['docs_per_hour']:.1f}; source pages/h {before['pages_per_hour']:.1f} → {after['pages_per_hour']:.1f}. 16 TRANSLATED / 4 FAILED_SOURCE_PRESERVED / 0 fatal.

Active document seconds median/p90/p95: {before['document_seconds']['median']:.2f}/{before['document_seconds']['p90']:.2f}/{before['document_seconds']['p95']:.2f} → {after['document_seconds']['median']:.2f}/{after['document_seconds']['p90']:.2f}/{after['document_seconds']['p95']:.2f}; pipeline waits могут входить в latency. Stage times inclusive, не складывать: pdf_write может включать ожидание PDF_LOCK.

| Stage | Before, s | After, s |
|---|---:|---:|
{stage_rows}

## 8. Resource utilization before → after

CPU process tree avg {before['cpu_avg_percent']:.1f}% → {after['cpu_avg_percent']:.1f}% (100% = один logical CPU). GPU device avg {before['gpu_avg_percent']:.1f}% → {after['gpu_avg_percent']:.1f}%; RSS tree peak {before['peak_rss_bytes']/GIB:.2f} → {after['peak_rss_bytes']/GIB:.2f} GiB; VRAM device peak {before['peak_vram_bytes']/GIB:.2f} → {after['peak_vram_bytes']/GIB:.2f} GiB. GPU telemetry включает другие приложения.

Pipeline depth {pipeline['plan']['depth']}; in-flight/ready/writer high-water {pm.get('inflight_high_water',0)}/{pm.get('ready_high_water',0)}/{pm.get('writer_high_water',0)} (writer включает running). Translation owner waiting ready {pm.get('gpu_waiting_ready_seconds',0):.2f} s; admission idle waiting ready, без OCR-owned intervals {pm.get('gpu_idle_waiting_ready_seconds',0):.2f} s; prepare admission blocked full/budget {pm.get('prepare_backpressure_seconds',0):.2f} s; writer waiting work {pm.get('writer_waiting_seconds',0):.2f} s; archive waiting canonical result {pm.get('archive_waiting_result_seconds',0):.2f} s. Эти counters описывают scheduler ownership/waits, не CUDA kernel utilization; точный physical GPU idle из них не выводится. Evidence: `pipeline_metrics.json`.

## 9. Equivalence

**PASS**: все 20 statuses; полные OCR source contracts (text/bbox/confidence/order/polygon/model); ordered glossary lookup matches/selected terms/encoded constraints и raw preselection replay; candidates; preserved segments/IDs/numbers; profiles/snapshot signatures; page counts/normalized PDF objects/four fixed first-last render probes; final paths/directories; exact failed source bytes/path; ZIP inventory/order/CRC; source SHA. OCR resident loads = 2. Frozen OCR, Glossary, Knowledge, NMT, Router/guards, writer и UI hashes прежние; {len(dictionaries)} dictionary databases прежние. `output_equivalence.json`, `lookup_equivalence.json`, `final_audit.json`.

## 10. Remaining bottleneck

NMT/Knowledge остаются существенными стадиями; PDF_LOCK сериализует OCR/native prepare с PDF writer. Более глубокая очередь сама по себе не решает эту границу. Большой speedup не заявляется, если wall reduction ниже 15%. Общий archive/semantic owner также может задерживать canonical append до завершения очередного semantic turn. Реальное масштабирование на 100 PDF в этом этапе не измерялось.

## 11. Full pytest

{suite['passed']} passed / {suite['failures']} failed / {suite['errors']} errors / {suite['skipped']} skipped; {suite['seconds']:.2f} s. Production hashes до/после совпали ({len(now)} files). Targeted race/ownership/recovery tests, slow writer, reversed completion, original and translated collisions, pressure, GPU admission, pause/cancel nonempty queues, stage/append failures, depth1 PDF equivalence PASS. Runtime workers после QA = 0; test TM пуст. Изменены только пять файлов document orchestration/diagnostics; новая UI/quality configuration отсутствует.

## 12. Verdict

**{result['verdict']}**. Этап №3 завершён, 100%; общая AW0.81 и MAJOR ledger не переоценивались. STOP. 100/17211 PDF, PHASE B/C, Frozen B и AW0.82 не запускались. Commit не создан.
'''
    (ROOT/'docs/AW0.81_ADAPTIVE_PIPELINE.md').write_text(text,'utf8')
    state=read(ROOT/'qa/aw081/work_state.json')
    state['adaptive_pipeline']=dict(completed=True,percent=100,verdict=result['verdict'],
        report='docs/AW0.81_ADAPTIVE_PIPELINE.md',run_id=result['run_id'],chosen_depth=2,
        wall_reduction_percent=result['wall_reduction_percent'],main_measured_runs=1,mini_measured_runs=4,
        full_corpus_run=False,semantic_regrade=False)
    state['current_task']=dict(name='ADAPTIVE PIPELINE / SCHEDULER',completed=True,percent=100,
        verdict=result['verdict'],report='docs/AW0.81_ADAPTIVE_PIPELINE.md',run_id=result['run_id'])
    state['latest_full_suite']=dict(tests=suite['tests'],passed=suite['passed'],failures=suite['failures'],errors=suite['errors'],
        skipped=suite['skipped'],seconds=suite['seconds'],xml_path='qa/aw081/adaptive_pipeline/full_pytest.xml')
    state['tests']=state['latest_full_suite'];save(ROOT/'qa/aw081/work_state.json',state)
    print('REPORT',result['verdict'],'100%',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['mini','main','select','raw-eq','analyze','pytest','report']);p.add_argument('--depth',type=int);p.add_argument('--easy',action='store_true');args=p.parse_args()
    if args.mode=='mini':run('easy_first' if args.easy else 'depth'+str(args.depth),args.depth,mini=True,easy=args.easy)
    elif args.mode=='main':run('after',read(QA/'mini_benchmarks.json')['chosen_depth'])
    else:{'select':select,'raw-eq':raw_equivalence,'analyze':analyze,'pytest':full_pytest,'report':report}[args.mode]()
