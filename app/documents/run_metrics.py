"""Opt-in local, content-safe streaming diagnostics; never a quality scorer.

Counters use completed semantic blocks, not internal lookup/model call totals.
Stage times are inclusive. SQLite supports bounded-memory aggregation/sampling;
JSONL is flushed at each document checkpoint and at least every second.
"""
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from threading import RLock
from hashlib import sha256
import ctypes
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import traceback
from time import perf_counter, time
from uuid import uuid4

_run = ContextVar('local_metrics_run', default=None)
_doc = ContextVar('local_metrics_document', default=None)
_segment = ContextVar('local_metrics_segment', default=None)
logger = logging.getLogger('treetranslate.metrics')
STREAMS = ('documents','stages','routing','warnings','errors','knowledge_frontier','resource_samples','archive_events')
CATEGORIES = frozenset('SOURCE_DAMAGED SOURCE_AMBIGUOUS UNSUPPORTED_STRUCTURE PDF_EXTRACTION OCR_FAILURE READING_ORDER SEGMENTATION TABLE_RECONSTRUCTION KNOWLEDGE_GAP AMBIGUOUS_TERM ROUTER_ERROR TEMPLATE_REJECTION MODEL_FALLBACK MODEL_LIMITATION ACTION_GUARD NEGATION_GUARD CONDITION_GUARD OBJECT_GUARD UNIT_GUARD OUTPUT_WRITER VALIDATION ARCHIVE_SECURITY ARCHIVE_IO OUT_OF_MEMORY UNKNOWN_INTERNAL_ERROR'.split())

def content_hash(text):return sha256(text.encode('utf8',errors='surrogatepass')).hexdigest()

def file_hash(path):
    result=sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()

def current():return _run.get()

def _safe(method,*args,**kwargs):
    """Logging errors cannot change translation or mask its exception."""
    try:return method(*args,**kwargs)
    except Exception as error:
        observer=current()
        if observer:observer.logging_failed=True
        logger.warning('local_metrics_failed operation=%s type=%s',method.__name__,type(error).__name__)
        return None

def resource_sample():
    result=dict(rss_bytes=None,peak_rss_bytes=None,available_ram_bytes=None,peak_vram_bytes=None,
                vram_status='unavailable: CUDA allocator not initialized')
    if os.name=='nt':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak_working_set','working_set','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
        class Memory(ctypes.Structure):
            _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(n,ctypes.c_ulonglong) for n in ('total_physical','available_physical','total_pagefile','available_pagefile','total_virtual','available_virtual','extended')]
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.GetCurrentProcess.restype=wintypes.HANDLE
        psapi=ctypes.WinDLL('psapi',use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
            result.update(rss_bytes=counters.working_set,peak_rss_bytes=counters.peak_working_set)
        memory=Memory();memory.length=ctypes.sizeof(memory)
        if kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):result['available_ram_bytes']=memory.available_physical
    else:
        try:
            import resource
            result['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        except ImportError:pass
    torch=sys.modules.get('torch')
    if torch and torch.cuda.is_initialized():
        result.update(peak_vram_bytes=torch.cuda.max_memory_allocated(),vram_status='allocator peak, process-local')
    return result

def category(error,stage=''):
    name=type(error).__name__
    if isinstance(error,MemoryError) or 'OutOfMemory' in name:return 'OUT_OF_MEMORY'
    if 'SourceChanged' in name:return 'VALIDATION'
    if 'Ocr' in name:return 'OCR_FAILURE'
    if isinstance(error,IndexError):return 'UNSUPPORTED_STRUCTURE'
    if 'Translation' in name:return 'MODEL_LIMITATION'
    if 'valid' in stage.lower():return 'VALIDATION'
    if 'Pdf' in name:return 'OUTPUT_WRITER' if 'write' in stage else 'PDF_EXTRACTION'
    if 'archive' in stage:return 'ARCHIVE_IO'
    return 'UNKNOWN_INTERNAL_ERROR'

def document_error_record(item,error,stage,elapsed,source_hash):
    """Content-free failure evidence, including unknown exception stack locations."""
    diagnostic=getattr(error,'diagnostic',None) or {}
    stage=diagnostic.get('stage',stage)
    primary=category(error,stage.lower())
    secondary=[]
    if isinstance(error,IndexError):secondary.append('UNKNOWN_INTERNAL_ERROR')
    if 'Translation' in type(error).__name__ and 'отрицатель' in str(error).lower():
        primary='UNIT_GUARD';secondary.append('MODEL_LIMITATION')
    return dict(document_id=content_hash(str(item.archive)+'\0'+item.relative.as_posix())[:24],
        member_path=item.relative.as_posix(),source_sha256=source_hash,stage=stage,
        primary_category=primary,secondary_categories=secondary,exception_type=type(error).__name__,
        elapsed_seconds=elapsed,original_member_preserved=False,
        diagnostic={k:diagnostic[k] for k in ('page','object_index','native_code') if isinstance(diagnostic.get(k),(int,float))},
        error_frames=[dict(file=f.filename,line=f.lineno,function=f.name)
                      for f in traceback.extract_tb(error.__traceback__)[-8:]])

@dataclass
class DocumentMetrics:
    document_id:str
    data:dict
    started:float=field(default_factory=perf_counter)
    counters:Counter=field(default_factory=Counter)
    stages:dict=field(default_factory=dict)
    phase_started:float=field(default_factory=perf_counter)
    active_seconds:float=0.
    frontier:dict=field(default_factory=dict)
    unknown_hashes:set=field(default_factory=set)
    engine_before:dict=field(default_factory=dict)

def serialized_metrics(method):
    """One storage owner at a time; document ContextVars remain task-local."""
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._storage_lock:
            return method(self, *args, **kwargs)
    return call


class LocalRun:
    def __init__(self,directory,*,run_id=None,metadata=None):
        self._storage_lock = RLock()
        self.run_id=run_id or uuid4().hex
        self.directory=Path(directory)/self.run_id
        self.directory.mkdir(parents=True,exist_ok=False)
        self.started=perf_counter();self.logging_failed=False;self.last_flush=self.started
        self.streams={n:(self.directory/(n+'.jsonl')).open('x',encoding='utf8',buffering=65536) for n in STREAMS}
        self.database=sqlite3.connect(self.directory/'index.sqlite3', check_same_thread=False)
        self.database.execute('PRAGMA journal_mode=WAL');self.database.execute('PRAGMA synchronous=NORMAL')
        self.database.executescript('CREATE TABLE documents(id TEXT PRIMARY KEY, seconds REAL, payload TEXT); CREATE TABLE frontier(hash TEXT PRIMARY KEY, payload TEXT); CREATE TABLE archives(source TEXT PRIMARY KEY, output TEXT, sha256 TEXT);')
        self.pending={};self.totals=Counter();self.archive_counters=Counter();self.run_stages={};self.peak_temporary_bytes=0
        self.manifest=dict(schema=1,run_id=self.run_id,status='RUNNING',started_at_unix=time(),metadata=metadata or {},
            local_only=True,telemetry=False,source_snippets=False,frontier_policy='Only bounded technical nominal candidates; unverified local proposals, never automatically published.',
            timing_policy='Inclusive stage times. Do not sum nested stages.',flush_policy='Per document and at least every second; torn final JSONL record may be ignored after a hard crash.',
            recovery_policy='Document failures preserve original members and continue; archive/global failures are fatal and atomic. No silent retry/resume.')
        self._json('run_manifest.json',self.manifest)
        self.emit('resource_samples',dict(event='start',**resource_sample()));self.flush()

    @serialized_metrics
    def _json(self,name,value):
        target=self.directory/name;temporary=target.with_suffix(target.suffix+'.tmp')
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(temporary,target)

    @contextmanager
    def activate(self):
        token=_run.set(self);doc_token=_doc.set(None);seg_token=_segment.set(None)
        try:yield self
        finally:_segment.reset(seg_token);_doc.reset(doc_token);_run.reset(token)

    @serialized_metrics
    def emit(self,stream,value):
        if self.logging_failed:return
        row=dict(run_id=self.run_id,document_id=getattr(_doc.get(),'document_id',None));row.update(value)
        self.streams[stream].write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
        if perf_counter()-self.last_flush>=1:self.flush()

    @serialized_metrics
    def flush(self):
        for stream in self.streams.values():stream.flush()
        self.database.commit();self.last_flush=perf_counter()

    @serialized_metrics
    def start_document(self,item,config,engine=None):
        key=str(item.path)
        doc_id=content_hash((str(item.archive or item.root or item.path.parent)+'\0'+item.relative.as_posix()))[:24]
        doc=DocumentMetrics(doc_id,dict(archive_member_path=item.relative.as_posix(),source_path=None if item.archive else str(item.path),
            source_archive_path=str(item.archive) if item.archive else None,source_archive_sha256=item.archive_hash or None,
            source_size=item.size,file_type=item.path.suffix.lower().lstrip('.'),source_sha256=None,source_language=config.source,
            target_language=config.target,requested_device=config.device.value,output_status='PROCESSING',source_immutable=None,
            profiler=None,source_pages=None,output_pages=None,protected_tokens=0,layout_status='NOT_EVALUATED'))
        contextual=getattr(engine,'context_router',None)
        if contextual:doc.engine_before=dict(contextual.metrics)
        self.pending[key]=doc;_doc.set(doc)
        self.emit('routing',dict(event='document_started',document_id=doc_id));self.flush()
        return doc

    @serialized_metrics
    def pause_document(self):
        doc=_doc.get()
        if doc:doc.active_seconds+=perf_counter()-doc.phase_started
        _doc.set(None)

    @serialized_metrics
    def resume_document(self,item):
        doc=self.pending.get(str(item.path));_doc.set(doc)
        if doc:doc.phase_started=perf_counter()

    @serialized_metrics
    def extracted(self,document,source,target,profile,extractor=None):
        doc=_doc.get()
        if not doc:return
        segments=document.segments
        native=sum(getattr(s,'origin','native')!='ocr' for s in segments);ocr=len(segments)-native
        summary=profile.summary() if profile else {}
        doc.data.update(source_sha256=document.source_hash,source_language=source,target_language=target,
            source_pages=len(getattr(document,'pages',())),extracted_blocks=len(segments),segments=len(segments),native_segments=native,ocr_segments=ocr,
            classification='mixed' if native and ocr else 'image_only' if ocr else 'native',
            profiler={k:summary[k] for k in ('selected_domain','domain_scores','selected_subdomains','confidence','document_types','content_types','semantic_facts','version') if k in summary},
            ocr_pages=len({s.page for s in segments if getattr(s,'origin','native')=='ocr'}),
            ocr_regions=getattr(getattr(extractor,'delegate',extractor),'region_count',None),
            ocr_low_confidence_segments=sum(getattr(s,'origin','native')=='ocr' and (getattr(s,'confidence',None) or 0)<.65 for s in segments),
            table_blocks=sum(getattr(s,'region_kind','')=='table_cell' for s in segments),
            schematic_blocks=sum(getattr(s,'region_kind','')=='diagram' for s in segments),
            suspicious_encoding_segments=sum('\ufffd' in s.text or any(0xD800<=ord(c)<=0xDFFF for c in s.text) for s in segments),
            missing_content_pages=None,reading_order_candidates=None,table_reconstruction_warnings=None)
        if extractor:
            timings=getattr(getattr(extractor,'delegate',extractor),'timings',())
            doc.data['ocr_region_timings']=dict(regions=len(timings),ocr_seconds=sum(t.get('ocr_seconds',0) for t in timings),render_seconds=sum(t.get('render_seconds',0) for t in timings))

    @serialized_metrics
    def stage(self,name,seconds,state='ok',page=None,block=None):
        doc=_doc.get();stages=doc.stages if doc else self.run_stages
        entry=stages.setdefault(name,dict(count=0,seconds=0.,failures=0))
        entry['count']+=1;entry['seconds']+=max(0,seconds);entry['failures']+=state!='ok'
        if state!='ok':
            primary='ARCHIVE_SECURITY' if name in {'archive_validate_input','archive_scan'} else 'ARCHIVE_IO' if 'archive' in name else 'OCR_FAILURE' if 'ocr' in name else 'VALIDATION' if 'valid' in name else 'OUTPUT_WRITER' if 'write' in name else 'PDF_EXTRACTION' if 'extract' in name else 'UNKNOWN_INTERNAL_ERROR'
            self.emit('errors',dict(event='stage_failure',stage=name,exception_type=state,primary_category=primary,secondary_categories=[]))

    @serialized_metrics
    def warning(self,message):
        doc=_doc.get()
        if doc:doc.counters['warnings']+=1
        text=message.casefold()
        primary='MODEL_LIMITATION' if 'смысл' in text else 'UNIT_GUARD' if 'числов' in text else 'OUTPUT_WRITER' if 'продолж' in text else 'UNSUPPORTED_STRUCTURE'
        self.emit('warnings',dict(message_sha256=content_hash(message),primary_category=primary,secondary_categories=[],event='warning'))

    @serialized_metrics
    def guards(self,issues):
        mapping={'object':'OBJECT_GUARD','action':'ACTION_GUARD','negation':'NEGATION_GUARD','condition':'CONDITION_GUARD','comparison':'CONDITION_GUARD','number':'UNIT_GUARD','unit':'UNIT_GUARD','question':'ROUTER_ERROR'}
        for issue in issues:
            primary=mapping.get(issue.split(':',1)[0],'MODEL_LIMITATION')
            doc=_doc.get()
            if doc:doc.counters[primary.lower()+'_events']+=1
            self.emit('errors',dict(event='unsafe_translation_rejected',primary_category=primary,secondary_categories=[],detail_sha256=content_hash(issue)))
        segment=_segment.get()
        if segment and issues:segment['unsafe']=True

    @serialized_metrics
    def see_result(self,result):
        segment=_segment.get()
        if not segment:return
        source=getattr(result,'knowledge_source','model');status=getattr(result,'constraint_status','')
        segment['routes'].add(source)
        segment['knowledge']|=source in {'template','tm'} or source=='glossary' and (getattr(result,'glossary_hits_count',0)>0 or status=='full_segment')
        segment['direct']|=getattr(result,'device','none')=='none' and source in {'glossary','template','tm'}
        segment['source_preserved']|=status.startswith('semantic_source_preserved:') or status.endswith('source_title_preserved')
        segment['composition']|=str(getattr(result,'route_reason','')).startswith('compose:')
        segment['cross_reference']|=status.startswith('verified_cross_reference')
        segment['device']=getattr(result,'device','none');segment['backend']=getattr(result,'backend','unknown')
        segment['fallback']|=bool(getattr(result,'fallback_used',False))

    @serialized_metrics
    def model_event(self,backend,device,success,fallback,error_type=None):
        doc=_doc.get()
        if doc:
            doc.counters['model_attempts']+=1
            doc.counters['gpu_attempts']+=device=='cuda';doc.counters['cpu_attempts']+=device=='cpu'
            doc.counters['gpu_fallback_events']+=bool(fallback and device=='cpu')
            doc.counters['gpu_oom_events']+=bool(error_type and ('outofmemory' in error_type.casefold() or 'oom' in error_type.casefold()))
        if not success:self.emit('errors',dict(event='model_attempt_failed',backend=backend,device=device,exception_type=error_type,
            primary_category='OUT_OF_MEMORY' if error_type and ('outofmemory' in error_type.casefold() or 'oom' in error_type.casefold()) else 'MODEL_LIMITATION',secondary_categories=[]))

    @serialized_metrics
    def frontier_candidate(self,source,request,result):
        segment=_segment.get();doc=_doc.get()
        if not segment or not doc or not segment['model'] or len(source)>48 or not re.fullmatch(r'[\u4e00-\u9fff]{2,24}',source):return
        if getattr(request,'domain','')!='automotive' or getattr(request,'segment_type','') not in {'HEADING','COMPONENT_LABEL','DIAGRAM_LABEL','TABLE_HEADER','TABLE_CELL'}:return
        # Only a technical nominal suffix; other Chinese content is not retained.
        if not re.search(r'(?:传感器|控制器|模块|总成|开关|连接器|阀|泵|软管|支架|轴|齿轮|线束|电机|螺栓|盖)$',source):return
        snapshot=getattr(request,'knowledge_snapshot',None)
        if snapshot and any(m.start==0 and m.end==len(source) for m in snapshot.candidates(source,request.domain,request.context,set())):return
        key=content_hash(source);doc.unknown_hashes.add(key)
        item=doc.frontier.setdefault(key,dict(normalized_source_form=source,hash=key,domain=request.domain,subdomains=list((doc.data.get('profiler') or {}).get('selected_subdomains',{})),
            segment_frequency=0,context_count=0,model_fallback_frequency=0,current_candidate_translation=None,confidence=None,confidence_status='unavailable: routing is not semantic confidence',protected=False,oem_identifier=False,noise=False,verified=False,representative_document_ids=[doc.document_id]))
        item['segment_frequency']+=1;item['context_count']+=1;item['model_fallback_frequency']+=1
        target=getattr(result,'translated_text','')
        if len(target)<=160:item['current_candidate_translation']=target

    @serialized_metrics
    def semantic_complete(self, engine=None):
        doc = _doc.get()
        contextual = getattr(engine, 'context_router', None)
        if doc and contextual:
            doc.engine_after = dict(contextual.metrics)

    @serialized_metrics
    def complete_document(self,item,document,output,engine=None):
        doc=_doc.get()
        if not doc:return
        doc.active_seconds+=perf_counter()-doc.phase_started
        output=Path(output)
        doc.data.update(output_status='TRANSLATED',validation_status='PASS',source_immutable=True,output_path=str(output),output_sha256=file_hash(output),output_size=output.stat().st_size,
            output_pages=len(getattr(document,'pages',()))+getattr(document,'continuation_count',0),continuation_pages=getattr(document,'continuation_count',0),
            continuation_blocks=len(getattr(document,'continuations',())),total_wall_seconds=doc.active_seconds,
            latency_seconds=perf_counter()-doc.started,translation_only_seconds=doc.stages.get('pdf_segment_translation',{}).get('seconds',0),
            ocr_seconds=(doc.data.get('ocr_region_timings') or {}).get('ocr_seconds',0),writer_seconds=doc.stages.get('document_write',{}).get('seconds',0),
            unknown_term_candidates=len(doc.unknown_hashes))
        contextual=getattr(engine,'context_router',None)
        if contextual:
            values=getattr(doc, 'engine_after', None) or dict(contextual.metrics)
            doc.data['engine_counter_delta']={k:round(v-doc.engine_before.get(k,0),6) for k,v in values.items() if v!=doc.engine_before.get(k,0)}
        self._finish(doc);self.pending.pop(str(item.path),None);_doc.set(None)

    @serialized_metrics
    def layout_warning(self,findings):
        doc=_doc.get()
        if not doc:return
        doc.data.update(layout_status='WARNING_KNOWN_OVERLAP',known_layout_findings=findings)
        doc.counters['known_layout_warnings']+=len(findings)
        self.emit('warnings',dict(event='known_layout_overlap',primary_category='TABLE_RECONSTRUCTION',
            secondary_categories=['OUTPUT_WRITER'],findings=findings,layout_status='WARNING_KNOWN_OVERLAP'))

    @serialized_metrics
    def document_error(self,record):
        self.emit('errors',dict(event='document_failure',**record));self.flush()

    @serialized_metrics
    def fail_document(self,item,record):
        doc=self.pending.get(str(item.path))
        if not doc:return
        if _doc.get() is doc:doc.active_seconds+=perf_counter()-doc.phase_started
        doc.data.update(output_status='FAILED_SOURCE_PRESERVED',source_sha256=record['source_sha256'],
            source_immutable=True,original_member_preserved=True,failure=record,
            output_sha256=record['source_sha256'],output_size=item.size,
            output_archive_member=item.relative.as_posix(),output_path=None,
            total_wall_seconds=doc.active_seconds,layout_status='NOT_EVALUATED')
        self.emit('errors',dict(event='document_source_preserved',**record))
        self._finish(doc);self.pending.pop(str(item.path),None);_doc.set(None)

    @serialized_metrics
    def _finish(self,doc):
        data=dict(doc.data,document_id=doc.document_id,counters=dict(doc.counters))
        semantic=doc.counters['semantic_segments'];eligible=doc.counters['eligible_semantic_segments']
        data.update(model_fallback_rate=doc.counters['model_fallback_segments']/semantic if semantic else None,
                    knowledge_coverage=doc.counters['knowledge_segments']/eligible if eligible else None)
        self.emit('documents',data)
        for name,value in doc.stages.items():self.emit('stages',dict(document_id=doc.document_id,stage=name,inclusive=True,**value))
        self.emit('routing',dict(document_id=doc.document_id,event='document_totals',**dict(doc.counters)))
        self.database.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?)',(doc.document_id,data.get('total_wall_seconds',0),json.dumps(data,ensure_ascii=False)))
        for key,item in doc.frontier.items():
            old=self.database.execute('SELECT payload FROM frontier WHERE hash=?',(key,)).fetchone()
            aggregate=dict(item,document_frequency=1)
            if old:
                previous=json.loads(old[0]);aggregate['document_frequency']+=previous['document_frequency']
                for field in ('segment_frequency','context_count','model_fallback_frequency'):aggregate[field]+=previous[field]
                aggregate['representative_document_ids']=list(dict.fromkeys(previous['representative_document_ids']+item['representative_document_ids']))[:8]
            self.database.execute('INSERT OR REPLACE INTO frontier VALUES(?,?)',(key,json.dumps(aggregate,ensure_ascii=False)))
            self.emit('knowledge_frontier',dict(event='document_delta',document_id=doc.document_id,**item))
        self.totals.update(doc.counters);self.totals['documents']+=1
        self.totals['written_documents']+=data['output_status']=='TRANSLATED'
        self.totals['failed_documents']+=data['output_status']=='FAILED_SOURCE_PRESERVED'
        self.totals['source_preserved_documents']+=data['output_status']=='FAILED_SOURCE_PRESERVED'
        self.totals['source_bytes']+=data.get('source_size',0);self.totals['output_bytes']+=data.get('output_size',0)
        self.totals['source_pages']+=data.get('source_pages') or 0
        self.emit('resource_samples',dict(event='document_completed',document_id=doc.document_id,**resource_sample()))
        self.flush()

    @serialized_metrics
    def archive_event(self,event,**data):
        if event=='published':
            self.database.execute('INSERT OR REPLACE INTO archives VALUES(?,?,?)',(data['source'],data['output'],data['output_sha256']))
        if event=='summary':
            for key in ('total_documents','translated_documents','failed_documents','source_preserved_documents','skipped_non_documents','fatal_errors'):
                self.archive_counters[key]+=data[key]
            for key,value in data['document_error_categories'].items():
                self.archive_counters['document_category:'+key]+=value
        self.peak_temporary_bytes=max(self.peak_temporary_bytes,data.get('temporary_bytes',0))
        self.archive_counters[event]+=1;self.emit('archive_events',dict(event=event,**data));self.flush()

    @serialized_metrics
    def bind_archive_member(self,source,member,output_member,seconds,temporary_bytes):
        doc_id=content_hash(str(source)+'\0'+member)[:24]
        row=self.database.execute('SELECT payload FROM documents WHERE id=?',(doc_id,)).fetchone()
        if row:
            d=json.loads(row[0]);d.update(output_path=None,output_archive_member=output_member,archive_append_seconds=seconds)
            self.database.execute('UPDATE documents SET payload=? WHERE id=?',(json.dumps(d,ensure_ascii=False),doc_id))
        self.archive_event('member_packaged',document_id=doc_id,source=str(source),source_member=member,output_member=output_member,seconds=seconds,temporary_bytes=temporary_bytes)

    @serialized_metrics
    def close(self,status='COMPLETED',error=None):
        if status=='COMPLETED' and self.totals['failed_documents']:
            status='COMPLETED_WITH_FAILURES'
        if error:
            _safe(self.emit,'errors',dict(event='run_failure',primary_category=category(error),secondary_categories=[],exception_type=type(error).__name__))
        for doc in list(self.pending.values()):
            doc.data.update(output_status='FAILED' if error else 'INCOMPLETE',total_wall_seconds=doc.active_seconds+(perf_counter()-doc.phase_started if _doc.get() is doc else 0))
            _safe(self._finish,doc)
        self.pending.clear();_doc.set(None)
        elapsed=perf_counter()-self.started;total=self.totals['documents']
        distribution={}
        for key,q in [('median',.5),('p90',.9),('p95',.95),('max',1.)]:
            row=self.database.execute('SELECT seconds FROM documents ORDER BY seconds LIMIT 1 OFFSET ?',(max(0,int((total-1)*q+.5)),)).fetchone()
            distribution[key]=row[0] if row else None
        semantic=self.totals['semantic_segments'];eligible=self.totals['eligible_semantic_segments']
        summary=dict(schema=1,run_id=self.run_id,status=status,logging_status='FAILED' if self.logging_failed else 'COMPLETE',total_wall_seconds=elapsed,
            counters=dict(self.totals),archive_events=dict(self.archive_counters),document_seconds=distribution,
            docs_per_hour=self.totals['written_documents']*3600/elapsed,pages_per_hour=self.totals['source_pages']*3600/elapsed,
            segments_per_second=semantic/elapsed,source_mb_per_hour=self.totals['source_bytes']/1048576*3600/elapsed,
            translated_mb_per_hour=self.totals['output_bytes']/1048576*3600/elapsed,
            peak_tracked_temporary_bytes=self.peak_temporary_bytes,temporary_disk_scope='Current extracted/output member plus growing temporary archive; excludes external OCR/runtime caches.',
            model_fallback_rate=self.totals['model_fallback_segments']/semantic if semantic else None,
            knowledge_coverage=self.totals['knowledge_segments']/eligible if eligible else None,quality_score=None,
            coverage_is_not_quality=True,unavailable_metrics=['Missing-content/reading-order detection needs a semantic/layout reviewer; null is not zero.','GPU peak VRAM unavailable until existing CUDA allocator is initialized.'])
        summary.update(total_documents=self.archive_counters.get('total_documents',total),
            translated_documents=self.archive_counters.get('translated_documents',self.totals['written_documents']),
            failed_documents=self.archive_counters.get('failed_documents',self.totals['failed_documents']),
            source_preserved_documents=self.archive_counters.get('source_preserved_documents',self.totals['source_preserved_documents']),
            skipped_non_documents=self.archive_counters['skipped_non_documents'],fatal_errors=self.archive_counters['fatal_errors'],
            document_error_categories={k.split(':',1)[1]:v for k,v in self.archive_counters.items() if k.startswith('document_category:')})
        for name,value in self.run_stages.items():_safe(self.emit,'stages',dict(stage=name,inclusive=True,**value))
        _safe(self.emit,'resource_samples',dict(event='end',**resource_sample()))
        _safe(self.flush);_safe(self._json,'run_summary.json',summary)
        _safe(self.write_sample)
        _safe(self._json,'run_manifest.json',dict(self.manifest,finished_at_unix=time(),status=status,logging_failed=self.logging_failed))
        _safe((self.directory/'README.txt').write_text,'Локальная диагностика TreeTranslate. run_summary.json содержит итоги; index.sqlite3 связывает документы и кандидаты. JSONL хранит завершённые checkpoints. Coverage и fallback не являются оценкой качества. Автоматического возобновления архива нет.\n',encoding='utf8')
        for stream in self.streams.values():_safe(stream.close)
        _safe(self.database.close)

    @serialized_metrics
    def write_sample(self,seed='AW0.81',count=8):
        # Deterministic, bounded selections; source text is never loaded.
        archives={source:dict(path=output,sha256=digest) for source,output,digest in self.database.execute('SELECT * FROM archives')}
        random_rows=[];domains={};rankings={k:[] for k in ('model_fallback','unknown_terms','warnings','ocr','tables_schematics','slowest','page_changes','known_layout_overlap','failed_documents')}
        for doc_id,payload in self.database.execute('SELECT id,payload FROM documents ORDER BY id'):
            d=json.loads(payload);c=d.get('counters',{});profile=d.get('profiler') or {}
            link=dict(document_id=doc_id,source=d.get('archive_member_path'),source_archive=d.get('source_archive_path'),source_sha256=d.get('source_sha256'),output_path=d.get('output_path'),output_sha256=d.get('output_sha256'),output_archive=archives.get(d.get('source_archive_path')),output_archive_member=d.get('output_archive_member'),event_join_key=doc_id,output_status=d.get('output_status'),layout_status=d.get('layout_status','NOT_EVALUATED'))
            random_rows.append((content_hash(seed+':'+doc_id),link));random_rows=sorted(random_rows,key=lambda x:x[0])[:count]
            domain=profile.get('selected_domain','unavailable')
            for scope in [domain,*profile.get('selected_subdomains',{})]:
                pool=domains.setdefault(scope,[]);pool.append((content_hash(seed+':'+doc_id),link));domains[scope]=sorted(pool,key=lambda x:x[0])[:count]
            scores=dict(model_fallback=d.get('model_fallback_rate') or 0,unknown_terms=d.get('unknown_term_candidates',0),warnings=c.get('warnings',0),ocr=d.get('ocr_segments',0),tables_schematics=d.get('table_blocks',0)+d.get('schematic_blocks',0),slowest=d.get('total_wall_seconds',0),page_changes=abs((d.get('output_pages') or 0)-(d.get('source_pages') or 0)),known_layout_overlap=c.get('known_layout_warnings',0),failed_documents=d.get('output_status')=='FAILED_SOURCE_PRESERVED')
            for key,score in scores.items():
                if key in ('known_layout_overlap','failed_documents') and not score:continue
                pool=rankings[key];pool.append((score,doc_id,link));rankings[key]=sorted(pool,key=lambda x:(-x[0],x[1]))[:count]
        result=dict(seed=seed,random=[d for _,d in random_rows],by_domain={k:[d for _,d in pool] for k,pool in sorted(domains.items())},
            **{k:[dict(d,sampling_score=s) for s,_,d in pool] for k,pool in rankings.items()},semantic_auto_grading=False)
        self._json('quality_sample_manifest.json',result)

def stage_observed(name,seconds,state='ok',page=None,block=None):
    observer=current()
    if observer:_safe(observer.stage,name,seconds,state,page,block)

def measure(stage,*,model=False):
    def decorate(method):
        @wraps(method)
        def call(*args,**kwargs):
            observer=current()
            if not observer:return method(*args,**kwargs)
            started=perf_counter();state='ok'
            segment=_segment.get()
            if model and segment:segment['model']=True;segment['model_calls']+=1
            try:return method(*args,**kwargs)
            except BaseException as error:state=type(error).__name__;raise
            finally:stage_observed(stage,perf_counter()-started,state)
        return call
    return decorate

def logged_run(method):
    @wraps(method)
    def call(job,*args,**kwargs):
        directory=getattr(job.config,'metrics_directory',None)
        if not directory or current():return method(job,*args,**kwargs)
        metadata=dict(device=job.config.device.value,source_language=job.config.source,target_language=job.config.target,domain=job.config.domain)
        metadata.update(getattr(job,'metrics_metadata',{}))
        try:observer=LocalRun(directory,run_id=job.run_id,metadata=metadata)
        except Exception as error:
            logger.warning('local_metrics_start_failed type=%s',type(error).__name__);job.metrics_failed=True
            return method(job,*args,**kwargs)
        job.metrics_path=observer.directory
        with observer.activate():
            if metadata.get('scan_seconds') is not None:
                _safe(observer.stage,'archive_scan_before_start',metadata['scan_seconds'])
            try:result=method(job,*args,**kwargs)
            except BaseException as error:
                _safe(observer.close,getattr(job,'run_status','FAILED'),error);raise
            else:_safe(observer.close);job.metrics_failed=observer.logging_failed;return result
    return call

@contextmanager
def semantic_segment(segment,kind=''):
    observer=current();doc=_doc.get()
    if not observer or not doc:yield;return
    from app.documents.pdf_ocr_policy import protected_kind
    text=segment.text;ocr_kind=getattr(segment,'ocr_kind','')
    eligible=not protected_kind(text) and ocr_kind not in {'noise','identifier','measurement'} and any(c.isalpha() for c in text)
    state=dict(routes=set(),model=False,model_calls=0,knowledge=False,direct=False,unsafe=False,source_preserved=False,composition=False,cross_reference=False,device='none',backend='protected',fallback=False)
    token=_segment.set(state)
    try:yield
    finally:
        _segment.reset(token)
        doc.counters['processed_segments']+=1
        doc.data['protected_tokens']+=len(re.findall(r'\b[A-Z][A-Z0-9_-]*\b|\d+(?:[.,]\d+)?',text))
        if eligible:
            state['source_preserved']|=getattr(segment,'policy','')=='CONSERVATIVE_PRESERVE'
            doc.counters['semantic_segments']+=1;doc.counters['eligible_semantic_segments']+=1
            for key,value in [('model_fallback_segments',state['model']),('knowledge_segments',state['knowledge']),('direct_known_segments',state['direct'] and not state['model']),('unsafe_translation_segments',state['unsafe']),('source_preserved_segments',state['source_preserved']),('composition_segments',state['composition']),('cross_reference_segments',state['cross_reference'])]:doc.counters[key]+=bool(value)
            for route in state['routes']:doc.counters[route+'_segments']+=1
            doc.counters['model_calls']+=state['model_calls'];doc.counters['fallback_events']+=state['fallback']
            _safe(observer.emit,'routing',dict(event='segment',segment_id=getattr(segment,'block_id',str(getattr(segment,'reading_order',0))),page=getattr(segment,'page',None),
                source_sha256=content_hash(text),output_sha256=content_hash(getattr(segment,'translated','') or ''),segment_type=kind,origin=getattr(segment,'origin','native'),
                routes=sorted(state['routes']),model_used=state['model'],knowledge_used=state['knowledge'],model_calls=state['model_calls'],source_preserved=state['source_preserved'],device=state['device'],backend=state['backend']))
        else:doc.counters['protected_or_noise_segments']+=1

def observe(method,*args,**kwargs):
    observer=current()
    if observer:return _safe(getattr(observer,method),*args,**kwargs)
    return None
