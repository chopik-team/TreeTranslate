"""Frozen whole-document representative text evaluation using production engine."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw088_prepare import QA,save


def freeze():
    destination=QA/'representative_holdout.json'
    if destination.exists():return
    held=json.loads((QA/'frozen_holdout_manifest.json').read_text('utf-8'))
    allowed={d['member']:d for d in held['documents']};choices={}
    with sqlite3.connect(QA/'native_corpus.db') as con:
        for member,_,_,raw in con.execute('SELECT * FROM documents ORDER BY member'):
            if member not in allowed:continue
            doc=json.loads(raw);lines=doc.get('lines',[]);item=allowed[member]
            if not (doc.get('pages')==1 and 3<=len(lines)<=16 and 50<=sum(map(len,lines))<=700):continue
            branch=item['stratum']
            if branch in {'general','software','industrial.hydraulics'}:continue
            choices.setdefault(branch,[]).append((sha256(('representative:'+member).encode()).hexdigest(),dict(item,lines=lines)))
    selected=[item for branch,items in sorted(choices.items()) for _,item in sorted(items)[:2]]
    save(destination.name,dict(frozen_before_knowledge_build=True,
        definition='Entire native text of two short whole held PDF documents per represented branch; no training on held content.',
        documents=selected,manifest_sha256=sha256((QA/'frozen_holdout_manifest.json').read_bytes()).hexdigest()))
    print('Representative documents',len(selected),'lines',sum(len(d['lines']) for d in selected),flush=True)


def evaluate(stage):
    from app.engine.factory import create_translation_engine
    from app.engine.types import TranslationRequest
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.knowledge.segments import SegmentClassifier
    freeze();frozen=QA/'representative_holdout.json';before=sha256(frozen.read_bytes()).hexdigest()
    knowledge_files=[ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db',*sorted((ROOT/'assets/config').glob('*knowledge*.json')),ROOT/'assets/config/automotive-slot-forms.json',ROOT/'assets/config/technical-actions.json']
    sealed={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in knowledge_files}
    cases=json.loads(frozen.read_text('utf-8'))['documents']
    production=stage.endswith('_production')
    baseline=stage=='before_production'
    paths=[QA/'baseline/aw083-body-repair-zh-ru.db'] if baseline else bundled_paths()
    engine=create_translation_engine(memory=TranslationMemoryEngine(QA/f'{stage}-isolated-tm.db'),
        glossary=GlossaryEngine(QA/f'{stage}-isolated-user.db',builtin_paths=paths))
    if baseline:
        from app.knowledge.profile import DocumentProfiler
        engine.context_router.profiler=DocumentProfiler(json.loads((QA/'baseline/knowledge-context.json').read_text('utf8')))
        engine.context_router.templates=json.loads((QA/'baseline/knowledge-templates.json').read_text('utf8'))['templates']
        engine.context_router.slot_forms={f['source']:f for f in json.loads((QA/'baseline/automotive-slot-forms.json').read_text('utf8'))['forms']}
    if production:
        from app.documents.job import DocumentJob,DocumentConfig
        from app.documents.control import JobControl
        from app.documents.pdf_fidelity import FidelityMismatch
        trace=[];translate=engine.translate
        def traced(request,*args,**kwargs):
            result=translate(request,*args,**kwargs);trace.append(result);return result
        job=DocumentJob([],DocumentConfig(source='zh',target='ru',domain='auto'),JobControl(),traced,engine.languages.resolve)
    rows=[];start=perf_counter();snapshots=[]
    try:
        with engine.runtime.keep_warm():
            for index,doc in enumerate(cases):
                p=engine.profile_document('zh','ru',identity=doc['sha256'],segments=doc['lines'],filename=doc['member'],folders=(doc['member'],))
                snapshot=engine.context_router.snapshot(p);snapshots.append(dict(member=doc['member'],entries=len(snapshot.entries),bytes=snapshot.bytes_estimate))
                for offset,line in enumerate(doc['lines']):
                    typ=SegmentClassifier.classify(line).value
                    if production:
                        job._domain=p.primary_domain;job._context_profile=p;job._snapshot=snapshot;job._segment_type=typ;trace.clear()
                        try:output=job._pdf_translation(line,'zh','ru')
                        except FidelityMismatch:output=line
                        r=trace[-1] if trace else None
                        backend=r.backend if r else 'protected';knowledge_source=r.knowledge_source if r else 'protected'
                    else:
                        r=engine.translate(TranslationRequest(line,'zh','ru',context_profile=p,knowledge_snapshot=snapshot,segment_type=typ))
                        output=r.translated_text;backend=r.backend;knowledge_source=r.knowledge_source
                    rows.append(dict(id=f'{index}:{offset}',member=doc['member'],sha256=doc['sha256'],stratum=doc['stratum'],
                        source=line,output=output,backend=backend,knowledge_source=knowledge_source,
                        segment_type=typ,profile=p.summary()))
                print(stage,index+1,len(cases),'segments',len(rows),'seconds',round(perf_counter()-start,2),flush=True)
        assert sha256(frozen.read_bytes()).hexdigest()==before
        assert sealed=={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in knowledge_files}
        save(f'holdout_{stage}.json',dict(stage=stage,seconds=perf_counter()-start,holdout_sha256=before,
            manifest_unchanged=True,knowledge_hashes=sealed,knowledge_unchanged=True,production_pdf_normalization=production,
            baseline_reconstructed_from_prebuild_snapshot=baseline,whole_documents=len(cases),segments=len(rows),rows=rows,
            knowledge_sources=dict(Counter(r['knowledge_source'] for r in rows)),
            snapshots=snapshots,metrics=dict(engine.context_router.metrics)))
    finally:engine.shutdown()

if __name__=='__main__':
    freeze() if sys.argv[1]=='freeze' else evaluate(sys.argv[1])
