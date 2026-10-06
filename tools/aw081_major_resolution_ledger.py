"""Track the original 51 MAJOR cases without changing references or grades."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'


def run():
    initial_path = QA / 'major_root_causes.json'
    current_path = QA / 'diagnostic_after.json'
    initial = json.loads(initial_path.read_text('utf8'))
    current = json.loads(current_path.read_text('utf8'))
    actual = {row['id']: row for row in current['rows']}
    assert len(actual) == 157 and len(initial['rows']) == 51
    rows = []
    for old in initial['rows']:
        row = actual[old['id']]
        assert sha256(row['source'].encode('utf8')).hexdigest() == old['source_text_sha256']
        selected = [match for event in row['events'] if event['layer']=='glossary_lookup'
                    for match in event.get('selected',[])]
        rows.append(dict(id=row['id'],source_file_sha256=old['source_file_sha256'],
            source_text_sha256=old['source_text_sha256'],source=row['source'],
            initial_output=old['current_output'],output=row['output'],grade=row['grade'],
            output_sha256=sha256(row['output'].encode('utf8')).hexdigest(),
            initial_cause=old['root_cause'],responsible_layer=old['responsible_layer'],
            status='FIXED_REVIEWED' if row['grade']=='PASS' else 'OPEN',
            reason=row['reason'],route_reason=row['route_reason'],
            constraint_status=row['constraint_status'],knowledge_source=row['knowledge_source'],
            backend=row['backend'],fallback_used=row['fallback_used'],
            selected_knowledge=selected,
            selected_templates=[event for event in row['events']
                                if event['layer']=='template' and event.get('selected_template')],
            native_layout_matches=old['native_layout_matches'],
            raw_line_is_part_of_larger_native_block=old['raw_line_is_part_of_larger_native_block']))
    result = dict(revision='AW0.81',scope='Original 51 MAJOR diagnostic cases; no new acceptance set.',
        initial_inventory_sha256=sha256(initial_path.read_bytes()).hexdigest(),
        current_review_sha256=sha256(current_path.read_bytes()).hexdigest(),
        raw_diagnostic_grades=current['after_grades'],
        statuses=dict(Counter(row['status'] for row in rows)),
        open_cause_groups=dict(Counter(row['initial_cause'] for row in rows if row['status']=='OPEN')),
        references_evaluation_only=True,final_semantic_gate_passed=False,rows=rows)
    (QA / 'major_resolution_ledger.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(result['statuses'], result['open_cause_groups'])


if __name__ == '__main__':
    run()
