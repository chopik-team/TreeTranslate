"""Record the explicit diagnostic review; references remain evaluation-only."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'
def run():
    original = QA / 'diagnostic_before.json'
    production = QA / 'diagnostic/holdout_after_production.json'
    baseline = json.loads(original.read_text('utf8'))
    assert sha256(Path(baseline['source_file']).read_bytes()).hexdigest() == baseline['sha256']
    actual = {r['id']: r for r in json.loads(production.read_text('utf8'))['rows']}
    decisions = {r['id']: r for r in json.loads((QA/'diagnostic_review_decisions.json').read_text('utf8'))['rows']}
    rows = []
    for old in baseline['rows']:
        row = dict(actual[old['id']])
        unchanged = row['output'] == old['output']
        if unchanged:
            grade, reason = old['grade'], 'Identical output; immutable historical grade inherited.'
        else:
            decision = decisions.get(row['id'],{})
            sealed = (decision.get('source_sha256')==sha256(row['source'].encode('utf8')).hexdigest()
                      and decision.get('output_sha256')==sha256(row['output'].encode('utf8')).hexdigest())
            grade = decision['grade'] if sealed else 'UNREVIEWED'
            reason = decision['reason'] if sealed else 'Output changed since semantic review; a fresh explicit review is required.'
        row.update(before=old['output'], before_grade=old['grade'], grade=grade,
                   reason=reason, reference=old['reference'], unchanged=unchanged)
        rows.append(row)
    result = dict(set_id='DIAGNOSTIC_REGRESSION_SET', revision='AW0.81', final_proof=False,
        reviewer='Codex; not human-certified', immutable_reference_sha256=baseline['sha256'],
        production_result_sha256=sha256(production.read_bytes()).hexdigest(),
        references_evaluation_only=True, references_not_written_to_knowledge=True,
        before_grades=dict(Counter(r['before_grade'] for r in rows)),
        after_grades=dict(Counter(r['grade'] for r in rows)), rows=rows)
    (QA/'diagnostic_after.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(result['before_grades'], '->', result['after_grades'])


if __name__ == '__main__':
    run()
