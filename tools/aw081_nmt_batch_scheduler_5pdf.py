"""One baseline/final on five frozen NMT-heavy members; no larger PDF runs."""
from collections import Counter,defaultdict
from contextvars import ContextVar
from dataclasses import asdict
import copy
import inspect
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw081_100pdf_final_speed_calibration import read,save,frozen_hashes
QA=ROOT/'qa/aw081/nmt_batch_scheduler_5pdf'
REF=ROOT/'qa/aw081/100pdf_final_speed_calibration'


def require_exact_replay(record):
    """Fail closed before creating any measured final run directory."""
    results=record.get('results',{})
    if not record.get('pass_') or any(
            not results.get(str(size),{}).get('exact_prepared_inputs')
            or not results.get(str(size),{}).get('exact_outputs')
            or results.get(str(size),{}).get('mismatches')
            for size in (1,2,4,8)):
        raise RuntimeError('Final fixed5 forbidden: mandatory exact native replay did not pass')


def prepare():
    assert not (QA/'sample_manifest.json').exists()
    m=read(REF/'sample_manifest.json');summary=read(REF/'run_summary.json')
    obs=read(REF/'raw/observations.json')['nmt'];scores=defaultdict(Counter)
    previous={}
    for r in obs['batches']:
        s=scores[r['member']];s['calls']+=1;s['inference_seconds']+=r['seconds']
        s['short_batch1']+=r['sequences']==1 and r['tokens']<=32
    for r in obs['requests']:
        key=(r['backend'],r['options']['device'],r['options']['compute_type'])
        scores[r['member']]['transitions']+=r['member'] in previous and previous[r['member']]!=key
        scores[r['member']]['failed_attempts']+='error_type' in r;previous[r['member']]=key
    docs={d['archive_member_path']:d for d in summary['documents']};chosen=[];rules=[]
    for name,metric,predicate in [
        ('max_CT2_calls','calls',lambda d:True),('max_CT2_inference','inference_seconds',lambda d:True),
        ('max_short_batch1','short_batch1',lambda d:True),('max_backend_transitions','transitions',lambda d:True),
        ('mixed_OCR_significant_NMT','inference_seconds',lambda d:docs[d['member_path']].get('ocr_regions',0)>0 or docs[d['member_path']].get('classification') in {'mixed','image_only'})]:
        eligible=[d for d in m['documents'] if d['index'] not in chosen and predicate(d)]
        d=sorted(eligible,key=lambda d:(-scores[d['member_path']][metric],d['index']))[0]
        chosen.append(d['index']);rules.append(dict(category=name,index=d['index'],metric=metric,value=scores[d['member_path']][metric]))
    selected=[copy.deepcopy(d) for d in m['documents'] if d['index'] in chosen]
    QA.mkdir(parents=True,exist_ok=True);archive=QA/'CN7C_NMT_FIXED5.zip'
    from hashlib import sha256
    with ZipFile(m['sample_archive']) as source,ZipFile(archive,'x',compression=ZIP_DEFLATED) as out:
        for d in selected:
            data=source.read(d['member_path']);assert sha256(data).hexdigest()==d['source_sha256']
            out.writestr(copy.copy(source.getinfo(d['member_path'])),data)
            d['nmt_reference_metrics']=dict(scores[d['member_path']])
    frozen=dict(m,documents=selected,sample_count=5,sample_archive=str(archive),sample_archive_sha256=sha256(archive.read_bytes()).hexdigest(),
        selection=rules,selection_reference_run='736fc7a72805',short_request_token_threshold=32,frozen=True,
        order='Original historical100 canonical indices; unique maxima in category order; ties original index')
    save(QA/'sample_manifest.json',frozen);print(json.dumps(rules),flush=True)


def run(role):
    assert role in {'baseline','after'}
    if role=='after':require_exact_replay(read(QA/'batch_replay.json'))
    target=QA/'runs'/role;assert not target.exists(),'Exactly one measured run for each role'
    target.mkdir(parents=True);m=read(QA/'sample_manifest.json');save(target/'sample_manifest.json',m)
    before=frozen_hashes();save(target/'run_manifest.json',dict(production_hashes_before=before,
        dictionary_sha256=read(REF/'run_manifest.json')['dictionary_sha256'],source_sha256=m['input_archive_sha256'],
        role=role,settings='Current production defaults, ORIGINAL, no benchmark resource caps',warmup=dict(seconds=0,contents=[])))
    from tools import aw081_100pdf_final_speed_calibration as harness
    from app.documents.job import DocumentJob
    from app.documents import run_metrics as metrics
    from app.glossary.engine import GlossaryEngine
    active=ContextVar('qa_nmt_segment',default=None);traces=[];candidates=[]
    original_segment=__import__('app.documents.job',fromlist=['semantic_segment']).semantic_segment
    from contextlib import contextmanager
    @contextmanager
    def segment(item,kind=''):
        token=active.set(dict(id=getattr(item,'block_id',None),page=getattr(item,'page',None),source=item.text,kind=kind))
        try:
            with original_segment(item,kind):yield
        finally:active.reset(token)
    module=__import__('app.documents.job',fromlist=['semantic_segment']);module.semantic_segment=segment
    lookup=GlossaryEngine.lookup
    def observed_lookup(engine,text,source,target,domain='general',context='',**kw):
        result=lookup(engine,text,source,target,domain,context,**kw)
        doc=metrics._doc.get();request=kw.get('request');profile=getattr(request,'context_profile',None)
        traces.append(dict(member=doc.data.get('archive_member_path') if doc else None,segment=active.get(),text=text,
            languages=[source,target],domain=domain,context=context,profile=asdict(profile) if profile else None,
            snapshot=getattr(kw.get('snapshot'),'signature',None),matches=[asdict(x) for x in result],plan=asdict(engine.codec.encode(text,result))))
        return result
    GlossaryEngine.lookup=observed_lookup
    route=DocumentJob._record_route
    def observed_route(job,result):
        route(job,result);doc=metrics._doc.get()
        value=asdict(result);value.pop('duration_ms',None);value.pop('request_id',None)
        candidates.append(dict(member=doc.data.get('archive_member_path') if doc else None,segment=active.get(),result=value))
    DocumentJob._record_route=observed_route
    # Only QA cardinality/destination change; the application pipeline and all defaults remain intact.
    source=inspect.getsource(harness.run).replace('len(scan.files)==100','len(scan.files)==5').replace('selected_files=100','selected_files=5').replace("'/100'","'/5'").replace('FINAL_100PDF_CALIBRATION_ONLY','NMT_FIXED5_ONLY')
    namespace=dict(harness.__dict__,QA=target);exec(compile(source,'<QA fixed5 cardinality>','exec'),namespace)
    try:namespace['run']()
    finally:
        module.semantic_segment=original_segment;GlossaryEngine.lookup=lookup;DocumentJob._record_route=route
        save(target/'raw/glossary_contracts.json',traces);save(target/'raw/candidates.json',candidates)
    receipt=read(target/'run_manifest.json');assert receipt['fatal'] is None
    save(QA/(role+'.json'),dict(role=role,wall_seconds=receipt['wall_seconds'],run_id=receipt['run_id'],receipt=str(target/'run_manifest.json'),
        nmt=read(target/'raw/observations.json')['nmt'],production_before=before,production_after=frozen_hashes()))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','baseline','after']);args=p.parse_args()
    prepare() if args.mode=='prepare' else run(args.mode)
