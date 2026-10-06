"""Diagnostic error taxonomy reviewed by source/output, never Knowledge input."""
import json
from pathlib import Path
from hashlib import sha256
from collections import Counter
ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'


def run():
    original = ROOT / 'qa/aw088/holdout_semantic_review.json'
    data = json.loads(original.read_text('utf8'))
    groups = {
        'ACTION_HEADING': ['0:0','1:0','3:0','6:0','14:0','15:0','17:0'],
        'ACTION_LOSS_OR_SUBSTITUTION': ['2:3','3:2','3:4','3:7','3:12','3:13','3:14','11:3','12:1','13:1','17:1','17:3'],
        'DANGEROUS_OPPOSITE_ACTION': ['12:3','13:3'],
        'CROSS_REFERENCE': ['3:3','3:9','7:7','12:2','13:2'],
        'DIAGNOSTIC_BRANCH': ['8:5','8:6','9:5','9:6','11:4','11:5'],
        'IDENTIFIER_OR_MARKER': ['4:5','5:5','7:1','7:5'],
        'SOURCE_UNIT_AMBIGUITY': ['16:10'],
        'NATIVE_LINE_FRAGMENT': ['0:3','1:3','4:2','4:3','4:6','4:7','4:10','4:11',
            '5:2','5:3','5:6','5:7','5:10','5:11','6:1','6:2','15:1','15:2'],
        'OBJECT_OR_CONTEXT': ['0:1','1:1','2:5','3:5','3:10','4:4','4:8','4:9','4:14',
            '5:4','5:8','5:9','5:14','12:6','12:8','13:6','13:8','14:2','14:3'],
        'LABEL_OR_CONTEXT': ['4:1','5:1','10:10','14:9','17:4'],
    }
    mapping = {identifier: category for category, identifiers in groups.items() for identifier in identifiers}
    rows = []
    for row in data['rows']:
        if row['grade'] not in ('MAJOR','CATASTROPHIC'):
            continue
        assert row['id'] in mapping, row['id']
        rows.append(dict(id=row['id'], baseline_grade=row['grade'], primary_category=mapping[row['id']],
            source_sha256=sha256(row['source'].encode()).hexdigest(), member_sha256=row['sha256']))
    result = dict(set_id='DIAGNOSTIC_REGRESSION_SET', reviewer='Codex', not_human_certification=True,
        source_review_sha256=sha256(original.read_bytes()).hexdigest(),
        refs_copied_to_knowledge=False, rows=rows, counts=dict(Counter(r['primary_category'] for r in rows)),
        interpretation='Native line fragments stay diagnostic. Whole-document writer and contextual meaning are assessed separately; baseline grades are unchanged.')
    for name in ['diagnostic_error_taxonomy.json','error_taxonomy.json']:
        (QA/name).write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(result['counts'])


if __name__ == '__main__':
    run()
