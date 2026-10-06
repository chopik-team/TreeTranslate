"""Capture the accepted reference before scheduler changes; no benchmark."""
import json
from dataclasses import asdict
from pathlib import Path
from tools.aw081_speed_calibration_100 import frozen_hashes

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT/'qa/aw081/adaptive_pipeline'

def capture():
    QA.mkdir(parents=True, exist_ok=True)
    reference = ROOT/'qa/aw081/glossary_hot_path/runs/after'
    stages = [
        dict(stage='inventory/extract', resources='IO/CPU', owner='archive/read-only reader', shared='ZIP handles, path reservations', lock='single ZIP owner; separate reader handle', overlap='different documents; no shared ZipFile'),
        dict(stage='native/page/OCR', resources='CPU/GPU', owner='one prepare worker', shared='PDFium global state, run OCR runtime', lock='unchanged PDF_LOCK; OCR runtime RLock; GPU admission', overlap='detached semantic IR only; cannot overlap PDF writer'),
        dict(stage='profile/snapshot/glossary', resources='CPU/SQLite', owner='semantic owner', shared='KnowledgeRouter mutable maps/counters; thread-local glossary connections', lock='existing glossary RLock', overlap='writer; no concurrent context mutations'),
        dict(stage='NMT/guards', resources='GPU/CPU', owner='semantic owner', shared='runtime loaded backends/circuit breaker', lock='existing RuntimeManager RLock plus GPU admission', overlap='writer/native CPU; OCR inference serial'),
        dict(stage='write/validate', resources='CPU/IO', owner='one writer', shared='PDFium; per-document FontResolver; immutable font_bytes LRU', lock='unchanged PDF_LOCK', overlap='semantic/NMT; no parallel PDFium or writers'),
        dict(stage='archive append/publish', resources='IO', owner='archive owner', shared='staging ZIP, output collision reservations', lock='one owner; JobControl publication condition', overlap='different document stages; canonical sequence only'),
        dict(stage='diagnostics', resources='SQLite/IO', owner='serialized observers', shared='LocalRun streams/database/pending/counters', lock='currently SQLite creator-thread only; requires synchronized handoffs', overlap='per-task ContextVars; serialize storage writes'),
    ]
    value = dict(reference_run_id='07e4d3b8a299', reference=str(reference),
        execution=json.loads((reference/'execution.json').read_text('utf8')),
        summary=json.loads((reference/'run_summary.json').read_text('utf8')),
        production_before=frozen_hashes(), architecture=stages,
        frozen_helpers={p: __import__('hashlib').sha256((ROOT/p).read_bytes()).hexdigest()
            for p in ['tools/aw081_hardware_scaling_20.py','tools/aw081_hardware_support.py']})
    target=QA/'baseline.json'
    if target.exists():
        raise RuntimeError('Baseline already captured; do not overwrite pre-change evidence')
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')
    print('Captured architecture and accepted 451.46 s reference')

if __name__=='__main__':capture()
