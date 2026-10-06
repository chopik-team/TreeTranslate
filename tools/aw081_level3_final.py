"""Fresh production BODY ZIP and coolant PDF with local observer enabled."""
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import aw086_e2e, aw086_analyze
from tools.aw081_large_zip import production_hashes
from app.documents.run_metrics import LocalRun, file_hash

QA=ROOT/'qa/aw081/iterations/14_phase_a_closure/level3'
QA.mkdir(exist_ok=False)
aw086_e2e.QA=QA
aw086_analyze.QA=QA
original_read=aw086_analyze.read
aw086_analyze.read=lambda path:original_read(path.replace('qa/aw086/',str(QA.relative_to(ROOT)).replace('\\','/')+'/'))
sealed=production_hashes()
started=perf_counter()
for mode in ('body','coolant'):
    observer=LocalRun(QA/'logs',metadata=dict(scope='LEVEL_3_DEV_REGRESSION',mode=mode,production_hashes=sealed))
    with observer.activate():
        try:
            aw086_e2e.run(mode,cycle='aw081/phase-a-14-level3',capture_routes=True)
        except BaseException as error:
            observer.close('FAILED',error)
            raise
        else:observer.close()
    assert not observer.logging_failed
    run=json.loads((QA/(mode+'_e2e.json')).read_text('utf8'))
    summary=json.loads((observer.directory/'run_summary.json').read_text('utf8'))
    documents=[json.loads(line) for line in (observer.directory/'documents.jsonl').read_text('utf8').splitlines()]
    assert summary['counters']['documents']==len(run['documents'])==len(documents)
    assert all(d['source_immutable'] and d['output_sha256'] for d in documents)
    assert run['source_hash_before']==run['source_hash_after']
    for d in documents:
        c=d['counters']
        assert c.get('knowledge_segments',0)<=c.get('eligible_semantic_segments',0)
        assert c.get('model_fallback_segments',0)<=c.get('semantic_segments',0)
    if mode=='body':
        assert run['crc_ok'] and len(run['documents'])==7
        assert all(d['source_pages']==d['output_pages'] for d in run['documents'])
        aw086_analyze.body()
    else:aw086_analyze.coolant()
assert production_hashes()==sealed
report=dict(revision='AW0.81',structural_checks='PASS',semantic_acceptance='PENDING_EXPLICIT_REVIEW',
            seconds=perf_counter()-started,production_hashes=sealed,
            evidence_hashes={p.name:file_hash(p) for p in QA.glob('*.json')},
            history_preserved=True,source_immutable=True,large_zip_translation_started=False,frozen_A_used=False)
(QA/'execution.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print('LEVEL3_STRUCTURAL_PASS',report['seconds'],flush=True)
