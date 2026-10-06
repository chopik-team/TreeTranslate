"""Refresh regression evidence without regrading changed outputs implicitly."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT/'qa/aw081'


def load(path):
    return json.loads(path.read_text('utf8'))


def save(name,value):
    (QA/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8')


def run():
    current = QA/'coolant_e2e.json'
    data = load(current)
    actual = [s for doc in data['documents'] for s in doc['segments']]
    baseline = ROOT/'qa/aw088/coolant_regression.json'
    previous = {r['index']:r for r in load(QA/'coolant_regression.json')['rows']}
    rows = []
    for old in load(baseline)['rows']:
        segment = actual[old['index']]
        assert segment['text']==old['source']
        digest = sha256((segment['translated'] or '').encode('utf8')).hexdigest()
        decision = previous.get(old['index'],{})
        if segment['translated']==old['after']:
            grade, reason = old['after_grade'],'Identical historical reviewed output.'
        elif decision.get('source')==segment['text'] and decision.get('output_sha256')==digest:
            grade, reason = decision['after_grade'],decision['reason']
        else:
            grade, reason = 'UNREVIEWED','Changed output requires a fresh explicit semantic review.'
        rows.append(dict(index=old['index'],source=segment['text'],before=old['after'],after=segment['translated'],
                         output_sha256=digest,before_grade=old['after_grade'],after_grade=grade,reason=reason))
    counts = Counter(r['after_grade'] for r in rows)
    noise = counts.pop('EXCLUDED_OCR_NOISE',0)
    before = Counter(r['before_grade'] for r in rows)
    before.pop('EXCLUDED_OCR_NOISE',None)
    save('coolant_regression.json',dict(revision='AW0.81',reviewer='Codex; not human-certified',
        historical_review_sha256=sha256(baseline.read_bytes()).hexdigest(),
        run_sha256=sha256(current.read_bytes()).hexdigest(),
        source_unchanged=data['source_hash_before']==data['source_hash_after'],
        segments=len(actual),reviewed_semantic_segments=len(actual)-noise,noise_excluded=noise,
        before_grades=dict(before),after_grades=dict(counts),rows=rows,
        seconds=data['elapsed'],timing_is_calibration=False,
        semantic_gate_passed=not any(counts[k] for k in ('MAJOR','CATASTROPHIC','UNREVIEWED'))))
    body = load(QA/'body_quality.json')
    save('body_regression.json',dict(revision='AW0.81',run_sha256=sha256((QA/'body_e2e.json').read_bytes()).hexdigest(),
        source_immutable=body['source_immutable'],crc_ok=body['crc_ok'],metrics=body['after'],
        instructions=body['stable_instructions'],seconds=body['wall_seconds'],timing_is_calibration=False))
    print('coolant',dict(counts),'noise',noise,'body',body['after'])


if __name__=='__main__':
    run()
