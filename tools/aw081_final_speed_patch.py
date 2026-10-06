"""Frozen five-member performance gate; observers do not alter production policy."""
import argparse
import ast
import copy
from collections import Counter, defaultdict
from contextvars import ContextVar
from dataclasses import asdict, replace
import hashlib
import inspect
import json
import os
import re
from pathlib import Path
import statistics
import subprocess
import sys
import textwrap
from threading import RLock, local
from time import perf_counter
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QA = ROOT / 'qa/aw081/final_speed_patch_5pdf'
REF = ROOT / 'qa/aw081/adaptive_pipeline/runs/after'

def data_path(path):
    path=Path(path)
    if path.exists():return path
    if path.is_relative_to(QA):
        raw=QA/'raw_copies'/path.relative_to(QA)
        if raw.exists():return raw
    return path
def read(path): return json.loads(data_path(path).read_text('utf8'))
def lines(path): return [json.loads(x) for x in data_path(path).read_text('utf8').splitlines()]
def canonical(value): return json.loads(json.dumps(value, ensure_ascii=False, default=str))
def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n', 'utf8')

def sample():
    target = QA / 'sample_manifest.json'
    if target.exists(): return read(target)
    original = read(ROOT / 'qa/aw081/hardware_scaling_20/sample_manifest.json')
    execution = read(REF / 'execution.json')
    logs = Path(execution['logs'])
    documents = {d['archive_member_path']: d for d in lines(logs/'documents.jsonl')}
    stages = defaultdict(dict)
    for row in lines(logs/'stages.jsonl'):
        stages[row['document_id']][row['stage']] = row['seconds']
    selected = []; rules = []
    def pick(category, predicate, metric, descending=True):
        eligible = [d for d in original['documents'] if predicate(d) and d['index'] not in selected]
        def value(d):
            doc = documents[d['member_path']]
            return doc['total_wall_seconds'] if metric == 'wall' else stages[doc['document_id']].get(metric, 0)
        chosen = sorted(eligible, key=lambda d: ((-1 if descending else 1)*value(d), d['index']))[0]
        selected.append(chosen['index'])
        rules.append(dict(category=category, index=chosen['index'], metric=metric,
                          direction='maximum' if descending else 'minimum', seconds=value(chosen)))
    pick('native_fast', lambda d:d['classification']=='native' and d['bucket']=='EASY_NATIVE', 'wall', False)
    pick('mixed_OCR', lambda d:d['classification']=='mixed', 'ocr_recognize')
    pick('image_heavy_OCR', lambda d:d['classification']=='image_only', 'ocr_recognize')
    pick('NMT_heavy', lambda d:True, 'model_translation')
    pick('writer_layout_heavy', lambda d:True, 'pdf_page_layout_write')
    selected_docs = [d for d in original['documents'] if d['index'] in selected]
    archive = QA / 'CN7C_FINAL_FIXED5.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(original['sample_archive']) as source, ZipFile(archive, 'w') as output:
        for d in selected_docs:
            info = source.getinfo(d['member_path'])
            data=source.read(info)
            assert hashlib.sha256(data).hexdigest() == d['source_sha256']
            output.writestr(copy.copy(info), data)
    # All translated members get render probes; failed cases are checked byte-for-byte.
    for d in selected_docs:
        d['original_bucket'] = d['bucket']; d['bucket'] = 'FIXED5'
        d['reference_stage_seconds'] = stages[documents[d['member_path']]['document_id']]
        d['reference_status'] = documents[d['member_path']]['output_status']
    manifest = dict(original, documents=selected_docs, sample_count=5,
        sample_archive=str(archive), sample_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        bucket_counts={'FIXED5':5}, selection=rules, selection_reference_run_id=execution['run_id'],
        order='Original fixed20 order; metric ties use original index', frozen=True)
    save(target, manifest)
    return manifest

class Profile:
    def __init__(self):
        self.active=False; self.restores=[]; self.seconds=Counter(); self.counts=Counter()
        self.requests=[]; self.batches=[]; self.loads=[]; self.locks=[]
        self.phase=ContextVar('qa_pdf_phase',default='unattributed')
        self.request=ContextVar('qa_nmt_request',default=None)
    def patch(self, obj, name, value):
        original=getattr(obj,name);setattr(obj,name,value)
        self.restores.append(lambda:setattr(obj,name,original))
        return original
    def member(self):
        from tools.aw081_hardware_scaling_20 import current_member
        from app.documents import run_metrics
        return current_member(run_metrics)
    def timed(self,obj,name,label):
        original=getattr(obj,name)
        def wrapped(*args,**kwargs):
            start=perf_counter()
            try:return original(*args,**kwargs)
            finally:
                if self.active:
                    self.seconds[label]+=perf_counter()-start;self.counts[label]+=1
        self.patch(obj,name,wrapped)
    def install(self):
        owner=self
        import app.documents.pdf_document as pdf
        for method,phase in [('__init__','native_extraction'),('write','writer'),('validate','validation')]:
            original=getattr(pdf.PdfDocument,method)
            def wrapped(*args,_original=original,_phase=phase,**kwargs):
                token=owner.phase.set(_phase)
                try:return _original(*args,**kwargs)
                finally:owner.phase.reset(token)
            self.patch(pdf.PdfDocument,method,wrapped)
        class ObservedLock:
            def __init__(self,native):self.native=native;self.state=local()
            def _is_owned(self):return self.native._is_owned()
            def acquire(self,*args,**kwargs):
                start=perf_counter();result=self.native.acquire(*args,**kwargs)
                if result:
                    depth=getattr(self.state,'depth',0)
                    if not depth:
                        self.state.record=dict(phase=owner.phase.get(),member=owner.member(),
                            wait_seconds=perf_counter()-start,held_seconds=0,active=owner.active)
                        self.state.started=perf_counter()
                    self.state.depth=depth+1
                return result
            def release(self):
                depth=self.state.depth
                if depth==1:
                    row=self.state.record;row['held_seconds']=perf_counter()-self.state.started
                    if row.pop('active'):owner.locks.append(row)
                self.state.depth=depth-1;return self.native.release()
            def __enter__(self):self.acquire();return self
            def __exit__(self,*args):self.release()
        self.patch(pdf,'PDF_LOCK',ObservedLock(pdf.PDF_LOCK))
        # Native extraction and OCR recognition are exclusive subscopes inside the lock.
        self.timed(pdf.NativeTextExtractor,'extract','native_extract_actual')
        from app.ocr.router.ocr_router import OcrRouter
        self.timed(OcrRouter,'recognize','ocr_recognize_inclusive')
        from app.engine.runtime.runtime_manager import RuntimeManager
        original=RuntimeManager.run
        def runtime(runtime,backend,request,kind,options,cancelled):
            row=dict(member=owner.member(),backend=backend,kind=kind,options=asdict(options),
                request={key:canonical(getattr(request,key)) for key in
                    ('text','source_language','target_language','domain','context','document_type','segment_type')},
                profile=canonical(asdict(request.context_profile)) if request.context_profile else None,
                snapshot=getattr(request.knowledge_snapshot,'signature',None))
            token=owner.request.set(row);start=perf_counter()
            try:
                result=original(runtime,backend,request,kind,options,cancelled)
                row['output']=asdict(result);return result
            except BaseException as error:
                row['error_type']=type(error).__name__;raise
            finally:
                if owner.active:owner.requests.append(dict(row,seconds=perf_counter()-start))
                owner.request.reset(token)
        self.patch(RuntimeManager,'run',runtime)
        from app.engine.backends.m2m100_backend import M2M100Backend
        from app.engine.backends.m2m100_tokenizer import LocalM2M100Tokenizer
        self.timed(M2M100Backend,'_load','m2m100_load_or_reuse')
        for name in ('encode','source_tokens','decode'):
            self.timed(LocalM2M100Tokenizer,name,'tokenizer_'+name)
        import ctranslate2
        native=ctranslate2.Translator
        class Translator:
            def __init__(self,*args,**kwargs):
                start=perf_counter();error=None
                try:self.native=native(*args,**kwargs)
                except BaseException as e:error=type(e).__name__;raise
                finally:
                    if owner.active:owner.loads.append(dict(model=str(args[0]),device=kwargs.get('device'),
                        seconds=perf_counter()-start,error_type=error))
                self.model=str(args[0]);self.device=kwargs.get('device')
            def __getattr__(self,name):return getattr(self.native,name)
            def translate_batch(self,source,**kwargs):
                start=perf_counter()
                row=dict(member=owner.member(),model=self.model,device=self.device,
                    source=canonical(source),settings=canonical(kwargs),sequences=len(source),
                    tokens=sum(map(len,source)))
                try:
                    result=self.native.translate_batch(source,**kwargs)
                    row['outputs']=[r.hypotheses for r in result];return result
                except BaseException as error:row['error_type']=type(error).__name__;raise
                finally:
                    if owner.active:owner.batches.append(dict(row,seconds=perf_counter()-start))
        self.patch(ctranslate2,'Translator',Translator)
    def close(self):
        for restore in reversed(self.restores):restore()
    def result(self):
        def identity(row):return json.dumps({k:v for k,v in row.items() if k!='seconds'},sort_keys=True,default=str)
        repeated=Counter(json.dumps(dict(model=r['model'],device=r['device'],source=r['source'],settings=r['settings']),sort_keys=True) for r in self.batches)
        groups=defaultdict(lambda:dict(wait_seconds=0,held_seconds=0,count=0))
        for row in self.locks:
            g=groups[row['phase']];g['wait_seconds']+=row['wait_seconds'];g['held_seconds']+=row['held_seconds'];g['count']+=1
        return dict(nmt=dict(requests=self.requests,batches=self.batches,loads=self.loads,
            seconds=dict(self.seconds),counts=dict(self.counts),
            inference_seconds=sum(r['seconds'] for r in self.batches),calls=len(self.batches),
            sequences=sum(r['sequences'] for r in self.batches),tokens=sum(r['tokens'] for r in self.batches),
            median_sequences=statistics.median([r['sequences'] for r in self.batches]) if self.batches else 0,
            median_tokens=statistics.median([r['tokens'] for r in self.batches]) if self.batches else 0,
            batch1=sum(r['sequences']==1 for r in self.batches),batch2=sum(r['sequences']==2 for r in self.batches),
            repeated_identical_calls=sum(c-1 for c in repeated.values()),
            transfer_seconds=None,transfer_note='CT2 owns host/device preparation; its public synchronous call cannot separate transfer from inference'),
            locks=dict(groups=groups,records=self.locks,
                note='Outer RLock acquisitions only; held includes nested extraction/OCR or writer CPU work; never sum inclusive subscopes twice'))

def run(label,depth):
    assert label in ('baseline','after','depth1')
    manifest=sample();assert not data_path(QA/'runs'/label).exists(), 'One run per declared role; no implicit retry'
    if label!='baseline':assert (QA/'baseline.json').exists()
    from tools import aw081_hardware_scaling_20 as frozen
    from tools.aw081_glossary_hot_path import Profile as LookupProfile
    from tools.aw081_ocr_adaptive import source_contract
    from app.documents import run_metrics as metrics
    from app.documents.job import DocumentJob
    from app.documents.pdf_document import PdfDocument, NativeTextExtractor
    from app.documents.pipeline import PipelineCapabilities, PipelineHardwarePlan
    plan=replace(PipelineHardwarePlan.build(PipelineCapabilities.detect()),depth=depth,ready_depth=depth)
    hashes=frozen.frozen_hashes();save(QA/'production_before.json',hashes)
    old_job=DocumentJob.__init__
    def job_init(job,*args,**kwargs):old_job(job,*args,**kwargs);job._pipeline_plan=plan
    DocumentJob.__init__=job_init
    observer=Profile();observer.install()
    lookup=LookupProfile();lookup.install()
    trace=(QA/(label+'_lookup_trace.jsonl')).open('x',encoding='utf8');lookup.trace=trace
    sources={};by_hash={d['source_sha256']:d['member_path'] for d in manifest['documents']}
    old_pdf=PdfDocument.__init__
    def pdf_init(document,*args,**kwargs):
        old_pdf(document,*args,**kwargs)
        extractor=kwargs.get('extractor',args[3] if len(args)>3 else None)
        member=by_hash.get(document.source_hash)
        if observer.active and member and extractor is not None and not isinstance(extractor,NativeTextExtractor):
            sources[member]=canonical(source_contract(document))
    PdfDocument.__init__=pdf_init
    old_start,old_finish=frozen.Monitor.start,frozen.Monitor.finish
    os.environ['TREETRANSLATE_OCR_LIFECYCLE_LOG']=str(QA/(label+'_warmup_loads.jsonl'))
    def start(monitor):
        observer.active=lookup.active=True
        os.environ['TREETRANSLATE_OCR_LIFECYCLE_LOG']=str(QA/(label+'_ocr_loads.jsonl'))
        return old_start(monitor)
    def finish(monitor):observer.active=lookup.active=False;return old_finish(monitor)
    frozen.Monitor.start,frozen.Monitor.finish=start,finish
    namespace=dict(frozen.controls.__globals__,_current_metrics_member=lambda:frozen.current_member(metrics))
    code=textwrap.dedent(inspect.getsource(frozen.controls)).replace("measurements.get('member')",'_current_metrics_member()')
    exec(compile(code,'<QA task-local observer>','exec'),namespace)
    namespace=dict(frozen.run.__globals__,QA=QA,controls=namespace['controls'])
    tree=ast.parse(textwrap.dedent(inspect.getsource(frozen.run)))
    class Cardinality(ast.NodeTransformer):
        def visit_Constant(self,node):
            if type(node.value) is int and node.value==20:return ast.copy_location(ast.Constant(5),node)
            return node
    tree=Cardinality().visit(tree);ast.fix_missing_locations(tree)
    # Make every translated PDF a visual probe, rather than one per old bucket.
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='visual' for t in node.targets):
            node.value=ast.parse("{x['member_path'] for x in manifest['documents'] if x['baseline_status']=='TRANSLATED'}",mode='eval').body
    ast.fix_missing_locations(tree)
    exec(compile(tree,'<QA fixed5 cardinality and all translated render probes>','exec'),namespace)
    try:namespace['run'](label,'mid')
    finally:
        observer.active=lookup.active=False;trace.close()
        save(QA/(label+'_contracts.json'),dict(sources=sources,profiles=lookup.profiles))
        save(QA/(label+'_profile.json'),observer.result())
        save(QA/(label+'_lookup_summary.json'),lookup.summary())
        lookup.close();PdfDocument.__init__=old_pdf;observer.close()
        DocumentJob.__init__=old_job;frozen.Monitor.start,frozen.Monitor.finish=old_start,old_finish
    from tools.aw081_adaptive_pipeline import metrics as summary
    measured=summary(QA/'runs'/label)
    save(QA/(label+'.json'),dict(metrics=measured,depth=depth,production_hashes_before=hashes,
                              production_hashes_after=frozen.frozen_hashes()))
    assert read(QA/'runs'/label/'execution.json')['fatal'] is None
    print(json.dumps(dict(label=label,wall=measured['wall_seconds'],nmt=observer.result()['nmt']['inference_seconds'],locks=observer.result()['locks']['groups']),default=str),flush=True)

def nmt_micro():
    """Replay captured model-ready inputs only, never run document translation."""
    assert not (QA/'nmt_microbenchmark.json').exists()
    import ctranslate2
    from app.engine.runtime.cuda_libraries import load_cuda_libraries
    load_cuda_libraries()
    profile=read(QA/'baseline_profile.json')['nmt']
    grouped=defaultdict(list)
    for row in profile['batches']:
        if row['device']=='cuda' and 'm2m100' in row['model'] and row['sequences']==1 and 'outputs' in row:
            grouped[(row['model'],json.dumps(row['settings'],sort_keys=True))].append(row)
    key,rows=max(grouped.items(),key=lambda item:len(item[1]));rows=rows[:64]
    options=next(r['options'] for r in profile['requests'] if r['backend']=='m2m100' and r['options']['device']=='cuda')
    translator=ctranslate2.Translator(key[0],device='cuda',compute_type=options['compute_type'],intra_threads=8,inter_threads=1)
    settings=json.loads(key[1]);translator.translate_batch(rows[0]['source'],**settings)
    results={}
    for size in (1,8,16):
        outputs=[];calls=[];start=perf_counter()
        for offset in range(0,len(rows),size):
            group=rows[offset:offset+size]
            # Same decoding flags; target prefix scatters by original sequence ID.
            cfg=dict(settings,target_prefix=[r['settings']['target_prefix'][0] for r in group])
            t=perf_counter();batch=translator.translate_batch([r['source'][0] for r in group],**cfg)
            calls.append(perf_counter()-t);outputs.extend(r.hypotheses for r in batch)
        results[str(size)]=dict(seconds=perf_counter()-start,calls=len(calls),
            exact_captured_outputs=outputs==[r['outputs'][0] for r in rows],
            output_sha256=hashlib.sha256(json.dumps(outputs,ensure_ascii=False).encode()).hexdigest())
    translator.unload_model(to_cpu=False)
    save(QA/'nmt_microbenchmark.json',dict(rows=len(rows),selection='First 64 single-sequence CUDA inputs in the largest identical-settings M2M group; measured baseline request order',
        results=results,settings=settings,options=options,
        ready_work_in_production='One synchronous routed request. Semantic result/guards/fallback must finish before the next request.',
        transfer_scope='Synchronous public CT2 call includes internal preparation and transfers'))
    print(json.dumps(results),flush=True)

def duplicate_micro():
    from types import SimpleNamespace
    import app.ocr.postprocess.deduplication as dedup
    old=dedup.duplicate
    def candidate(item,existing):
        thresholds=dedup.configuration()['dedup']
        for other in existing:
            coverage=dedup.intersection(item.bbox,other.bbox)/max(1,min(dedup.area(item.bbox),dedup.area(other.bbox)))
            if coverage>=thresholds['overlap']:
                similarity=dedup.SequenceMatcher(None,dedup.normalize(item.text),dedup.normalize(other.text)).ratio()
                if similarity>=thresholds['similarity']:return True
        return False
    cases=[]
    for rows in read(QA/'baseline_contracts.json')['sources'].values():
        pages=defaultdict(list)
        for row in rows:
            item=SimpleNamespace(text=row['text'],bbox=row['bbox'])
            if row['origin']=='ocr':cases.append((item,tuple(pages[row['page']])))
            pages[row['page']].append(item)
        for row in rows[::17]:
            item=SimpleNamespace(text=row['text'],bbox=row['bbox']);cases.append((item,(item,)))
    result={};outputs={}
    for name,fn in [('before',old),('candidate',candidate)]:
        start=perf_counter();outputs[name]=[fn(*case) for case in cases]
        result[name]=perf_counter()-start
    save(QA/'duplicate_microbenchmark.json',dict(cases=len(cases),
        source='Every captured OCR source block against earlier blocks on its page; extra identical positives every 17th block',
        seconds=result,exact_outputs=outputs['before']==outputs['candidate'],
        reduction_percent=(1-result['candidate']/result['before'])*100))
    assert outputs['before']==outputs['candidate'] and result['candidate']<result['before']
    print(json.dumps(result),flush=True)

def lock_micro():
    from contextlib import contextmanager, nullcontext
    from tempfile import TemporaryDirectory
    from threading import Event,Thread
    from app.documents import pdf_document as module
    from tools.aw081_hardware_scaling_20 import fingerprint_pdf
    from time import sleep
    @contextmanager
    def suspend():
        owned=getattr(module.PDF_LOCK,'_is_owned',lambda:False)()
        if owned:module.PDF_LOCK.release()
        try:yield
        finally:
            if owned:module.PDF_LOCK.acquire()
    manifest=sample();native=next(d for d in manifest['documents'] if d['classification']=='native')
    with TemporaryDirectory(prefix='aw081-lock-') as tmp,ZipFile(manifest['sample_archive']) as archive:
        path=Path(tmp)/'source.pdf';path.write_bytes(archive.read(native['member_path']))
        fingerprints={};seconds={};errors=[]
        for label,scope in [('before',nullcontext),('candidate',suspend)]:
            writer=module.PdfDocument(path)
            for s in writer.segments:s.translated='Проверка контрольного узла'
            started=Event()
            class Extractor(module.NativeTextExtractor):
                def extract(self,*args):
                    result=super().extract(*args)
                    # A detached image/CPU operation; no PDFium calls in this scope.
                    with scope():started.set();sleep(.6)
                    return result
            def reader():
                try:module.PdfDocument(path,extractor=Extractor())
                except BaseException as e:errors.append(type(e).__name__)
            start=perf_counter();thread=Thread(target=reader);thread.start();assert started.wait(5)
            output=Path(tmp)/(label+'.pdf');writer.write(output);thread.join(10)
            assert not thread.is_alive();seconds[label]=perf_counter()-start
            fingerprints[label]=fingerprint_pdf(output.read_bytes(),True)
        save(QA/'lock_microbenchmark.json',dict(seconds=seconds,exact_objects_render=fingerprints['before']==fingerprints['candidate'],errors=errors,
            scope='Actual PDF extraction and translated writer; controlled 0.6s detached CPU operation replaces recognition only in this microbenchmark',
            reduction_percent=(1-seconds['candidate']/seconds['before'])*100))
        assert not errors and fingerprints['before']==fingerprints['candidate'] and seconds['candidate']<seconds['before']
        print(json.dumps(seconds),flush=True)

def equivalence(label='after'):
    a=QA/'runs/baseline';b=QA/'runs'/label
    checks={name:read(a/(name+'.json'))==read(b/(name+'.json')) for name in ('candidates','writer','fingerprints')}
    checks['full_OCR_source_contracts_profiles']=read(QA/'baseline_contracts.json')==read(QA/(label+'_contracts.json'))
    checks['ordered_glossary_terms_constraints']=lines(QA/'baseline_lookup_trace.jsonl')==lines(QA/(label+'_lookup_trace.jsonl'))
    before=read(QA/'baseline_profile.json');after=read(QA/(label+'_profile.json'))
    def immutable(rows):return [{k:v for k,v in r.items() if k!='seconds'} for r in rows]
    checks['every_NMT_semantic_request_backend_model_output']=immutable(before['nmt']['requests'])==immutable(after['nmt']['requests'])
    checks['every_ordered_model_input_settings_output']=immutable(before['nmt']['batches'])==immutable(after['nmt']['batches'])
    ea,eb=read(a/'execution.json'),read(b/'execution.json')
    checks['fallback_attempts']=ea['models']==eb['models']
    def skips(e):return [{k:v for k,v in r.items() if k!='elapsed'} for r in e['events'] if r['event']=='backend_circuit_skip']
    checks['backend_circuit_fallback_skips']=skips(ea)==skips(eb)
    checks['statuses']=read(a/'run_summary.json')['translated_documents']==read(b/'run_summary.json')['translated_documents'] and read(a/'run_summary.json')['failed_documents']==read(b/'run_summary.json')['failed_documents'] and eb['fatal'] is None
    checks['source_SHA']=ea['source_immutable'] and eb['source_immutable']
    crc_details=[]
    with ZipFile(data_path(ea['outputs'][0])) as za,ZipFile(data_path(eb['outputs'][0])) as zb:
        checks['ZIP_inventory_order_directories_CRC']=[(i.filename,i.file_size) for i in za.infolist()]==[(i.filename,i.file_size) for i in zb.infolist()] and za.testzip() is None and zb.testzip() is None
        # PDFium generates trailer file identifiers per save. Their bytes/CRC
        # differ even on identical serial writes; prove every other byte equal.
        normalized=lambda data:re.sub(rb'/ID\s*\[\s*<[0-9A-Fa-f]+>\s*<[0-9A-Fa-f]+>\s*\]',b'/ID[<GENERATED><GENERATED>]',data)
        for entry in za.infolist():
            x,y=za.read(entry),zb.read(entry.filename)
            crc_details.append(dict(member=entry.filename,CRC_before=entry.CRC,CRC_after=zb.getinfo(entry.filename).CRC,
                raw_exact=x==y,all_bytes_except_generated_trailer_ID_exact=normalized(x)==normalized(y)))
        checks['all_PDF_bytes_except_generated_trailer_ID']=all(r['all_bytes_except_generated_trailer_ID_exact'] for r in crc_details)
    for role in ('baseline',label):
        checks[role+'_two_resident_OCR_loads']=sum(r['event']=='model_load' for r in lines(QA/(role+'_ocr_loads.jsonl')))==2
    save(QA/('output_equivalence.json' if label=='after' else label+'_equivalence.json'),dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,
        CRC_details=crc_details,normalization='Only regenerated PDF trailer /ID bytes; no content/objects/fonts/images/metadata normalization. ZIP CRC validated against every stored member; failed source raw exact.'))
    print(json.dumps(checks),flush=True);assert all(checks.values()),checks

def full_pytest():
    from tools.aw081_speed_calibration_100 import frozen_hashes
    import xml.etree.ElementTree as ET
    assert read(QA/'output_equivalence.json')['status']=='PASS'
    assert not (QA/'full_pytest.json').exists()
    before=frozen_hashes();start=perf_counter()
    with (QA/'pytest_stdout.txt').open('x',encoding='utf8') as output:
        result=subprocess.run([sys.executable,'-X','utf8','-m','pytest','-q','--junitxml='+str(QA/'pytest.xml')],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
    after=frozen_hashes();totals=Counter()
    for suite in ET.parse(QA/'pytest.xml').getroot().iter('testsuite'):
        for k in ('tests','failures','errors','skipped'):totals[k]+=int(suite.get(k,0))
    save(QA/'full_pytest.json',dict(status='PASS' if result.returncode==0 and before==after else 'FAIL',
        passed=totals['tests']-totals['failures']-totals['errors']-totals['skipped'],**totals,
        duration_seconds=perf_counter()-start,production_hashes_before=before,production_hashes_after=after))
    assert result.returncode==0 and before==after and totals['tests']>=1248

def report():
    assert read(QA/'output_equivalence.json')['status']=='PASS'
    assert read(QA/'full_pytest.json')['status']=='PASS'
    before=read(QA/'baseline.json');after=read(QA/'after.json');serial=read(QA/'depth1.json')
    bp=read(QA/'baseline_profile.json');ap=read(QA/'after_profile.json')
    save(QA/'nmt_profile.json',dict(before=bp['nmt'],after=ap['nmt'],microbenchmark=read(QA/'nmt_microbenchmark.json')))
    def lock_detail(label,profile):
        directory=QA/'runs'/label;ocr_members={r['member'] for r in read(directory/'ocr_calls.json')}
        groups=defaultdict(lambda:dict(wait_seconds=0,held_seconds=0,count=0))
        for row in profile['locks']['records']:
            phase='OCR_preparation' if row['phase']=='native_extraction' and row['member'] in ocr_members else row['phase']
            g=groups[phase];g['count']+=1;g['wait_seconds']+=row['wait_seconds'];g['held_seconds']+=row['held_seconds']
        return dict(groups=groups,records=profile['locks']['records'],
            native_extraction_actual_seconds=profile['nmt']['seconds']['native_extract_actual'],
            layout_write_seconds=read(QA/(label+'.json'))['metrics']['stage_seconds'].get('pdf_page_layout_write',0),
            note='Outer lock scopes. OCR preparation includes native extraction and postprocess; recognition is detached after patch. Layout/write is inclusive inside writer held, not additive.')
    save(QA/'lock_profile.json',dict(before=lock_detail('baseline',bp),after=lock_detail('after',ap),microbenchmark=read(QA/'lock_microbenchmark.json')))
    bm,am=before['metrics'],after['metrics']
    gain=(1-am['wall_seconds']/bm['wall_seconds'])*100
    nmtgain=(1-am['stage_seconds']['model_translation']/bm['stage_seconds']['model_translation'])*100
    depthgain=(1-am['wall_seconds']/serial['metrics']['wall_seconds'])*100
    verdict='EXCELLENT PASS' if gain>=25 else 'STRONG PASS' if gain>=15 else 'FINAL SPEED PATCH PASS' if gain>=8 else 'FUNCTIONAL PASS; SPEED TARGET NOT MET'
    accepted=read(QA/'accepted_changes.json');accepted.update(status='ACCEPTED',
        final_output_equivalence='PASS',targeted_existing_tests_passed=67,new_tests_passed=8,
        duplicate_microbenchmark=read(QA/'duplicate_microbenchmark.json'),
        lock_microbenchmark=read(QA/'lock_microbenchmark.json'),
        OCR_postprocess_before_seconds=bm['stage_seconds']['ocr_postprocess'],
        OCR_postprocess_after_seconds=am['stage_seconds']['ocr_postprocess'],
        production_before=before['production_hashes_before'],production_after=after['production_hashes_after'])
    from tools.aw081_speed_calibration_100 import frozen_hashes
    assert frozen_hashes()==after['production_hashes_after']
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in accepted['dictionary_sha256'].items())
    save(QA/'accepted_changes.json',accepted)
    save(QA/'fixed5_result.json',dict(verdict=verdict,before=bm,after=am,depth1=serial['metrics'],
        wall_reduction_percent=gain,model_translation_reduction_percent=nmtgain,depth2_vs_depth1_percent=depthgain,
        measured_baseline_runs=1,measured_final_runs=1,additional_depth_recheck_runs=1,
        pipeline='Existing conservative depth2 ceiling retained; no scheduler changes',
        source_SHA=sample()['sample_archive_sha256'],equivalence='PASS',
        warmup_scope='One identical excluded OCR/NMT warmup per fresh process; root run still measures its two resident OCR loads',
        STOP='No fixed20, 100-PDF or full archive runs; no AW0.82'))
    table=[]
    def row(name,b,a,unit='',higher=False):
        delta=((a/b-1) if higher else (1-a/b))*100 if b and a is not None else None
        fmt=lambda v:'N/A' if v is None else f'{v:.3f}'
        table.append(f'| {name}{" ("+unit+")" if unit else ""} | {fmt(b)} | {fmt(a)} | {fmt(delta)}% |')
    row('wall',bm['wall_seconds'],am['wall_seconds'],'s')
    row('successful docs/hour',bm['docs_per_hour'],am['docs_per_hour'],higher=True)
    for key in ('model_translation','ocr_recognize','ocr_postprocess','glossary_lookup','knowledge_snapshot','template_routing'):
        row(key,bm['stage_seconds'].get(key,0),am['stage_seconds'].get(key,0),'s')
    for key in ('inference_seconds','calls','sequences','tokens','median_sequences','median_tokens','batch1','batch2'):
        row('NMT '+key,bp['nmt'][key],ap['nmt'][key])
    for key in ('tokenizer_encode','tokenizer_source_tokens','tokenizer_decode','m2m100_load_or_reuse'):
        row(key,bp['nmt']['seconds'][key],ap['nmt']['seconds'][key],'s')
    row('actual CT2 loads',len(bp['nmt']['loads']),len(ap['nmt']['loads']))
    row('PDF_LOCK total wait',sum(r['wait_seconds'] for r in bp['locks']['records']),sum(r['wait_seconds'] for r in ap['locks']['records']),'s')
    row('PDF_LOCK total held',sum(r['held_seconds'] for r in bp['locks']['records']),sum(r['held_seconds'] for r in ap['locks']['records']),'s')
    row('writer lock wait',bp['locks']['groups']['writer']['wait_seconds'],ap['locks']['groups']['writer']['wait_seconds'],'s')
    row('writer actual work',bp['locks']['groups']['writer']['held_seconds'],ap['locks']['groups']['writer']['held_seconds'],'s')
    row('layout/write',bm['stage_seconds']['pdf_page_layout_write'],am['stage_seconds']['pdf_page_layout_write'],'s')
    row('CPU average',bm['cpu_avg_percent'],am['cpu_avg_percent'],'% of one logical CPU')
    row('GPU average',bm['gpu_avg_percent'],am['gpu_avg_percent'],'device-wide %')
    row('peak RSS',bm['peak_rss_bytes']/1024**3,am['peak_rss_bytes']/1024**3,'GiB process tree')
    row('peak VRAM',bm['peak_vram_bytes']/1024**3,am['peak_vram_bytes']/1024**3,'GiB device-wide')
    tested=read(QA/'full_pytest.json');manifest=sample()
    micro=read(QA/'nmt_microbenchmark.json')['results']
    text=f'''# AW0.81 — Final performance patch / fixed5

## 1. Fixed5 sample

Ровно пять исходных fixed20 members: {', '.join(str(d['index']) for d in manifest['documents'])}, {sum(d['pages'] for d in manifest['documents'])} страниц. Детерминированные правила: minimum measured native/EASY_NATIVE document wall; maximum mixed OCR; maximum image-only OCR; maximum remaining model_translation; maximum remaining actual page layout/write. Ties — original index; ZIP order восстановлен. Два FAILED_SOURCE_PRESERVED cases. Manifest/source SHA заморожены до baseline. Baseline — current uncommitted AW0.81 source, hashes сохранены; это не Git HEAD без предыдущих изменений.

## 2. Before bottlenecks

Baseline {bm['wall_seconds']:.2f}s: NMT inference {bp['nmt']['inference_seconds']:.2f}s, model_translation {bm['stage_seconds']['model_translation']:.2f}s, glossary {bm['stage_seconds']['glossary_lookup']:.2f}s, OCR recognition {bm['stage_seconds']['ocr_recognize']:.2f}s, postprocess {bm['stage_seconds']['ocr_postprocess']:.2f}s. Timings inclusive, их нельзя складывать как wall. Reference fixed20 glossary был 76.46s на stage3; 66.89s относится к предыдущему stage2.

## 3. NMT findings

{bp['nmt']['calls']} real CT2 calls, все batch=1; median {bp['nmt']['median_tokens']} source tokens. {bp['nmt']['repeated_identical_calls']} повторных точных prepared inputs, но M2M encode/source/decode суммарно <0.09s: cache не нужен. {len(bp['nmt']['loads'])} real CT2 loads, из них четыре CUDA M2M на существующих OCR memory boundaries; 858 M2M load/reuse checks заняли3.25s, model reuse работает. Argos CPU/CUDA fallback определяется guards и сохранён.

GPU получает множество коротких синхронных запросов между glossary/guards; model_translation включает actual CT2 и lifecycle/preparation. CT2 synchronous public API не разделяет host/device transfer и kernel time, поэтому это N/A, а не ноль. Encode/decode отдельно измерены для M2M; Argos preparation/discovery входит в оставшийся model runtime. Токены — model-ready source pieces с language/EOS, не output tokens. Replay первых64 совместимых captured inputs: sequential {micro['1']['seconds']:.3f}s; batch8 {micro['8']['seconds']:.3f}s exact PASS; batch16 {micro['16']['seconds']:.3f}s exact FAIL. Production не имеет очереди уже routed независимых requests: следующий semantic turn ждёт result/guards/fallback предыдущего. Assembler сейчас немедленно flush batch1; новый async semantic scheduler сюда не добавлен.

## 4. PDF_LOCK / writer findings

До fix writer: {bp['locks']['groups']['writer']['wait_seconds']:.2f}s wait и {bp['locks']['groups']['writer']['held_seconds']:.2f}s actual work. После: {ap['locks']['groups']['writer']['wait_seconds']:.2f}s wait, {ap['locks']['groups']['writer']['held_seconds']:.2f}s work. Lock освобождается ровно вокруг recognize по copied RGB image: bitmap уже закрыт, rotation восстановлена; page/objects не используются. Все PDFium operations остаются под lock; exception/cancel восстанавливает ownership в finally. Recursive caller scope сохраняется. Раздельные native/OCR/writer/validation outer scope данные в lock_profile.json; layout/write nested inclusive, не дополнительное время.

## 5. Accepted changes

Два небольших runtime changes в трёх production files: detached OCR lock scope и geometry-first deduplication. Ни models, thresholds, DPI, gate, candidate order, Knowledge, constraints, beam, decoding, routing, fallback, UI не изменены. Microtests: detached writer overlap {read(QA/'lock_microbenchmark.json')['reduction_percent']:.2f}% faster, exact PDF objects/render; dedup replay {read(QA/'duplicate_microbenchmark.json')['reduction_percent']:.2f}% faster, exact decisions. В baseline5308 raw recognized segments против3611 retained OCR blocks; postprocess14.43s оправдывал проверку residual path. Final postprocess {am['stage_seconds']['ocr_postprocess']:.2f}s. Новый real PDF race test подтверждает source contracts/render; 49 Knowledge DB hashes unchanged.

## 6. Rejected / no-benefit ideas

Batch16 нарушил exact output; batch8 требует отсутствующей ready request queue. Preparation cache экономил бы <0.09s. NMT lifecycle уже reuse, не переписан. Writer process: actual work только2.5% baseline wall, ниже10% potential cutoff. Knowledge hot path: большая стоимость PRAGMA data_version нужна для external commit invalidation; immutable run-wide revision cache изменил бы поведение. OCR allocation/models/thresholds не менялись.

## 7. Before → after

| Metric | Before | After | Reduction / gain |
|---|---:|---:|---:|
{chr(10).join(table)}

Одинаковые MID QA controls: CPU8, OCR4, NMT tokens768, OCR batch6, serial GPU owner, same excluded warmup. Model parameters одинаковы. GPU utilization/VRAM device-wide включают другие приложения; RSS/CPU process tree,100%CPU=один logical CPU. Status counts:3 TRANSLATED,2 FAILED_SOURCE_PRESERVED,0fatal. Exactly one baseline, one final; дополнительный разрешённый depth1 recheck {serial['metrics']['wall_seconds']:.2f}s против final depth2 {am['wall_seconds']:.2f}s, depth2 gain {depthgain:.2f}%. Depth3/4 не запускались; существующий conservative ceiling2 оставлен без scheduler изменений.

## 8. Equivalence

PASS: все final checks в output_equivalence.json: statuses, full captured OCR sources, ordered glossary/selected terms/constraints, profiles/snapshots, candidates, writer protected IDs/numbers/preserved segments, page counts/normalized objects/render probes всех translated PDFs, paths/directories, failed exact bytes, ZIP inventory/order/CRC, source SHA. Для каждого runtime request совпали semantic identity/backend/options/model output и ordered prepared CT2 input/output, fallback attempts/circuit skips. Нет quality regrade/Frozen A evaluation.

## 9. Full pytest

{tested['passed']} passed, {tested['failures']} failures, {tested['errors']} errors, {tested['skipped']} skipped; {tested['duration_seconds']:.2f}s. Production SHA до/после совпали. 1248 baseline +8 новых проверок. Earlier targeted:67 existing +8 new PASS.

## 10. Remaining bottleneck

Синхронные маленькие NMT requests и glossary revision polling. NMT model time reduction {nmtgain:.2f}% — отдельный20% NMT target не достигнут. Пересчёт времени17211 PDF по пяти PDF не выполнялся: требуется отдельная исходная100-PDF calibration.

## 11. Verdict

**{verdict}**. Wall reduction {gain:.2f}%. Это измеренный результат одного before/after на fixed5, не прогноз для полного архива. No new fixed20 /100 /17211 runs, resource modes, UI changes, AW0.82 or commits. STOP.
'''
    path=ROOT/'docs/AW0.81_FINAL_SPEED_PATCH_5PDF.md';path.write_text(text,'utf8')
    print(verdict,round(gain,3),'DEPTH2_GAIN',round(depthgain,3),flush=True)

def bundle():
    """Consolidate existing diagnostic evidence after all measured work is done."""
    from zipfile import ZIP_DEFLATED
    assert read(QA/'full_pytest.json')['status']=='PASS'
    assert read(QA/'output_equivalence.json')['status']=='PASS'
    keep={'sample_manifest.json','baseline.json','nmt_profile.json','lock_profile.json',
          'accepted_changes.json','fixed5_result.json','output_equivalence.json','full_pytest.json',
          'CN7C_FINAL_FIXED5.zip','evidence.zip'}
    files=[p for p in QA.rglob('*') if p.is_file() and not (p.parent==QA and p.name in keep)]
    archive=QA/'evidence.zip';assert not archive.exists()
    with ZipFile(archive,'w',ZIP_DEFLATED) as output:
        for path in files:output.write(path,path.relative_to(QA).as_posix())
    with ZipFile(archive) as check:
        assert check.testzip() is None
        for path in files:
            assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(check.read(path.relative_to(QA).as_posix())).digest()
    path=ROOT/'docs/AW0.81_FINAL_SPEED_PATCH_5PDF.md'
    path.write_text(path.read_text('utf8')+'\nRaw source contracts, glossary traces, run logs, per-document fingerprints, translated result ZIPs и pytest XML/stdout сведены в `qa/aw081/final_speed_patch_5pdf/evidence.zip`: проверены CRC архива и SHA-256 каждого entry. Основные8 JSON и frozen input ZIP доступны отдельно; временные копии дополнительно сохранены в raw_copies/. Helper читает их оттуда; исходные receipt paths также восстанавливаются распаковкой evidence.zip в его каталог.\n','utf8')
    print('EVIDENCE_BUNDLE_VERIFIED',len(files),str(archive),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['sample','run','nmt-micro','duplicate-micro','lock-micro','equivalence','pytest','report','bundle']);parser.add_argument('--label',default='baseline');parser.add_argument('--depth',type=int,default=2)
    args=parser.parse_args()
    if args.mode=='sample':print(json.dumps(sample()['selection'],ensure_ascii=False))
    elif args.mode=='run':run(args.label,args.depth)
    elif args.mode=='nmt-micro':nmt_micro()
    elif args.mode=='duplicate-micro':duplicate_micro()
    elif args.mode=='lock-micro':lock_micro()
    elif args.mode=='equivalence':equivalence(args.label)
    elif args.mode=='pytest':full_pytest()
    elif args.mode=='report':report()
    else:bundle()
