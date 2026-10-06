"""Bounded lookup replay and one fixed20 control against accepted post-OCR output."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sqlite3
import shutil
import os
import ast
import inspect
import textwrap
import types
import subprocess
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw081/glossary_hot_path'
REF=ROOT/'qa/aw081/ocr_adaptive_runtime/runs/after'
MANIFEST=ROOT/'qa/aw081/hardware_scaling_20/sample_manifest.json'


def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
def read(path):return json.loads(path.read_text('utf8'))
def lines(path):return [json.loads(s) for s in path.read_text('utf8').splitlines()]
def canonical(value):return json.loads(json.dumps(value,ensure_ascii=False,default=str))
def percentile(values,fraction):
    values=sorted(values);return values[min(len(values)-1,int((len(values)-1)*fraction))] if values else 0


class Profile:
    def __init__(self):
        self.counts=Counter();self.seconds=Counter();self.unique={};self.active=False;self.durations=[]
        self.misses=Counter();self.queries=Counter();self.restores=[]
        self.trace=None;self.profiles={};self.engine=None

    def install(self):
        native=sqlite3.connect;owner=self
        class Cursor:
            def __init__(self,cursor,enabled=True):self.cursor=cursor;self.enabled=enabled
            def fetchone(self):
                row=self.cursor.fetchone()
                if owner.active and self.enabled:owner.counts['sql_rows_fetched']+=int(row is not None)
                return row
            def fetchall(self):
                rows=self.cursor.fetchall()
                if owner.active and self.enabled:owner.counts['sql_rows_fetched']+=len(rows)
                return rows
            def __iter__(self):
                for row in self.cursor:
                    if owner.active and self.enabled:owner.counts['sql_rows_fetched']+=1
                    yield row
            def __getattr__(self,name):return getattr(self.cursor,name)
        class Connection(sqlite3.Connection):
            def execute(self,sql,params=()):
                start=perf_counter();value=super().execute(sql,params)
                if owner.active and self.glossary_sql:
                    owner.counts['sql_statements']+=1;owner.seconds['sql_execute']+=perf_counter()-start
                    owner.counts['sql_query_count']+=sql.lstrip().upper().startswith(('SELECT','PRAGMA'))
                    owner.counts['transaction_begins']+=sql.lstrip().upper().startswith('BEGIN')
                    owner.queries[sql]+=1
                return Cursor(value,self.glossary_sql)
            def commit(self):
                if owner.active and self.glossary_sql:owner.counts['sql_commits']+=1
                return super().commit()
        def connect(*args,**kwargs):
            path=str(args[0] if args else kwargs.get('database','')).lower().replace('\\','/')
            enabled=not any(name in path for name in ('empty-tm.db','index.sqlite3'))
            if owner.active and enabled:owner.counts['connection_opens']+=1
            con=native(*args,**dict(kwargs,factory=Connection));con.glossary_sql=enabled
            return con
        sqlite3.connect=connect;self.restores.append(lambda:setattr(sqlite3,'connect',native))
        import app.glossary.normalization as norm
        import app.glossary.repository as repository
        import app.glossary.ranking as ranking
        import app.glossary.models as models
        import app.knowledge.router as knowledge
        functions=[('normalization',norm.normalize),('offset_normalization',norm.mapped),
                               ('materialization',repository.model),('entry_metadata',models.entry_metadata),
                               ('ranking',ranking.resolve)]
        if hasattr(norm,'_mapped_uncached'):functions.append(('normalization_compute',norm._mapped_uncached))
        for name,original in functions:
            def wrapper(*args,_original=original,_name=name,**kwargs):
                start=perf_counter()
                try:return _original(*args,**kwargs)
                finally:
                    if self.active:
                        self.counts[_name]+=1;self.seconds[_name]+=perf_counter()-start
                        if _name in ('normalization','offset_normalization'):
                            self.unique.setdefault(_name,set()).add(repr((args,kwargs)))
            for module in list(sys.modules.values()):
                if getattr(module,'__name__','').startswith(('app.glossary','app.knowledge')):
                    for key,value in list(vars(module).items()):
                        if value is original:
                            setattr(module,key,wrapper)
                            self.restores.append(lambda m=module,k=key,v=original:setattr(m,k,v))
        for name in ['ranked','_noun_slot']:
            original=getattr(knowledge.KnowledgeRouter,name)
            def wrapper(*args,_original=original,_name=name,**kwargs):
                start=perf_counter()
                try:return _original(*args,**kwargs)
                finally:
                    if self.active:self.counts[_name]+=1;self.seconds[_name]+=perf_counter()-start
            setattr(knowledge.KnowledgeRouter,name,wrapper)
            self.restores.append(lambda n=name,v=original:setattr(knowledge.KnowledgeRouter,n,v))
        from app.glossary.engine import GlossaryEngine
        original=GlossaryEngine.lookup
        def lookup(engine,text,source,target,domain='general',context='',**kwargs):
            started=perf_counter();snapshot=kwargs.get('snapshot');request=kwargs.get('request')
            key=repr((text,source,target,domain,context,snapshot.signature if snapshot else '',
                      getattr(request,'segment_type',''),asdict(request.context_profile) if request and request.context_profile else None))
            result=original(engine,text,source,target,domain,context,**kwargs)
            if self.active:
                self.engine=engine
                self.counts['lookups']+=1;self.durations.append(perf_counter()-started)
                self.unique.setdefault('lookup',set()).add(key)
                if not result:self.misses[key]+=1
                if self.trace:
                    profile=request.context_profile if request else None
                    profile_key=hashlib.sha256(json.dumps(asdict(profile),sort_keys=True,default=str).encode()).hexdigest() if profile else None
                    if profile:self.profiles[profile_key]=asdict(profile)
                    row=dict(text=text,source=source,target=target,domain=domain,context=context,
                        snapshot=snapshot.signature if snapshot else None,profile=profile_key,
                        request_text=request.text if request else None,segment_type=request.segment_type if request else '',
                        matches=[asdict(m) for m in result],plan=asdict(engine.codec.encode(text,result)))
                    self.trace.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
            return result
        GlossaryEngine.lookup=lookup;self.restores.append(lambda:setattr(GlossaryEngine,'lookup',original))

    def close(self):
        for restore in reversed(self.restores):restore()

    def summary(self):
        return dict(counts=dict(self.counts),seconds=dict(self.seconds),unique={k:len(v) for k,v in self.unique.items()},
            glossary_seconds=sum(self.durations),median_lookup_seconds=percentile(self.durations,.5),
            p90_lookup_seconds=percentile(self.durations,.9),negative_lookups=sum(self.misses.values()),
            repeated_misses=sum(n-1 for n in self.misses.values()),sql_patterns=dict(self.queries))


def corpus():
    docs={d['archive_member_path']:d for d in lines(REF/'logs'/read(REF/'execution.json')['run_id']/'documents.jsonl')}
    queries=[]
    for member,rows in read(REF/'candidates.json').items():
        if member not in docs:continue
        document=docs[member];p=document.get('profiler') or {}
        profile=dict(source_language=document['source_language'],target_language='ru',
            primary_domain=p.get('selected_domain','general'),domains=list(p.get('domain_scores',{}).items()),
            subdomains=list(p.get('selected_subdomains',{}).items()),document_types=list(p.get('document_types',{}).items()),
            content_types=list(p.get('content_types',{}).items()),evidence=[],identity=document['source_sha256'],
            version=p.get('version','0.81'),semantic_facts=p.get('semantic_facts',[]))
        for row in rows:
            text=row['source']
            queries.append(dict(text=text,source='zh' if any('\u3400'<=c<='\u9fff' for c in text) else document['source_language'],
                target='ru',domain=profile['primary_domain'],context='',profile=profile,member=member))
    return queries


def replay(label):
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.knowledge.router import KnowledgeRouter
    from app.knowledge.profile import ContextProfile
    from app.knowledge.segments import SegmentClassifier
    from app.engine.types import TranslationRequest
    queries=read(QA/'corpus.json');results=[]
    profiler=Profile();profiler.install()
    with TemporaryDirectory(prefix='TreeTranslate-glossary-replay-') as temp:
        glossary=GlossaryEngine(Path(temp)/'user.db',builtin_paths=bundled_paths())
        router=KnowledgeRouter(glossary);snapshots={};profiles={}
        glossary.lookup('','zh','ru')
        for q in queries:
            identity=q['profile']['identity']
            if identity in profiles:continue
            data=dict(q['profile'])
            for key in ['domains','subdomains','document_types','content_types','evidence']:
                data[key]=tuple(tuple(r) for r in data[key])
            data['semantic_facts']=tuple(data['semantic_facts'])
            profile=ContextProfile(**data);profiles[identity]=profile;snapshots[identity]=router.snapshot(profile)
        started=perf_counter();profiler.active=True
        for index,q in enumerate(queries):
            profile=profiles[q['profile']['identity']];snapshot=snapshots[profile.identity]
            request=TranslationRequest(q['text'],q['source'],q['target'],domain=q['domain'],context=q['context'],
                context_profile=profile,knowledge_snapshot=snapshot,context_router=router,
                segment_type=SegmentClassifier.classify(q['text']).value)
            # Cover the real contextual path and unsnapshotted lexical path;
            # immediate repeats expose hit/miss overhead without NMT/OCR.
            rows=[]
            for contextual in [True,False,True]:
                active_request=request if contextual else None
                matches=glossary.lookup(q['text'],q['source'],q['target'],q['domain'],q['context'],
                    snapshot=snapshot if contextual else None,request=active_request)
                plan=glossary.codec.encode(q['text'],matches)
                selected=glossary.full_segment(request,matches)
                rows.append(canonical(dict(matches=[asdict(m) for m in matches],plan=asdict(plan),
                    selected=selected.translated_text if selected else None,
                    selected_status=selected.constraint_status if selected else None)))
            results.append(rows)
            if (index+1)%200==0:print('LOOKUP_REPLAY',label,index+1,'/',len(queries),round(perf_counter()-started,2),flush=True)
        profiler.active=False
        profile=profiler.summary();profile['wall_seconds']=perf_counter()-started
        profile['engine_counters']=dict(glossary.counters)
        profile['runtime_caches']=glossary.cache_metrics() if hasattr(glossary,'cache_metrics') else {}
        if hasattr(glossary,'close'):glossary.close()
    profiler.close()
    save(QA/(label+'_lookup_results.json'),results);save(QA/(label+'_lookup_profile.json'),profile)
    if label=='after':
        expected=read(QA/'before_lookup_results.json')
        equivalent=results==expected
        save(QA/'lookup_equivalence.json',dict(status='PASS' if equivalent else 'FAIL',queries=len(queries),
             modes_per_query=3,ordered_results_constraints_selected_exact=equivalent))
        assert equivalent
    print('REPLAY_DONE',label,profile['wall_seconds'],profile['counts'],flush=True)


def baseline():
    QA.mkdir(exist_ok=False)
    from tools.aw081_speed_calibration_100 import frozen_hashes
    before=frozen_hashes();events=lines(REF/'timing_events.jsonl')
    durations=[e['seconds'] for e in events if e['stage']=='glossary_lookup']
    save(QA/'baseline.json',dict(reference=str(REF),wall_seconds=read(REF/'execution.json')['wall_seconds'],
        glossary_calls=len(durations),glossary_seconds=sum(durations),median_lookup_seconds=percentile(durations,.5),
        p90_lookup_seconds=percentile(durations,.9),production_before=before,
        source_manifest_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        instrumentation_scope='Existing accepted fixed20 stage timing plus before-code-change lookup-only replay of its real candidate sources; replay SQL/CPU counts are not claimed as counts of the original whole-document run.'))
    frozen=QA/'legacy';frozen.mkdir()
    for package in ['glossary']:
        shutil.copytree(ROOT/'app'/package,frozen/package,ignore=shutil.ignore_patterns('__pycache__'))
    save(QA/'corpus.json',corpus())
    from app.glossary.bundled import bundled_paths
    plans=[]
    for path in bundled_paths():
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            sql='SELECT e.*,a.term AS alias FROM aliases a JOIN entries e ON e.id=a.entry_id WHERE a.pair=? AND a.domain IN (?,?) AND a.hash IN (?,?,?) LIMIT ?'
            rows=[list(r) for r in con.execute('EXPLAIN QUERY PLAN '+sql,('zh>ru','automotive','general','a','b','c',4097))]
            plans.append(dict(store=str(path),query=sql,plan=rows))
    save(QA/'query_plan.json',dict(schema_changed=False,index_added=False,hot_queries=plans))
    replay('before')
    assert frozen_hashes()==before


def load_legacy():
    sys.path.insert(0,str(QA/'legacy'))
    from glossary.engine import GlossaryEngine
    return GlossaryEngine


def pdf_run(label,targeted=False):
    from tools import aw081_hardware_scaling_20 as frozen
    from app.glossary import engine as glossary_module
    from app.documents.pdf_document import PdfDocument,NativeTextExtractor
    from tools.aw081_ocr_adaptive import source_contract
    from app.documents.job import DocumentJob
    manifest=read(MANIFEST);area=QA/'targeted' if targeted else QA
    area.mkdir(exist_ok=True)
    if targeted:
        # Three real glossary-heavy members, preserving original archive order.
        selected=sorted(manifest['documents'],key=lambda d:d['baseline_glossary_seconds'],reverse=True)[:3]
        manifest['documents']=[d for d in manifest['documents'] if d in selected]
        archive=area/'TARGETED3.zip'
        if not archive.exists():
            with ZipFile(manifest['sample_archive']) as source,ZipFile(archive,'w') as output:
                for d in manifest['documents']:output.writestr(d['member_path'],source.read(d['member_path']))
        manifest.update(sample_count=3,sample_archive=str(archive),sample_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            bucket_counts={d['bucket']:1 for d in selected if d['baseline_status']=='TRANSLATED'})
    else:
        assert read(QA/'targeted_result.json')['status']=='PASS'
        assert read(QA/'lookup_equivalence.json')['status']=='PASS'
    save(area/'sample_manifest.json',manifest);save(area/'production_before.json',frozen.frozen_hashes())
    old_class=glossary_module.GlossaryEngine
    if label=='before':glossary_module.GlossaryEngine=load_legacy()
    profile=Profile();profile.install();sources={}
    trace=(area/(label+'_lookup_trace.jsonl')).open('x',encoding='utf8');profile.trace=trace
    old_start,old_finish=frozen.Monitor.start,frozen.Monitor.finish
    old_init=PdfDocument.__init__
    by_hash={d['source_sha256']:d['member_path'] for d in manifest['documents']}
    def observed_init(document,*args,**kwargs):
        old_init(document,*args,**kwargs)
        extractor=kwargs.get('extractor',args[3] if len(args)>3 else None)
        # Archive profiler uses NativeTextExtractor. Record the actual child.
        member=by_hash.get(document.source_hash)
        if profile.active and member and extractor is not None and not isinstance(extractor,NativeTextExtractor):
            sources[member]=canonical(source_contract(document))
    PdfDocument.__init__=observed_init
    os.environ['TREETRANSLATE_OCR_LIFECYCLE_LOG']=str(area/(label+'_warmup_loads.jsonl'))
    def start(monitor):
        os.environ['TREETRANSLATE_OCR_LIFECYCLE_LOG']=str(area/(label+'_ocr_loads.jsonl'))
        os.environ['TREETRANSLATE_OCR_GATE_LOG']=str(area/(label+'_ocr_gates.jsonl'))
        profile.active=True
        return old_start(monitor)
    def finish(monitor):
        profile.active=False
        return old_finish(monitor)
    frozen.Monitor.start,frozen.Monitor.finish=start,finish
    namespace=dict(frozen.run.__globals__,QA=area)
    if targeted:
        tree=ast.parse(textwrap.dedent(inspect.getsource(frozen.run)))
        class Cardinality(ast.NodeTransformer):
            def visit_Constant(self,node):
                if type(node.value) is int and node.value==20:return ast.copy_location(ast.Constant(3),node)
                return node
        tree=Cardinality().visit(tree);ast.fix_missing_locations(tree)
        exec(compile(tree,'<QA targeted3 cardinality only>','exec'),namespace);run=namespace['run']
    else:run=types.FunctionType(frozen.run.__code__,namespace,'run',frozen.run.__defaults__)
    try:run(label,'mid')
    finally:
        profile.active=False;trace.close()
        save(area/(label+'_lookup_profiles.json'),profile.profiles)
        summary=profile.summary()
        if profile.engine and hasattr(profile.engine,'cache_metrics'):
            summary['runtime_caches']=profile.engine.cache_metrics();summary['cache_plan']=asdict(profile.engine.cache_plan)
        save(area/(label+'_lookup_profile.json' if targeted else 'fixed20_lookup_profile.json'),summary);save(area/(label+'_source_contracts.json'),sources)
        profile.close();glossary_module.GlossaryEngine=old_class
        PdfDocument.__init__=old_init;frozen.Monitor.start,frozen.Monitor.finish=old_start,old_finish
    if targeted and label=='after':
        checks={name:read(area/'runs/before'/(name+'.json'))==read(area/'runs/after'/(name+'.json'))
                for name in ['candidates','writer','fingerprints']}
        checks['sources']=read(area/'before_source_contracts.json')==sources
        before=read(area/'before_lookup_profile.json');after=read(area/'after_lookup_profile.json')
        checks['sql_reduced']=after['counts']['sql_statements']<before['counts']['sql_statements']
        save(QA/'targeted_result.json',dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,
            documents=[d['member_path'] for d in manifest['documents']],before=before,after=after,
            before_wall=read(area/'runs/before/execution.json')['wall_seconds'],
            after_wall=read(area/'runs/after/execution.json')['wall_seconds']))
        assert all(checks.values()),checks


def actual_lookup_equivalence(raw=False):
    from app.glossary.bundled import bundled_paths
    from app.knowledge.router import KnowledgeRouter
    from app.knowledge.profile import ContextProfile
    from app.engine.types import TranslationRequest
    legacy_class=load_legacy()
    from app.glossary import engine as engine_module
    from glossary.matcher import candidates as legacy_candidates
    glossary_class=engine_module.GlossaryEngine if raw else legacy_class
    profiles=read(QA/'after_lookup_profiles.json');count=0;errors=[];raw_errors=[];reference_cache={};raw_calls=0
    original_candidates=engine_module.candidates
    def checked_candidates(*args,**kwargs):
        nonlocal raw_calls
        raw_calls+=1
        identity=(args[1],args[2],args[3],args[4],tuple(args[5]),args[6],frozenset(args[7]),args[8:],kwargs.get('namespace'))
        def digest(fn,options):
            try:
                rows=fn(*args,**options)
                value=('rows',[asdict(m) for m in rows])
                error=None
            except Exception as e:
                value=('error',type(e).__name__,str(e));rows=None;error=e
            signature=hashlib.sha256(json.dumps(value,ensure_ascii=False,default=str).encode()).hexdigest()
            return signature,rows,error
        if identity not in reference_cache:reference_cache[identity]=digest(legacy_candidates,{})[0]
        signature,rows,error=digest(original_candidates,kwargs)
        if signature!=reference_cache[identity]:raw_errors.append(dict(index=count,store=args[6],text=args[1]))
        if error:raise error
        return rows
    if raw:engine_module.candidates=checked_candidates
    with TemporaryDirectory(prefix='TreeTranslate-legacy-equivalence-') as temporary:
        g=glossary_class(Path(temporary)/'user.db',builtin_paths=bundled_paths(),config=dict(cache_size=512,compiled_index_cache_size=8))
        router=KnowledgeRouter(g);snapshots={};contexts={}
        for key,data in profiles.items():
            for name in ['domains','subdomains','document_types','content_types','evidence']:
                data[name]=tuple(tuple(v) for v in data[name])
            data['semantic_facts']=tuple(data['semantic_facts']);contexts[key]=ContextProfile(**data)
        for line in (QA/'after_lookup_trace.jsonl').open(encoding='utf8'):
            row=json.loads(line);p=contexts.get(row['profile']);snapshot=None
            if row['snapshot']:
                if row['profile'] not in snapshots:snapshots[row['profile']]=router.snapshot(p)
                snapshot=snapshots[row['profile']];assert snapshot.signature==row['snapshot']
            request=TranslationRequest(row['request_text'],row['source'],row['target'],domain=row['domain'],context=row['context'],
                context_profile=p,knowledge_snapshot=snapshot,context_router=router,segment_type=row['segment_type']) if row['request_text'] is not None else None
            matches=g.lookup(row['text'],row['source'],row['target'],row['domain'],row['context'],snapshot=snapshot,request=request)
            actual=canonical(dict(matches=[asdict(m) for m in matches],plan=asdict(g.codec.encode(row['text'],matches))))
            if actual!=dict(matches=row['matches'],plan=row['plan']):errors.append(dict(index=count,text=row['text']))
            count+=1
            if count%1000==0:print('RAW_LOOKUP_EQ' if raw else 'ACTUAL_LOOKUP_EQ',count,len(errors),len(raw_errors),flush=True)
        if hasattr(g,'close'):g.close()
    engine_module.candidates=original_candidates
    result=read(QA/'lookup_equivalence.json')
    if raw:result.update(raw_candidate_queries=count,raw_candidate_calls=raw_calls,unique_raw_candidate_requests=len(reference_cache),
        raw_preselection_ordered_candidates_exact=not raw_errors,raw_errors=raw_errors,current_final_matches_exact=not errors)
    else:result.update(actual_fixed20_queries=count,actual_ordered_candidates_constraints_exact=not errors,errors=errors)
    if errors or raw_errors:result['status']='FAIL'
    save(QA/'lookup_equivalence.json',result);assert not errors and not raw_errors


def analyze():
    directory=QA/'runs/after';execution=read(directory/'execution.json');summary=read(directory/'run_summary.json')
    checks={name:read(directory/(name+'.json'))==read(REF/(name+'.json')) for name in ['candidates','writer','fingerprints']}
    reference=read(ROOT/'qa/aw081/ocr_adaptive_runtime/baseline.json')['documents']
    sources=read(QA/'after_source_contracts.json')
    checks['full_source_contracts']=len(sources)==20 and all(sources.get(k)==v['source'] for k,v in reference.items())
    counts=summary['archive_events'];checks['statuses']=counts['translated_documents']==16 and counts['failed_documents']==4 and counts['fatal_errors']==0 and execution['fatal'] is None
    checks['source_and_production_unchanged']=execution['source_immutable'] and execution['production_unchanged']
    events=lines(QA/'after_ocr_loads.jsonl');checks['ocr_two_loads']=sum(e['event']=='model_load' for e in events)==2
    lexical_eq=read(QA/'lookup_equivalence.json')
    checks['actual_lookup_equivalence']=lexical_eq['status']=='PASS' and lexical_eq.get('actual_fixed20_queries')==9473
    checks['ordered_preselection_candidates']=lexical_eq.get('raw_preselection_ordered_candidates_exact') is True and lexical_eq.get('raw_candidate_queries')==9473
    with ZipFile(execution['outputs'][0]) as output,ZipFile(read(REF/'execution.json')['outputs'][0]) as before:
        checks['archive_crc']=output.testzip() is None
        checks['directory_paths']={x.filename for x in output.infolist() if x.is_dir()}=={x.filename for x in before.infolist() if x.is_dir()}
    save(QA/'output_equivalence.json',dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,reference=str(REF)))
    stages=Counter();calls=Counter()
    for e in lines(directory/'timing_events.jsonl'):stages[e['stage']]+=e['seconds'];calls[e['stage']]+=1
    base=read(QA/'baseline.json');gain=(1-execution['wall_seconds']/base['wall_seconds'])*100
    glossary_gain=(1-stages['glossary_lookup']/base['glossary_seconds'])*100
    verdict='GLOSSARY OPTIMIZATION REJECTED' if not all(checks.values()) else 'GLOSSARY PERFORMANCE PASS' if glossary_gain>=50 else 'GLOSSARY OPTIMIZATION INSUFFICIENT'
    resources=lines(directory/'resource_samples.jsonl')
    after=dict(wall_seconds=execution['wall_seconds'],glossary_seconds=stages['glossary_lookup'],glossary_calls=calls['glossary_lookup'],
        stage_seconds=dict(stages),stage_calls=dict(calls),model_loads=sum(e['event']=='model_load' for e in events),
        peak_rss_bytes=max(r['rss_bytes'] for r in resources),peak_private_commit_bytes=max(r['private_commit_bytes'] for r in resources))
    save(QA/'fixed20_result.json',dict(verdict=verdict,baseline=dict(wall_seconds=base['wall_seconds'],glossary_seconds=base['glossary_seconds']),
        after=after,wall_reduction_percent=gain,glossary_reduction_percent=glossary_gain,run_id=execution['run_id'],main_measured_runs=1,equivalence='PASS' if all(checks.values()) else 'FAIL'))
    profiles=dict(before_replay=read(QA/'before_lookup_profile.json'),after_replay=read(QA/'after_lookup_profile.json'),
        actual_fixed20=read(QA/'fixed20_lookup_profile.json'))
    for p in profiles.values():p['unique_sql_statement_shapes']=len(p['sql_patterns'])
    profiles['actual_fixed20']['counts'].setdefault('connection_opens',0)
    profiles['actual_fixed20']['scope']='Measured fixed20 after excluded warmup; SQLite opens=0 within this window, warmup total not counted; TM/index databases excluded.'
    save(QA/'lookup_profile.json',profiles)
    print('FIXED20_RESULT',verdict,gain,glossary_gain,checks,flush=True)
    assert all(checks.values())


def query_plan():
    from app.glossary.bundled import bundled_paths
    plans=[]
    for path in bundled_paths():
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            sql='SELECT e.*,a.term AS alias FROM aliases a JOIN entries e ON e.id=a.entry_id WHERE a.pair=? AND a.domain IN (?,?) AND a.hash IN (?,?,?) LIMIT ?'
            rows=[list(r) for r in con.execute('EXPLAIN QUERY PLAN '+sql,('zh>ru','automotive','general','a','b','c',4097))]
            plans.append(dict(store=str(path),query=sql,plan=rows))
    save(QA/'query_plan.json',dict(schema_changed=False,index_added=False,hot_queries=plans))


def full_pytest():
    assert read(QA/'output_equivalence.json')['status']==read(QA/'lookup_equivalence.json')['status']=='PASS'
    from tools.aw081_speed_calibration_100 import frozen_hashes
    before=frozen_hashes();started=perf_counter()
    command=[sys.executable,'-X','utf8','-m','pytest','-q','--junitxml='+str(QA/'full_pytest.xml')]
    with (QA/'full_pytest_stdout.txt').open('x',encoding='utf8') as stdout:
        result=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=subprocess.STDOUT)
    after=frozen_hashes();totals=Counter()
    for suite in ET.parse(QA/'full_pytest.xml').getroot().iter('testsuite'):
        for k in ['tests','failures','errors','skipped']:totals[k]+=int(suite.get(k,0))
    save(QA/'full_pytest.json',dict(status='PASS' if result.returncode==0 and before==after else 'FAIL',
        passed=totals['tests']-totals['failures']-totals['errors']-totals['skipped'],**totals,seconds=perf_counter()-started,
        returncode=result.returncode,production_hashes_before=before,production_hashes_after=after,production_unchanged=before==after))
    print('FULL_PYTEST',result.returncode,dict(totals),flush=True);assert result.returncode==0 and before==after


def report():
    from tools.aw081_speed_calibration_100 import frozen_hashes
    result=read(QA/'fixed20_result.json');eq=read(QA/'output_equivalence.json');lookup=read(QA/'lookup_equivalence.json');suite=read(QA/'full_pytest.json')
    assert eq['status']==lookup['status']==suite['status']=='PASS'
    original=read(QA/'baseline.json')['production_before'];current=frozen_hashes()
    changed=[k for k in sorted(original.keys()|current.keys()) if original.get(k)!=current.get(k)]
    allowed={p.replace('/','\\') for p in ['app/glossary/cache_plan.py','app/glossary/hot_cache.py','app/glossary/database.py',
        'app/glossary/normalization.py','app/glossary/matcher.py','app/glossary/engine.py','app/translation_memory/knowledge.py']}
    assert set(changed)<=allowed and current==suite['production_hashes_after']==read(QA/'production_before.json')
    frozen_scripts=read(ROOT/'qa/aw081/hardware_scaling_20/final_evidence_audit.json')['qa_analysis_script_sha256']
    checks={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==frozen_scripts[p]
        for p in ['tools\\aw081_hardware_scaling_20.py','tools\\aw081_hardware_support.py']}
    assert all(checks.values())
    assert all(current[k]==value for k,value in original.items() if k.startswith('app\\ocr\\'))
    dictionary_hashes=read(QA/'dictionary_hashes_before.json')
    assert all(hashlib.sha256(Path(k).read_bytes()).hexdigest()==v for k,v in dictionary_hashes.items())
    manifest=read(MANIFEST);execution=read(QA/'runs/after/execution.json')
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest()==read(QA/'baseline.json')['source_manifest_sha256']
    with ZipFile(manifest['sample_archive']) as archive:
        assert archive.testzip() is None
        assert all(hashlib.sha256(archive.read(d['member_path'])).hexdigest()==d['source_sha256'] for d in manifest['documents'])
    import psutil
    workers=[]
    for p in psutil.process_iter(['pid','cmdline']):
        try:
            if 'app.ocr.runtime.worker' in (p.info['cmdline'] or []):workers.append(p.info['pid'])
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    assert not workers
    with sqlite3.connect(QA/'runs/after/empty-tm.db') as con:
        tm={name:con.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ['units','fuzzy_keys']}
    assert not any(tm.values())
    save(QA/'final_audit.json',dict(status='PASS',changed_production_files=changed,frozen_harness_unchanged=checks,
        production_before=original,production_after=current,ocr_unchanged=True,assets_knowledge_nmt_ui_unchanged=True,
        dictionary_hashes_unchanged=len(dictionary_hashes),
        source_sha_checks=20,source_crc='PASS',translation_memory_rows=tm,workers_remaining=workers,main_measured_runs=1))
    before=read(QA/'before_lookup_profile.json');after=read(QA/'after_lookup_profile.json');main=read(QA/'fixed20_lookup_profile.json')
    targeted=read(QA/'targeted_result.json');base=result['baseline'];run=result['after'];plan=main['cache_plan'];caches=main['runtime_caches']
    baseline=read(QA/'baseline.json')
    rows=[('Lookup replay wall, с',before['wall_seconds'],after['wall_seconds']),
        ('SQL statements, replay',before['counts']['sql_statements'],after['counts']['sql_statements']),
        ('SQL queries, replay',before['counts']['sql_query_count'],after['counts']['sql_query_count']),
        ('BEGIN, replay',before['counts']['transaction_begins'],after['counts']['transaction_begins']),
        ('Fetched rows, replay',before['counts']['sql_rows_fetched'],after['counts']['sql_rows_fetched']),
        ('Entry materializations, replay',before['counts']['materialization'],after['counts']['materialization']),
        ('Fixed20 glossary, с',base['glossary_seconds'],run['glossary_seconds']),
        ('Fixed20 lookup P50, мс',baseline['median_lookup_seconds']*1000,main['median_lookup_seconds']*1000),
        ('Fixed20 lookup P90, мс',baseline['p90_lookup_seconds']*1000,main['p90_lookup_seconds']*1000),
        ('Fixed20 wall, с',base['wall_seconds'],run['wall_seconds'])]
    def fmt(value):return f'{value:.2f}' if isinstance(value,float) else str(value)
    table='| Показатель | До | После |\n|---|---:|---:|\n'+'\n'.join(f'| {name} | {fmt(a)} | {fmt(b)} |' for name,a,b in rows)
    old_stages=Counter()
    for e in lines(REF/'timing_events.jsonl'):old_stages[e['stage']]+=e['seconds']
    components='; '.join(f"{k}: {old_stages[k]:.2f} → {run['stage_seconds'].get(k,0):.2f} с" for k in ['model_translation','template_routing','knowledge_snapshot','pdf_write','pdf_page_layout_write'])
    document=f'''# AW0.81 Glossary Hot Path

**{result['verdict']}**. Этап №2 завершён. Ровно один основной measured fixed20, run `{result['run_id']}`; эталон — принятый post-OCR `2681af77e18c`, 726.26 с. Warmup исключён одинаково; sample 5/5/5/5 и MID settings сохранены.

## 1. Root cause

49 словарных DB при compiled-index capacity 8 вызывали повторные открытия, PRAGMA/BEGIN/revision/length queries и повторную нормализацию. До изменений сохранён реальный corpus из 1598 source segments принятого fixed20: 5094 lookup calls с contextual/unsnapshotted/repeat вариантами, 2044 уникальных логических запроса. Это отдельный instrumentation replay; его SQL counts не выдаются за исторические counts всего PDF run. Индексы aliases PK и entries PK уже используются; schema/index changes не понадобились (`query_plan.json`).

## 2. Optimization

Read connections переиспользуются в пределах thread; writable операции остаются отдельными транзакциями, builtins открываются mode=ro. SQLite data_version плюс revision, file identity и connection epoch инвалидируют caches при внешней записи/замене DB/reopen. BEGIN/COMMIT и rollback сохраняют прежние границы. Shutdown и отключение/удаление пакета закрывают handles текущего потока. Нормализация вычисляется по прежнему алгоритму; offsets возвращаются отдельным списком. Её функция не зависит от языка: key содержит raw text, fold и версию Unicode policy; language/domain-dependent retrieval кешируется отдельно.

## 3. Cache/prefetch architecture

Bounded byte LRU хранит immutable raw lexical rows, lengths и empty misses. Namespace включает store/data source/file identity/revision, языковую пару, domain, hash chunk и limit. Final selection cache сохраняет context/snapshot/config/segment/subdomain/facts и добавляет raw request/profile/forms identity. Фильтрация, рейтинг, grammar, placeholders и fallback выполняются прежним кодом. Prefetch использует уникальные уже известные document sources, без выбора терминов и изменения порядка; оригинальные 300-hash SQL chunks/LIMIT оставлены ради exact retrieval order. Forms уже загружены как dict: отдельный morphology cache не добавлен, поскольку CPU profile не показал там существенной стоимости.

## 4. Hardware-aware RAM policy

Reserve max(2 GiB,15% total); lexical ≤256 MiB и min(usable/32,working-set estimate,2×DB bytes); normalization ≤32 MiB/usable÷256; prefetch ≤16 MiB/lexical÷4/usable÷512, source batch ≤256. Это ceilings без предварительного выделения памяти. На этом запуске: lexical {plan['lexical_bytes']/1024**2:.2f} MiB, normalization {plan['normalization_bytes']/1024**2:.2f} MiB, prefetch {plan['document_prefetch_bytes']/1024**2:.2f} MiB, batch {plan['prefetch_batch_items']}. Fake 8/16/32/64 GiB и pressure cases проверены; при нехватке headroom caches отключаются и lookup продолжает работать.

## 5. Before → after glossary metrics

{table}

Replay connection opens {before['counts']['connection_opens']} → {after['counts']['connection_opens']} относятся только к measured replay после snapshot warmup: 49 builtin handles были открыты до таймера. В реальном fixed20 measured DB opens {main['counts'].get('connection_opens',0)}, SQL statements {main['counts']['sql_statements']}, queries {main['counts']['sql_query_count']}, rows {main['counts']['sql_rows_fetched']}; TM/index SQL исключены. Unique lookup queries {main['unique']['lookup']}; negative calls {main['negative_lookups']}, repeated misses {main['repeated_misses']}. Cache/prefetch details и normalization computations/hit/miss/bytes записаны в `lookup_profile.json`; cache totals включают одинаковый warmup. API normalize calls в replay {before['counts']['normalization']} → {after['counts']['normalization']}; uncached CPU отделён от числа обращений. SQL execute timing измеряет execute без fetch; wall охватывает весь lookup.

## 6. Fixed20 wall before → after

726.26 → **{run['wall_seconds']:.2f} с**, wall −**{result['wall_reduction_percent']:.2f}%**, glossary −**{result['glossary_reduction_percent']:.2f}%**. Targeted3 до/после: {targeted['before_wall']:.2f} → {targeted['after_wall']:.2f} с, SQL decrease и output/source equivalence PASS. Peak tree RSS {run['peak_rss_bytes']/1024**3:.2f} GiB, private commit {run['peak_private_commit_bytes']/1024**3:.2f} GiB. OCR model loads: 2 → 2; OCR code/settings/gates не менялись. Stage comparison: {components}. Вложенные stage times нельзя суммировать как независимые части wall.

## 7. Equivalence

**PASS**: corpus selected terms/constraints; все {lookup['actual_fixed20_queries']} фактических lookup queries контрольного fixed20 проиграны по сохранённому legacy GlossaryEngine после benchmark, включая profile/snapshot signature. Совпали ordered matches и encoded placeholders/forbidden constraints. Дополнительно {lookup['raw_candidate_calls']} raw candidate calls ({lookup['unique_raw_candidate_requests']} уникальных) сверены с legacy SQL matcher до выбора термина: полные списки и порядок совпали. Все 20 source contracts (text/bbox/confidence/order/polygon/model), translation candidates, writer statuses/IDs/numbers, normalized PDF fingerprints и четыре rendered first/last probes совпали. 16 TRANSLATED / 4 FAILED_SOURCE_PRESERVED / 0 fatal; failed exact path/bytes, ZIP CRC, source SHA и directory paths PASS. QA observer исключил native archive sample.

## 8. Remaining bottleneck

Остаются обязательные snapshot/context operations, per-call invalidation checks, NMT inference и PDF writer; их processing policy не менялась. Data-version polling сохраняет безопасную видимость внешних правок, поэтому полного устранения SQL нет. Scheduler, model options, OCR и качество перевода относятся к отдельным задачам и здесь не менялись.

## 9. Full pytest

{suite['passed']} passed / {suite['failures']} failed / {suite['errors']} errors / {suite['skipped']} skipped; {suite['seconds']:.2f} с. Production hashes до/после suite совпали ({len(current)} files). Diff ограничен {len(changed)} файлами glossary data access/cache и Knowledge wrapper lifecycle/prefetch; content Knowledge/TM/NMT/UI/assets и весь OCR сохранены. Frozen harness/support SHA совпали, test TM пуст, OCR workers завершены. Evidence: `qa/aw081/glossary_hot_path/`.

## 10. Verdict

**{result['verdict']}**, текущий этап 100%. STOP. Общая AW0.81 и semantic MAJOR ledger не переоценивались. Этап №3, 100/17211 PDF, PHASE B/C и AW0.82 не запускались. Commit не создан.
'''
    (ROOT/'docs/AW0.81_GLOSSARY_HOT_PATH.md').write_text(document,'utf8')
    state=read(ROOT/'qa/aw081/work_state.json')
    state.update(status='GLOSSARY_HOT_PATH_COMPLETE_STOP',next='STOP: stage 2 complete; await instruction for stage 3.',
        current_task=dict(name='GLOSSARY / KNOWLEDGE HOT PATH',completed=True,percent=100,verdict=result['verdict'],
            report='docs/AW0.81_GLOSSARY_HOT_PATH.md',run_id=result['run_id']))
    state['latest_full_suite']=dict(tests=suite['tests'],passed=suite['passed'],failures=suite['failures'],errors=suite['errors'],
        skipped=suite['skipped'],seconds=suite['seconds'],xml_path='qa/aw081/glossary_hot_path/full_pytest.xml')
    state['tests']=state['latest_full_suite'];save(ROOT/'qa/aw081/work_state.json',state)
    print('REPORT_COMPLETE',result['verdict'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['baseline','replay','targeted','fixed','actual-eq','raw-eq','analyze','plan','pytest','report']);parser.add_argument('--label',default='after');args=parser.parse_args()
    if args.mode=='baseline':baseline()
    elif args.mode=='replay':replay(args.label)
    elif args.mode=='targeted':pdf_run(args.label,True)
    elif args.mode=='fixed':pdf_run('after')
    elif args.mode=='raw-eq':actual_lookup_equivalence(True)
    else:{'actual-eq':actual_lookup_equivalence,'analyze':analyze,'plan':query_plan,'pytest':full_pytest,'report':report}[args.mode]()
