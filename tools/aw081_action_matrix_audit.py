"""Independent conformance cases for the configured guard, not model QA."""
from hashlib import sha256
import json
from pathlib import Path

from app.knowledge.safety import COMMANDS, OPPOSITES, action_records, source_actions, violations

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'


def run():
    records = {row['semantic_id']: row for row in action_records()}
    sources = {key: row['zh'][0] + '测试机构。' for key, row in records.items()}
    sources.update(STOP='关闭发动机。', APPLY_POWER='通电。', REMOVE_POWER='切断测试机构电源。',
                   CUT='剪断测试导线。')
    targets = {key: row['imperative'] + ' тестовый механизм.' for key, row in records.items()}
    targets['CUT'] = 'Разрежьте тестовый провод.'
    targets['APPLY_POWER'] = 'Подайте питание тестового механизма.'
    targets['REMOVE_POWER'] = 'Отключите питание тестового механизма.'
    rows = []
    for concept, opposites in OPPOSITES.items():
        for opposite in opposites:
            expected = f'action:{concept}:{opposite}'
            found = violations(sources[concept], targets[opposite])
            rows.append(dict(source_action=concept, substituted_action=opposite,
                source=sources[concept], dangerous_target=targets[opposite],
                source_action_detected=concept in source_actions(sources[concept]),
                expected_rejection=expected, actual_rejections=found, passed=expected in found))
    config = ROOT / 'assets/config/technical-action-safety.json'
    result = dict(revision='AW0.81',scope='Configured incompatible-action guard conformance; not all-action preservation or unseen model acceptance.',
        config_sha256=sha256(config.read_bytes()).hexdigest(), configured_patterns=len(COMMANDS),
        configured_source_actions=len(OPPOSITES), verified_registry_actions=len(records),
        registry_actions_without_target_patterns=sorted(set(records)-set(COMMANDS)),
        patterns_without_incompatible_pairs=sorted(set(COMMANDS)-set(OPPOSITES)),
        cases=len(rows), passed=sum(r['passed'] for r in rows), rows=rows,
        open_requirement='Lost-action detection and semantic ID equality for all high-confidence roles still require separate implementation and evidence.')
    (QA / 'action_safety.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print('incompatible action cases',result['passed'],'/',result['cases'],
          'registry actions without target patterns',len(result['registry_actions_without_target_patterns']))
    assert all(r['passed'] and r['source_action_detected'] for r in rows)


if __name__ == '__main__':
    run()
