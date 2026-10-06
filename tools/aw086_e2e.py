"""Production DocumentJob E2E capture; validators and publication are unmodified."""
from dataclasses import asdict
from hashlib import sha256
import json
import os
import logging
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw086';QA.mkdir(parents=True,exist_ok=True)
from PySide6.QtWidgets import QApplication
from app.config.logging_config import configure_logging,document_run
from app.engine.factory import create_translation_engine
from app.engine.types import TranslationRequest
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.engine import TranslationMemoryEngine
from app.documents.job import DocumentJob,DocumentConfig
from app.documents.scanner import scan_sources
from app.documents.control import JobControl
from app.documents.pdf_document import PdfDocument
from app.knowledge.profile import DocumentProfiler


def save(name,value):
    (QA/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')


def prepare():
    dev=[
        dict(id='body',texts=['车身维修 车门 铰链 内板'],domain='automotive',branches=['automotive.body.body_repair']),
        dict(id='measurement',texts=['车身尺寸 测量点 投影尺寸 参考平面'],domain='automotive',branches=['automotive.body.body_measurement']),
        dict(id='cooling',texts=['冷却液 散热器 冷却风扇'],domain='automotive',branches=['automotive.cooling']),
        dict(id='engine',texts=['发动机 机油 发动机舱'],domain='automotive',branches=['automotive.engine']),
        dict(id='suspension',texts=['悬架 减震器 副车架'],domain='automotive',branches=['automotive.suspension']),
        dict(id='electrical',texts=['熔断器 线束 电压 接地'],domain='automotive',branches=['automotive.electrical']),
        dict(id='general',texts=['今天的故事提到一个散热器。'],domain='general',branches=[]),
        dict(id='mixed',texts=['冷却液 散热器','线束 电压'],domain='automotive',branches=['automotive.cooling','automotive.electrical']),
    ]
    p=DocumentProfiler();results=[]
    for case in dev:
        result=p.profile('zh','ru',segments=case['texts'])
        results.append(dict(case,profile=result.summary(),passed=result.primary_domain==case['domain'] and set(case['branches'])<=set(dict(result.subdomains))))
    save('profiler_dev.json',dict(definition='Development cases, not final holdout evidence',cases=results))
    assert all(r['passed'] for r in results)
    held=[
        dict(id='repair',texts=['更换前门面板，检查门锁与车门限位器。车身维修完成后检查外板。'],domain='automotive',branches=['automotive.body.doors','automotive.body.panels']),
        dict(id='measurement',texts=['记录实际测量尺寸。对角线尺寸应从测量点投影到参考平面。'],domain='automotive',branches=['automotive.body.body_measurement','automotive.body.body_geometry']),
        dict(id='cooling',texts=['检查储液罐中的冷却液。散热器和冷却风扇应保持清洁。'],domain='automotive',branches=['automotive.cooling']),
        dict(id='engine',texts=['发动机舱内检查机油。发动机的燃油系统需要检查。'],domain='automotive',branches=['automotive.engine']),
        dict(id='suspension',texts=['拆下副车架，检查悬架和减振器。'],domain='automotive',branches=['automotive.suspension']),
        dict(id='electrical',texts=['在连接器处测量电压。检查熔断器以及线束接地。'],domain='automotive',branches=['automotive.electrical']),
        dict(id='general',texts=['读书小组今天讨论旅行。故事中出现散热器，这是一个普通生活故事。'],domain='general',branches=[]),
        dict(id='mixed',texts=['检查冷却液与散热器。','检查线束和电压，确认熔断器没有损坏。'],domain='automotive',branches=['automotive.cooling','automotive.electrical']),
    ]
    config=ROOT/'assets/config/knowledge-context.json'
    destination=QA/'profiler_holdout.json'
    if not destination.exists():
        save('profiler_holdout.json',dict(frozen_before_results=True,rule_sha256=sha256(config.read_bytes()).hexdigest(),cases=held))
    held=json.loads(destination.read_text('utf-8'));results=[]
    for case in held['cases']:
        result=p.profile('zh','ru',segments=case['texts'])
        results.append(dict(case,profile=result.summary(),passed=result.primary_domain==case['domain'] and set(case['branches'])<=set(dict(result.subdomains))))
    save('profiler_holdout_results.json',dict(holdout_sha256=sha256(destination.read_bytes()).hexdigest(),passed=sum(r['passed'] for r in results),total=len(results),cases=results))
    print('PROFILER HOLDOUT',sum(r['passed'] for r in results),'/',len(results),flush=True)


def fixtures():
    from tools.pdf_fixtures import make_pdf
    root=QA/'fixtures';root.mkdir(exist_ok=True)
    make_pdf(root/'general.pdf',text='故事中的散热器只是比喻。今天我们讨论读书和旅行。',lines=2)
    make_pdf(root/'mixed.pdf',text='检查冷却液液位和散热器。检查熔断器和线束电压。',lines=2)


def run(mode, *, cycle='aw086', capture_routes=False, paths_override=None, legacy_templates=False):
    app=QApplication.instance() or QApplication([])
    configure_logging()
    output=ROOT/'output'/cycle/mode;output.mkdir(parents=True,exist_ok=True)
    if mode=='body' and (QA/'body_e2e.json').exists() and not (QA/'body_pilot.json').exists():
        shutil.copy2(QA/'body_e2e.json',QA/'body_pilot.json')
    source={'body':Path('C:/Users/PC/Downloads/车身尺寸.zip'),
            'coolant':ROOT/'tests/fixtures/pdf/automotive.pdf',
            'general':QA/'fixtures/general.pdf','mixed':QA/'fixtures/mixed.pdf'}[mode]
    documents=[];original=PdfDocument.validate
    def validate(document,path):
        result=original(document,path)
        relative=Path(*document.path.parts[document.path.parts.index('input')+1:]).as_posix() if 'input' in document.path.parts else document.path.name
        documents.append(dict(file=relative,source_pages=len(document.pages),output_pages=len(document.pages)+document.continuation_count,
            segments=[asdict(s) for s in document.segments],output_hash=sha256(Path(path).read_bytes()).hexdigest()))
        return result
    PdfDocument.validate=validate
    engine=create_translation_engine(memory=TranslationMemoryEngine(QA/(mode+'-isolated-tm.db')),
        glossary=GlossaryEngine(QA/(mode+'-isolated-glossary.db'),builtin_paths=paths_override or bundled_paths()))
    routes=[];model_calls=[]
    if legacy_templates:engine.context_router.templates=[r for r in engine.context_router.templates if not r['id'].startswith('aw087-')]
    if capture_routes:
        original_translate=engine._translate;original_model=engine.router.translate
        def traced(request,*args,**kwargs):
            result=original_translate(request,*args,**kwargs)
            routes.append(dict(source=request.text,segment_type=request.segment_type,context=request.context_profile.summary() if request.context_profile else {},
                output=result.translated_text,knowledge_source=result.knowledge_source,backend=result.backend,constraint_status=result.constraint_status))
            return result
        def inference(request,*args,**kwargs):
            model_calls.append(dict(source=request.text,segment_type=request.segment_type))
            return original_model(request,*args,**kwargs)
        engine._translate=traced;engine.router.translate=inference
    before=sha256(source.read_bytes()).hexdigest();started=time.perf_counter();control=JobControl();warnings=[]
    scanned=scan_sources([source],control)
    last=[0.]
    def progress(value):
        if time.perf_counter()-last[0]>30:
            print(mode,value.stage,value.file_index,value.processed,value.total,round(control.elapsed,2),flush=True);last[0]=time.perf_counter()
    config=DocumentConfig(source='zh',target='ru',output=output,domain='auto',translate_directories=True,translate_filenames=True)
    job=DocumentJob(scanned.files,config,control,engine.translate,engine.languages.resolve,progress=progress,warning=warnings.append)
    try:
        with document_run(job.run_id),engine.runtime.keep_warm():
            paths=job.run()
        result=dict(mode=mode,run=job.run_id,elapsed=time.perf_counter()-started,source_hash_before=before,
            source_hash_after=sha256(source.read_bytes()).hexdigest(),documents=documents,outputs=[str(p) for p in paths],
            warnings=warnings,context=engine.last_context_metrics,routes=routes,model_calls=model_calls)
        if mode=='body':
            from zipfile import ZipFile
            with ZipFile(paths[0]) as archive:result['crc_ok']=archive.testzip() is None
        save(mode+'_e2e.json',result)
        logging.getLogger('treetranslate.documents').info('run=%s operation=translate started version=AW0.8.6 files=%d requested_source=zh target=ru device=auto',job.run_id,len(scanned.files))
        logging.getLogger('treetranslate.documents').info('run=%s finished state=COMPLETED elapsed=%.2f warnings=%d active_seconds=%.2f',job.run_id,control.elapsed,len(warnings),control.active_seconds)
        if mode=='body':save('accepted_segments.json',result)
        print('RESULT',mode,round(result['elapsed'],2),result['outputs'],flush=True)
    finally:
        engine.shutdown();PdfDocument.validate=original


def holdout():
    frozen=ROOT/'qa/aw085/holdout_fresh.json';before_hash=sha256(frozen.read_bytes()).hexdigest()
    cases=json.loads(frozen.read_text('utf-8'))['entries']
    baseline=json.loads((ROOT/'qa/aw085/holdout_fresh_results.json').read_text('utf-8'))['after']
    engine=create_translation_engine(memory=TranslationMemoryEngine(QA/'holdout-isolated-tm.db'),
        glossary=GlossaryEngine(QA/'holdout-isolated-glossary.db',builtin_paths=bundled_paths()))
    profile=engine.profile_document('zh','ru',identity=before_hash,segments=[c['source'] for c in cases])
    snapshot=engine.context_router.snapshot(profile);rows=[]
    try:
        for case,old in zip(cases,baseline):
            result=engine.translate(TranslationRequest(case['source'],'zh','ru',domain='auto',context_profile=profile,knowledge_snapshot=snapshot))
            rows.append(dict(case,before=old['output'],after=result.translated_text,backend=result.backend,
                exact=result.translated_text==case['reference'],same_as_aw085=result.translated_text==old['output']))
        save('holdout_regression.json',dict(frozen_sha256=before_hash,references_unchanged=sha256(frozen.read_bytes()).hexdigest()==before_hash,
            baseline=dict(PASS=33,MINOR=4,MAJOR=3,CATASTROPHIC=0),profile=profile.summary(),rows=rows))
        print('HOLDOUT',sum(r['exact'] for r in rows),'exact',sum(r['same_as_aw085'] for r in rows),'unchanged',flush=True)
    finally:engine.shutdown()


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='prepare':prepare()
    elif mode=='fixtures':fixtures()
    elif mode=='holdout':holdout()
    else:run(mode)
