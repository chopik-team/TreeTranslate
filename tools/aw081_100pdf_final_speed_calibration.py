"""One measured historical sample, with observational hooks only. No tuning."""
from collections import Counter
from hashlib import sha256
import argparse
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
from time import perf_counter, time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aw081_speed_calibration_100 import frozen_hashes, EXPECTED_SOURCE_SHA
from app.documents.run_metrics import file_hash
QA = ROOT / 'qa/aw081/100pdf_final_speed_calibration'
OLD = ROOT / 'qa/aw081/speed_calibration_100'


def read(path): return json.loads(Path(path).read_text('utf8'))
def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n', 'utf8')
    os.replace(temp, path)


def verify_members(manifest, original, subset):
    docs = manifest['documents']
    assert len(docs) == 100 and len({d['member_path'] for d in docs}) == 100
    infos = [i for i in original.infolist() if not i.is_dir() and i.filename.lower().endswith('.pdf')]
    assert len(infos) == 17211
    assert [i.filename for i in subset.infolist()] == [d['member_path'] for d in docs]
    assert [d['inventory_pdf_index'] for d in docs] == sorted(d['inventory_pdf_index'] for d in docs)
    verified = []
    for d in docs:
        i = original.getinfo(d['member_path']); s = subset.getinfo(d['member_path'])
        assert infos[d['inventory_pdf_index']].filename == d['member_path']
        assert i.file_size == s.file_size == d['source_size'] and i.CRC == s.CRC
        data = original.read(i)
        assert data == subset.read(s) and sha256(data).hexdigest() == d['source_sha256']
        verified.append(dict(member=d['member_path'],crc=i.CRC,size=i.file_size,sha256=d['source_sha256']))
    assert subset.testzip() is None
    return verified


def preflight():
    assert not (QA/'run_started.json').exists(), 'Measured run already admitted; no second run'
    manifest = read(OLD/'sample_manifest.json')
    current = frozen_hashes()
    assert current == read(ROOT/'qa/aw081/final_speed_patch_5pdf/full_pytest.json')['production_hashes_after']
    knowledge = read(ROOT/'qa/aw081/final_speed_patch_5pdf/accepted_changes.json')['dictionary_sha256']
    assert all(file_hash(Path(p)) == digest for p,digest in knowledge.items())
    started = perf_counter()
    assert file_hash(Path(manifest['input_archive'])) == EXPECTED_SOURCE_SHA
    assert file_hash(Path(manifest['sample_archive'])) == manifest['sample_archive_sha256']
    with ZipFile(manifest['input_archive']) as original, ZipFile(manifest['sample_archive']) as subset:
        verified = verify_members(manifest, original, subset)
    QA.mkdir(parents=True, exist_ok=True)
    # Copy the historical manifest verbatim; never reselect or replace failed files.
    (QA/'sample_manifest.json').write_bytes((OLD/'sample_manifest.json').read_bytes())
    save(QA/'run_manifest.json', dict(same_sample='PASS',historical_run='25825c3f75a7',
        verified_members=verified,source_sha256=EXPECTED_SOURCE_SHA,preflight_seconds=perf_counter()-started,
        production_hashes_before=current,dictionary_sha256=knowledge,last_pytest_passed=1256,
        settings='Unmodified DocumentConfig defaults; auto/ru/auto, translated filenames/directories; ORIGINAL policy',
        input='Exact historical subset ZIP, byte-proven against full original corpus; same archive context as baseline',
        warmup=dict(contents=[],seconds=0,resident_models=[],
            reason='Historical run() has no explicit warmup. Cold model initialization remains inside measured wall.',
            caches='Fresh empty isolated TM/user database; no input pretranslation or document cache warmup'),
        sample_scan_in_wall=True,full_corpus_run=False))
    print('PREFLIGHT PASS: exact 100; full source SHA; current production == 1256 PASS; 49 dictionaries unchanged',flush=True)


class LookupObserver:
    """Observe only logical lookups and statements on glossary database connections."""
    def __init__(self):
        self.active=False;self.counts=Counter();self.keys=set();self.negatives=Counter();self.seconds=0
    def install(self):
        from app.glossary.engine import GlossaryEngine
        from dataclasses import asdict
        owner=self;self.original_connect=sqlite3.connect;self.original_lookup=GlossaryEngine.lookup
        class Connection(sqlite3.Connection):
            def execute(self,sql,*args,**kwargs):
                if owner.active and self.observed:owner.counts['sql_statements']+=1
                return super().execute(sql,*args,**kwargs)
        def connect(*args,**kwargs):
            path=str(args[0] if args else kwargs.get('database','')).lower().replace('\\','/')
            # Isolated TM and run metrics are deliberately excluded from glossary SQL.
            con=owner.original_connect(*args,**dict(kwargs,factory=Connection))
            con.observed=('index.sqlite3' not in path and 'isolated-tm.db' not in path)
            return con
        def lookup(engine,text,source,target,domain='general',context='',**kwargs):
            start=perf_counter();result=owner.original_lookup(engine,text,source,target,domain,context,**kwargs)
            if owner.active:
                request=kwargs.get('request');snapshot=kwargs.get('snapshot')
                profile=getattr(request,'context_profile',None)
                key=json.dumps([text,source,target,domain,context,getattr(snapshot,'signature',None),
                    getattr(request,'segment_type',''),asdict(profile) if profile else None],sort_keys=True,default=str)
                key=sha256(key.encode()).hexdigest();owner.keys.add(key);owner.counts['lookups']+=1
                owner.seconds+=perf_counter()-start
                if not result:owner.negatives[key]+=1
            return result
        sqlite3.connect=connect;GlossaryEngine.lookup=lookup
    def close(self):
        from app.glossary.engine import GlossaryEngine
        sqlite3.connect=self.original_connect;GlossaryEngine.lookup=self.original_lookup
    def result(self):return dict(counts=dict(self.counts),unique_logical_lookups=len(self.keys),
        seconds=self.seconds,negative_lookups=sum(self.negatives.values()),
        repeated_negative_results=sum(n-1 for n in self.negatives.values()))


def run():
    receipt=read(QA/'run_manifest.json');manifest=read(QA/'sample_manifest.json')
    assert frozen_hashes()==receipt['production_hashes_before']
    marker=QA/'run_started.json'
    with marker.open('x',encoding='utf8') as stream:json.dump(dict(started_unix=time(),one_measured_run=True),stream)
    raw=QA/'raw';raw.mkdir(exist_ok=False)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    os.environ['TREETRANSLATE_OCR_LIFECYCLE_LOG']=str(raw/'ocr_lifecycle.jsonl')
    from PySide6.QtWidgets import QApplication
    qt=QApplication.instance() or QApplication([])
    from app.documents.control import JobControl
    from app.documents.job import DocumentJob,DocumentConfig
    from app.documents.scanner import scan_sources
    from app.documents import run_metrics as metrics
    from app.engine.factory import create_translation_engine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from tools.aw081_final_speed_patch import Profile
    from tools.aw081_hardware_support import Monitor,gpu_once
    from app.documents.pdf_document import PdfDocument,NativeTextExtractor
    from tools.aw081_ocr_adaptive import source_contract
    import psutil
    observer=Profile();observer.install();lookup=LookupObserver();lookup.install()
    engine=create_translation_engine(memory=TranslationMemoryEngine(raw/'isolated-tm.db'),
        glossary=GlossaryEngine(raw/'isolated-user.db',builtin_paths=bundled_paths()))
    handler=logging.FileHandler(raw/'timing.log',encoding='utf8');handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s'))
    logger=logging.getLogger('treetranslate');logger.setLevel(logging.INFO);logger.addHandler(handler)
    state=dict(phase='measured',stage=None,member=None)
    class NoBudget:
        def peak(self):return None  # Observation only: NO Windows job assignment or benchmark RAM cap.
    monitor=Monitor(raw/'resource_samples_tree.jsonl',NoBudget(),state)
    receipt['hardware']=dict(logical_cpu=psutil.cpu_count(),physical_cpu=psutil.cpu_count(logical=False),
        ram_bytes=psutil.virtual_memory().total,gpu=gpu_once())
    originals=(metrics.LocalRun.stage,metrics.LocalRun.archive_event,metrics.LocalRun.model_event,PdfDocument.__init__)
    events=[];errors=[];sources={};by_hash={d['source_sha256']:d['member_path'] for d in manifest['documents']}
    timing=(raw/'timing_events.jsonl').open('x',encoding='utf8',buffering=65536)
    def stage(local,name,seconds,state_='ok',page=None,block=None):
        result=originals[0](local,name,seconds,state_,page,block)
        try:
            state['stage']=name
            timing.write(json.dumps(dict(stage=name,seconds=seconds,state=state_,page=page,block=block,
                document_id=getattr(metrics._doc.get(),'document_id',None),elapsed_since_run_start=perf_counter()-start))+'\n')
        except Exception as e:errors.append(type(e).__name__)
        return result
    def event(local,name,**data):
        result=originals[1](local,name,**data)
        try:
            row=dict(event=name,elapsed_since_run_start=perf_counter()-start,**data);events.append(row)
            if name in {'document_start','member_packaged'}:
                state['member']=data.get('member',data.get('source_member'))
                count=sum(r['event']==name for r in events)
                print(name,count,'/100',round(row['elapsed_since_run_start'],2),flush=True)
                save(QA/'live_progress.json',dict(events=events,elapsed=row['elapsed_since_run_start']))
        except Exception as e:errors.append(type(e).__name__)
        return result
    def model(local,backend,device,success,fallback,error_type=None):
        result=originals[2](local,backend,device,success,fallback,error_type)
        local.emit('routing',dict(event='backend_attempt',backend=backend,device=device,success=success,fallback=fallback,exception_type=error_type))
        return result
    def pdf_init(document,*args,**kwargs):
        originals[3](document,*args,**kwargs)
        extractor=kwargs.get('extractor',args[3] if len(args)>3 else None)
        member=by_hash.get(document.source_hash)
        if observer.active and member and extractor is not None and not isinstance(extractor,NativeTextExtractor):
            sources[member]=source_contract(document)
    metrics.LocalRun.stage=stage;metrics.LocalRun.archive_event=event;metrics.LocalRun.model_event=model;PdfDocument.__init__=pdf_init
    control=JobControl();job=None;outputs=[];fatal=None
    monitor.start();observer.active=lookup.active=True;start=perf_counter()
    try:
        scan=scan_sources([Path(manifest['sample_archive'])],control)
        receipt['sample_scan_seconds']=perf_counter()-start
        assert len(scan.files)==100
        cfg=DocumentConfig(source='auto',target='ru',domain='auto',translate_directories=True,translate_filenames=True,
            output=raw/'output',metrics_directory=raw/'logs')
        job=DocumentJob(scan.files,cfg,control,engine.translate,engine.languages.resolve,before_ocr=engine.runtime.release_models)
        job.metrics_metadata=dict(scope='FINAL_100PDF_CALIBRATION_ONLY',historical_run='25825c3f75a7',selected_files=100,
            input_corpus=manifest['input_archive'],scan_seconds=receipt['sample_scan_seconds'],training=False)
        with engine.runtime.keep_warm():outputs=job.run()
    except BaseException as e:
        import traceback
        fatal=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
    finally:
        wall=perf_counter()-start;observer.active=lookup.active=False
        monitor.finish();timing.close()
        receipt.update(wall_seconds=wall,run_id=getattr(job,'run_id',None),logs=str(getattr(job,'metrics_path','')),
            outputs=[str(p) for p in outputs],fatal=fatal,events=events,observer_errors=errors,
            glossary_counters=dict(engine.glossary.counters),glossary_cache=engine.glossary.cache_metrics(),
            lookup_profile=lookup.result(),resource_monitor_errors=monitor.errors)
        metrics.LocalRun.stage,metrics.LocalRun.archive_event,metrics.LocalRun.model_event,PdfDocument.__init__=originals
        lookup.close();observer.close();engine.shutdown();logger.removeHandler(handler);handler.close()
    save(raw/'observations.json',observer.result());save(raw/'source_contracts.json',sources)
    receipt['production_hashes_after']=frozen_hashes()
    receipt['production_unchanged']=receipt['production_hashes_after']==receipt['production_hashes_before']
    receipt['source_unchanged']=file_hash(Path(manifest['input_archive']))==EXPECTED_SOURCE_SHA
    receipt['sample_unchanged']=file_hash(Path(manifest['sample_archive']))==manifest['sample_archive_sha256']
    receipt['dictionary_unchanged']=all(file_hash(Path(p))==h for p,h in receipt['dictionary_sha256'].items())
    save(QA/'run_manifest.json',receipt)
    assert receipt['production_unchanged'] and receipt['source_unchanged'] and receipt['sample_unchanged'] and receipt['dictionary_unchanged']
    print('FINISHED',wall,'fatal',fatal,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['preflight','run']);args=parser.parse_args()
    preflight() if args.mode=='preflight' else run()
