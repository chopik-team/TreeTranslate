"""LEVEL 2 semantic probes over frozen production extraction, without PDF writing."""
from hashlib import sha256
import json
from pathlib import Path
import re
from time import perf_counter
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'


def read(path):
    return json.loads(path.read_text('utf8'))


def freeze_inputs():
    destination = QA/'text_regression_inputs.json'
    if destination.exists():
        return destination
    documents, cases, hashes = [], [], {}
    for mode in ('coolant','body'):
        path = QA/(mode+'_e2e.json')
        data = read(path)
        hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
        for doc in data['documents']:
            documents.append(dict(mode=mode,file=doc['file'],segments=doc['segments']))
        review_path = QA/(mode+'_regression.json')
        reviewed = read(review_path)
        hashes[str(review_path.relative_to(ROOT))] = sha256(review_path.read_bytes()).hexdigest()
        if mode=='coolant':
            assert len(data['documents'])==1
            doc = data['documents'][0]
            for row in reviewed['rows']:
                if row['after_grade']=='EXCLUDED_OCR_NOISE':
                    continue
                segment = doc['segments'][row['index']]
                assert segment['text']==row['source']
                cases.append(dict(mode=mode,file=doc['file'],segment=segment,
                    expected=row['after'],grade=row['after_grade'],review=row['reason']))
        else:
            for row in reviewed['instructions']:
                matches = [(doc,segment) for doc in data['documents'] for segment in doc['segments']
                           if re.sub(r'\s+','',segment['text'])==re.sub(r'\s+','',row['source'])]
                assert len(matches)==1
                doc,segment = matches[0]
                assert segment['translated']==row['output']
                cases.append(dict(mode=mode,file=doc['file'],segment=segment,
                    expected=row['output'],grade=row['status'],review='Accepted body instruction review.'))
    assert sum(c['mode']=='coolant' for c in cases)==94
    assert sum(c['mode']=='body' for c in cases)==10
    destination.write_text(json.dumps(dict(revision='AW0.81',frozen_before_action_group=True,
        extraction_source_hashes=hashes,documents=documents,cases=cases,
        references_evaluation_only=True),ensure_ascii=False,indent=2)+'\n','utf8')
    return destination


def run():
    from app.engine.factory import create_translation_engine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.documents.job import DocumentJob, DocumentConfig
    from app.documents.control import JobControl
    from app.knowledge.segments import SegmentClassifier
    from tools.aw081_diagnostic_evaluate import Trace

    inputs = freeze_inputs()
    data = read(inputs)
    paths = list((ROOT/'app').rglob('*.py')) + list((ROOT/'assets/config').glob('*.json'))
    paths += list(bundled_paths()) + [ROOT/'assets/knowledge/manifest.json']
    sealed = {path:sha256(path.read_bytes()).hexdigest() for path in paths}
    engine = create_translation_engine(memory=TranslationMemoryEngine(QA/'text-probe-isolated-tm.db'),
        glossary=GlossaryEngine(QA/'text-probe-isolated-user.db',builtin_paths=bundled_paths()))
    trace = Trace(engine,capture_events=True)
    rows, timings = [], []
    started = perf_counter()
    try:
        with engine.runtime.keep_warm():
            for doc in data['documents']:
                cases = [c for c in data['cases'] if (c['mode'],c['file'])==(doc['mode'],doc['file'])]
                if not cases:
                    continue
                begin = perf_counter()
                profile = engine.profile_document('zh','ru',identity='text-probe:'+doc['mode']+':'+doc['file'],
                    segments=[s['text'] for s in doc['segments']],filename=doc['file'])
                job = DocumentJob([],DocumentConfig(source='zh',target='ru',domain='auto'),
                    JobControl(),trace.translate,engine.languages.resolve)
                job._domain,job._context_profile=profile.primary_domain,profile
                job._snapshot=engine.context_router.snapshot(profile)
                for case in cases:
                    segment = case['segment']
                    job._segment_type=SegmentClassifier.classify(segment['text'],segment=SimpleNamespace(**segment)).value
                    trace.events.clear();trace.results.clear()
                    output = job._pdf_translation(segment['text'],'zh','ru')
                    unchanged = output==case['expected']
                    rows.append(dict(mode=doc['mode'],file=doc['file'],block_id=segment['block_id'],
                        source=segment['text'],source_sha256=sha256(segment['text'].encode()).hexdigest(),
                        before=case['expected'],output=output,output_sha256=sha256(output.encode()).hexdigest(),
                        before_grade=case['grade'],grade=case['grade'] if unchanged else 'UNREVIEWED',
                        unchanged=unchanged,segment_type=job._segment_type,events=list(trace.events)))
                timings.append(dict(mode=doc['mode'],file=doc['file'],cases=len(cases),seconds=perf_counter()-begin))
                print('TEXT',doc['mode'],len(cases),round(perf_counter()-begin,2),flush=True)
    finally:
        engine.shutdown()
    assert all(sha256(p.read_bytes()).hexdigest()==h for p,h in sealed.items())
    result=dict(revision='AW0.81',level=2,input_sha256=sha256(inputs.read_bytes()).hexdigest(),
        scope='Cached production extraction; semantic mechanism probe, not PDF/OCR/layout/render acceptance.',
        final_proof=False,pdf_checks_replaced=False,seconds=perf_counter()-started,
        timing_is_calibration=False,timings=timings,rows=rows,
        changed=[dict(mode=r['mode'],file=r['file'],block_id=r['block_id']) for r in rows if not r['unchanged']])
    (QA/'text_regression_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print('Text probe changed',len(result['changed']),'/',len(rows))


if __name__=='__main__':
    run()
