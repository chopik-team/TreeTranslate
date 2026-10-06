"""Fixed, bounded resource experiment; all controls exist only in QA processes."""
from collections import Counter, defaultdict
from dataclasses import replace
import argparse
import ast
import copy
import inspect
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from time import perf_counter, time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aw081_speed_calibration_100 import frozen_hashes, save
from tools.aw081_hardware_support import CommitBudget, Monitor, gpu_once, GIB
QA = ROOT / 'qa/aw081/hardware_scaling_20'


def configuration(cpu, gpu, ram):
    return dict(cpu=cpu, gpu=gpu, ram=ram, threads=6 if cpu=='LOW' else 14,
        ocr_threads=6 if cpu=='LOW' else 14,
        ram_gib=8 if ram=='LOW' else 24, vram_gib=4.5 if gpu=='LOW' else 10.5,
        nmt_batch_tokens=384 if gpu=='LOW' else 1536, ocr_batch=2 if gpu=='LOW' else 16,
        glossary_cache_entries=512 if ram=='LOW' else 4096,
        compiled_indexes=8 if ram=='LOW' else 32,
        gpu_residency='serial' if gpu=='LOW' else 'coexistence_probe',
        persistent_ocr=gpu=='HIGH', pipeline_depth=1, gpu_queue_depth=1)


CONFIGS = dict(zip([f'run{i}' for i in range(1,9)], [configuration(*values) for values in
    [('LOW','LOW','LOW'),('HIGH','LOW','LOW'),('LOW','HIGH','LOW'),('LOW','LOW','HIGH'),
     ('HIGH','HIGH','LOW'),('HIGH','LOW','HIGH'),('LOW','HIGH','HIGH'),('HIGH','HIGH','HIGH')]]))
CONFIGS['mid'] = dict(cpu='MID',gpu='MID',ram='MID',threads=8,ocr_threads=4,
    ram_gib=16,vram_gib=6.5,nmt_batch_tokens=768,ocr_batch=6,glossary_cache_entries=512,
    compiled_indexes=8,gpu_residency='serial',persistent_ocr=False,pipeline_depth=1,gpu_queue_depth=1)
ORDER = ['run1','run8','mid','run2','run7','run3','run6','run4','run5']


def current_member(metrics):
    doc = metrics._doc.get()
    return doc.data.get('archive_member_path') if doc else None


def fingerprint_pdf(data, render_pages=False):
    import hashlib
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    result = dict(pages=[], renders=[])
    pdf = pdfium.PdfDocument(data)
    try:
        for i in range(len(pdf)):
            page = pdf[i]; tp = page.get_textpage(); objects=[]
            try:
                for obj in page.get_objects(max_depth=8):
                    matrix=obj.get_matrix()
                    row = dict(type=obj.type,bounds=[round(x,5) for x in obj.get_bounds()],
                        matrix=[round(getattr(matrix,k),5) for k in ('a','b','c','d','e','f')])
                    import ctypes
                    for label,getter in [('fill',raw.FPDFPageObj_GetFillColor),('stroke',raw.FPDFPageObj_GetStrokeColor)]:
                        color=[ctypes.c_uint() for _ in range(4)]
                        if getter(obj,*color):row[label]=[c.value for c in color]
                    if obj.type==raw.FPDF_PAGEOBJ_TEXT:
                        obj.textpage=tp; row.update(text=obj.extract(),font_size=round(obj.get_font_size(),5))
                    objects.append(row)
                result['pages'].append(dict(size=list(page.get_size()),rotation=page.get_rotation(),
                    text=tp.get_text_range(),objects=objects))
                if render_pages and i in {0,len(pdf)-1}:
                    bitmap=page.render(scale=1.25); image=bitmap.to_pil().convert('RGB')
                    result['renders'].append(dict(page=i,shape=image.size,sha256=hashlib.sha256(image.tobytes()).hexdigest()))
                    bitmap.close()
            finally: tp.close();page.close()
    finally: pdf.close()
    return result


def controls(cfg, engine, control, measurements):
    """Keep semantic policy intact; change only documented resource fields."""
    from app.engine.router.routing_policy import RoutingPolicy
    from app.ocr.config import configuration as ocr_configuration
    from app.ocr.runtime.ocr_runtime_manager import OcrRuntimeManager
    from app.ocr.router.ocr_router import OcrRouter
    from app.documents.archive_job import ArchiveJob
    original = RoutingPolicy.profile
    def profile(policy,name,threads=None):
        return replace(original(policy,name,threads),threads=cfg['threads'],batch_tokens=cfg['nmt_batch_tokens'])
    RoutingPolicy.profile=profile
    ocr=ocr_configuration()
    ocr['profiles']['automatic']['threads']=cfg['ocr_threads']
    ocr['profiles']['automatic']['batch']=cfg['ocr_batch']
    if cfg['persistent_ocr']:ocr['runtime']['idle_seconds']=3600
    shared = OcrRuntimeManager(checkpoint=control.checkpoint) if cfg['persistent_ocr'] else None
    if shared:
        init=OcrRouter.__init__
        def initialize(router,checkpoint=lambda:None,runtime=None,before_ocr=lambda:None):
            return init(router,checkpoint,runtime or shared,before_ocr)
        OcrRouter.__init__=initialize
        OcrRouter.shutdown=lambda router:None
    ocr_run=OcrRuntimeManager.run
    def recognize(runtime,image,command):
        measurements['active_ocr']+=1
        try:
            result=ocr_run(runtime,image,command)
            measurements['ocr_calls'].append(dict(member=measurements.get('member'),
                device=command['device'],backend=command['backend'],recognizer=command['recognizer'],
                options=command['options'],**{k:result.get(k) for k in
                ['load_seconds','inference_seconds','rss_bytes','gpu_peak_allocated_bytes','gpu_peak_reserved_bytes']}))
            return result
        finally:measurements['active_ocr']-=1
    OcrRuntimeManager.run=recognize
    # The Paddle allocation cap applies to its worker only. CT2 has no public
    # allocator quota. Reserve no memory; measure device peak and report scope.
    os.environ['FLAGS_allocator_strategy']='auto_growth'
    os.environ['FLAGS_gpu_memory_limit_mb']=str(int((cfg['vram_gib']-1 if shared else cfg['vram_gib'])*1024))
    measurements['vram_limit_scope']='Paddle worker hard allocator cap; CT2/backend CUDA cap UNAVAILABLE; device-wide peak observed. 1 GiB headroom for CT2 in coexistence arms.'
    if shared:
        before_ocr=lambda:None
    else:before_ocr=engine.runtime.release_models
    # Change only the processing loop, preserving archive inventory, context
    # sampling, all original-path reservations and writer/recovery code.
    if measurements['order']=='easy_first':
        tree=ast.parse(textwrap.dedent(inspect.getsource(ArchiveJob._run)))
        count=0
        for node in ast.walk(tree):
            if (isinstance(node,ast.With) and any(isinstance(item.context_expr,ast.Call)
                and getattr(item.context_expr.func,'id','')=='ZipFile' for item in node.items)):
                for child in node.body:
                    if isinstance(child,ast.For) and isinstance(child.iter,ast.Name) and child.iter.id=='members':
                        child.iter=ast.Call(func=ast.Name(id='_qa_order_members',ctx=ast.Load()),args=[child.iter],keywords=[]);count+=1
        assert count==1
        manifest=json.loads((QA/'sample_manifest.json').read_text('utf8'))
        metadata={d['member_path']:d for d in manifest['documents']}
        def order_members(members):
            def key(member):
                d=metadata[member.name];i=d['source_inspection']
                likelihood=2 if i['empty_native_pages'] or not i['native_alphabetic_chars'] else 1 if i['large_raster_pages'] else 0
                return likelihood,d['pages'],d['source_size'],member.name
            return sorted(members,key=key)
        namespace=dict(ArchiveJob._run.__globals__,_qa_order_members=order_members)
        ast.fix_missing_locations(tree);exec(compile(tree,'<QA easy-first processing loop>','exec'),namespace)
        ArchiveJob._run=namespace['_run']
    return before_ocr,shared


def run(label, config_name, order='original', warm_sustained=False):
    import hashlib
    from threading import Event
    cfg=CONFIGS[config_name]
    assert frozen_hashes()==json.loads((QA/'production_before.json').read_text('utf8'))
    manifest=json.loads((QA/'sample_manifest.json').read_text('utf8'));source=Path(manifest['sample_archive'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['sample_archive_sha256']
    with ZipFile(source) as f:assert len(f.infolist())==20 and all(i.filename.endswith('.pdf') for i in f.infolist())
    directory=QA/'runs'/label;directory.mkdir(parents=True,exist_ok=False)
    os.environ.update(QT_QPA_PLATFORM='offscreen',OMP_NUM_THREADS=str(cfg['threads']),
        OPENBLAS_NUM_THREADS=str(cfg['threads']),MKL_NUM_THREADS=str(cfg['threads']))
    budget=CommitBudget(cfg['ram_gib'])
    from PySide6.QtWidgets import QApplication
    qt=QApplication.instance() or QApplication([])
    from app.documents import run_metrics as metrics
    from app.documents.scanner import scan_sources
    from app.documents.control import JobControl
    from app.documents.job import DocumentConfig,DocumentJob
    from app.documents.pdf_document import PdfDocument
    from app.engine.factory import create_translation_engine
    from app.glossary.bundled import bundled_paths
    from app.glossary.engine import GlossaryEngine
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.engine.types import TranslationRequest
    from app.ocr.router.ocr_router import OcrRouter
    from app.ocr.types import OcrRequest
    control=JobControl()
    engine=create_translation_engine(memory=TranslationMemoryEngine(directory/'empty-tm.db'),
        glossary=GlossaryEngine(directory/'empty-user.db',builtin_paths=bundled_paths(),
            config=dict(cache_size=cfg['glossary_cache_entries'],compiled_index_cache_size=cfg['compiled_indexes'])))
    state=dict(phase='warmup',order=order,stage=None,member=None,events=[],ocr_calls=[],batch_calls=[],
        active_ocr=0,active_model=0,models=[],timing=[],candidates=defaultdict(list),writer={},observer_errors=[])
    state['before_gpu']=gpu_once()
    before_ocr,shared=controls(cfg,engine,control,state)
    from app.engine.runtime.cuda_libraries import load_cuda_libraries
    load_cuda_libraries()
    import ctranslate2
    native_translator=ctranslate2.Translator
    class TranslatorObserver:
        def __init__(self,*args,**kwargs):
            self.native=native_translator(*args,**kwargs);self.device=kwargs.get('device')
        def __getattr__(self,name):return getattr(self.native,name)
        def translate_batch(self,source,**kwargs):
            state['active_model']+=1
            try:
                state['batch_calls'].append(dict(device=self.device,sequences=len(source),
                    tokens=sum(len(x) for x in source),batch_limit=kwargs.get('max_batch_size'),beam=kwargs.get('beam_size')))
                return self.native.translate_batch(source,**kwargs)
            finally:state['active_model']-=1
    ctranslate2.Translator=TranslatorObserver
    from collections import OrderedDict
    class ObservedCache(OrderedDict):
        hits=misses=0
        def __contains__(self,key):
            found=super().__contains__(key)
            if found:self.hits+=1
            else:self.misses+=1
            return found
    engine.glossary.cache=ObservedCache(engine.glossary.cache)
    engine.memory.cache=ObservedCache(engine.memory.cache)
    handler=logging.FileHandler(directory/'timing.log',encoding='utf8')
    handler.setFormatter(logging.Formatter('%(asctime)s | %(name)s | %(message)s'))
    logger=logging.getLogger('treetranslate');logger.setLevel(logging.INFO);logger.addHandler(handler)
    scan=scan_sources([source],control);assert len(scan.files)==20
    # One fixed warmup, never included in the measured wall. Use ONLY frozen
    # sample bytes and existing models/thresholds; no new corpus or learning.
    import pypdfium2 as pdfium
    with ZipFile(source) as f: warmbytes=f.read(manifest['documents'][0]['member_path'])
    pdf=pdfium.PdfDocument(warmbytes);page=pdf[0];tp=page.get_textpage();text=tp.get_text_range();tp.close()
    bitmap=page.render(scale=1.25);image=bitmap.to_pil().convert('RGB');bitmap.close();page.close();pdf.close()
    warm_start=perf_counter()
    try:
        router=OcrRouter(checkpoint=control.checkpoint,before_ocr=before_ocr)
        router.recognize(OcrRequest(image,complexity=dict(lines=9,regions=0,columns=0)))
        if not shared:router.shutdown()
        engine.translate(TranslationRequest(text[:500],'zh','ru'),control.cancelled)
    except Exception as error: state['warmup_error']=type(error).__name__
    warmup_seconds=perf_counter()-warm_start
    state['ocr_calls'].clear()
    state['batch_calls'].clear()
    for cache in (engine.glossary.cache,engine.memory.cache):cache.hits=cache.misses=0
    # Observe without changing the translation callback identity or data.
    originals=(metrics.LocalRun.stage,metrics.LocalRun.archive_event,metrics.LocalRun.model_event,
        DocumentJob._pdf_translation,PdfDocument.write)
    start=perf_counter()
    def stage(observer,name,seconds,status='ok',page=None,block=None):
        result=originals[0](observer,name,seconds,status,page,block)
        state['stage']=name
        state['timing'].append(dict(stage=name,seconds=seconds,state=status,
            document_id=getattr(metrics._doc.get(),'document_id',None),elapsed=perf_counter()-start))
        return result
    def event(observer,name,**data):
        result=originals[1](observer,name,**data)
        state['events'].append(dict(event=name,elapsed=perf_counter()-start,**data))
        if name=='document_start':state['member']=data['member']
        if name=='member_packaged':
            completed=sum(x['event']=='member_packaged' for x in state['events'])
            assert completed<=20
            save(QA/'live_progress.json',dict(label=label,config=config_name,completed=completed,total=20,
                wall_seconds=perf_counter()-start,phase=state['phase'],member=state['member']))
            print('PACKAGED',label,completed,'/20',round(perf_counter()-start,2),flush=True)
        return result
    def model(observer,backend,device,success,fallback,error_type=None):
        result=originals[2](observer,backend,device,success,fallback,error_type)
        state['models'].append(dict(backend=backend,device=device,success=success,fallback=fallback,error_type=error_type))
        return result
    def candidate(job,text,source_lang,target_lang):
        member=current_member(metrics)
        try:
            result=originals[3](job,text,source_lang,target_lang)
            state['candidates'][member].append(dict(source=text,target=result))
            return result
        except Exception as error:
            state['candidates'][member].append(dict(source=text,error_type=type(error).__name__))
            raise
    def writer(document,output):
        member=current_member(metrics)
        row=dict(segments=[dict(block=s.block_id,page=s.page,source=s.text,target=s.translated,
            ids=sorted(__import__('re').findall(r'[A-Z][A-Z0-9_-]*\d[A-Z0-9_-]*|\d+(?:[.,]\d+)?',s.translated or s.text)))
            for s in document.segments])
        state['writer'][member]=row
        try:result=originals[4](document,output)
        except Exception as error:row['error_type']=type(error).__name__;raise
        row['continuation_pages']=getattr(document,'continuation_count',0)
        row['segment_results']=[dict(status=s.status,visible=s.visible_text,overflow=s.overflow_text) for s in document.segments]
        return result
    metrics.LocalRun.stage,metrics.LocalRun.archive_event,metrics.LocalRun.model_event=stage,event,model
    DocumentJob._pdf_translation,PdfDocument.write=candidate,writer
    monitor=Monitor(directory/'resource_samples.jsonl',budget,state)
    outputs=[];fatal=None
    cfgdoc=DocumentConfig(source='auto',target='ru',domain='auto',threads=cfg['threads'],
        translate_directories=True,translate_filenames=True,output=directory/'output',metrics_directory=directory/'logs')
    try:
        with engine.runtime.keep_warm():
            if warm_sustained:
                state['phase']='sustained_warmup_full20'
                job=DocumentJob(scan.files,replace(cfgdoc,output=directory/'warmup-output'),control,
                    engine.translate,engine.languages.resolve,before_ocr=before_ocr)
                job.run()
                state['events'].clear();state['timing'].clear();state['models'].clear();state['ocr_calls'].clear()
                state['candidates'].clear();state['writer'].clear()
                state['batch_calls'].clear()
                for cache in (engine.glossary.cache,engine.memory.cache):cache.hits=cache.misses=0
            start=perf_counter();state['phase']='measured';monitor.start()
            job=DocumentJob(scan.files,cfgdoc,control,engine.translate,engine.languages.resolve,before_ocr=before_ocr)
            outputs=job.run()
    except BaseException as error:fatal=dict(type=type(error).__name__,status=getattr(job,'run_status','FAILED'))
    finally:
        wall=perf_counter()-start
        records=monitor.finish() if hasattr(monitor,'thread') else []
        metrics.LocalRun.stage,metrics.LocalRun.archive_event,metrics.LocalRun.model_event,DocumentJob._pdf_translation,PdfDocument.write=originals
        if shared:shared.shutdown()
        engine.shutdown();logger.removeHandler(handler);handler.close()
    receipt=dict(label=label,config=config_name,resource_configuration=cfg,order=order,wall_seconds=wall,
        warmup_seconds=warmup_seconds,sustained=warm_sustained,run_id=getattr(job,'run_id',None),fatal=fatal,
        outputs=[str(p) for p in outputs],logs=str(getattr(job,'metrics_path','')),events=state['events'],
        models=state['models'],ocr_calls=state['ocr_calls'],vram_limit_scope=state['vram_limit_scope'],
        cpu_time_seconds=sum(monitor.cpu_times.values())-getattr(monitor,'initial_cpu',0),
        monitor_errors=monitor.errors,production_unchanged=frozen_hashes()==json.loads((QA/'production_before.json').read_text('utf8')),
        source_immutable=hashlib.sha256(source.read_bytes()).hexdigest()==manifest['sample_archive_sha256'],
        glossary_cache_size=len(engine.glossary.cache),glossary_term_counters=dict(engine.glossary.counters),
        glossary_cache_hits=engine.glossary.cache.hits,glossary_cache_misses=engine.glossary.cache.misses,
        tm_cache_hits=engine.memory.cache.hits,tm_cache_misses=engine.memory.cache.misses,
        system_gpu_note='Device-wide telemetry includes other applications; WDDM process VRAM/compute ownership UNAVAILABLE.',
        snapshots=dict(before_gpu=state.get('before_gpu')))
    save(directory/'execution.json',receipt)
    save(directory/'candidates.json',dict(state['candidates']));save(directory/'writer.json',state['writer'])
    save(directory/'ocr_calls.json',state['ocr_calls'])
    save(directory/'batch_calls.json',state['batch_calls'])
    (directory/'timing_events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in state['timing']),'utf8')
    if outputs:
        with sqlite3.connect(job.metrics_path/'index.sqlite3') as con:
            docs=[json.loads(x[0]) for x in con.execute('SELECT payload FROM documents')]
        assert len(docs)==20
        visual={next(x['member_path'] for x in manifest['documents'] if x['bucket']==b and x['baseline_status']=='TRANSLATED') for b in manifest['bucket_counts']}
        fingerprints={}
        with ZipFile(outputs[0]) as output,ZipFile(source) as original:
            assert output.testzip() is None
            for doc in docs:
                member=doc['archive_member_path'];entry=doc['output_archive_member'];data=output.read(entry)
                if doc['output_status']=='FAILED_SOURCE_PRESERVED':assert entry==member and data==original.read(member)
                fp=fingerprint_pdf(data,member in visual)
                fingerprints[member]=dict(status=doc['output_status'],output_member=entry,
                    source_preserved_segments=doc['counters'].get('source_preserved_segments',0),
                    protected_tokens=doc.get('protected_tokens'),pdf=fp,
                    failed_sha256=hashlib.sha256(data).hexdigest() if doc['output_status']=='FAILED_SOURCE_PRESERVED' else None)
        save(directory/'fingerprints.json',fingerprints)
        shutil.copy2(job.metrics_path/'run_summary.json',directory/'run_summary.json')
    assert receipt['production_unchanged'] and receipt['source_immutable']
    print('RUN_FINISHED',label,round(wall,2),fatal,flush=True)


def suite():
    for name in ORDER:
        path=QA/'runs'/name/'execution.json'
        if path.exists():continue
        completed=subprocess.run([sys.executable,'-X','utf8',__file__,'run','--label',name,'--config',name],cwd=ROOT)
        if completed.returncode:raise RuntimeError(f'QA run {name} exited {completed.returncode}')
        receipt=json.loads(path.read_text('utf8'))
        if receipt['fatal']:raise RuntimeError(f'Global failure in {name}; no automatic retry')
    print('FACTORIAL_AND_MID_COMPLETE',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['run','suite'])
    parser.add_argument('--label');parser.add_argument('--config',choices=list(CONFIGS));parser.add_argument('--order',default='original',choices=['original','easy_first'])
    parser.add_argument('--sustained',action='store_true');args=parser.parse_args()
    if args.mode=='suite':suite()
    else:run(args.label,args.config,args.order,args.sustained)
