"""Record the four-page visual review performed by Codex after Poppler rendering."""
import json
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/aw081/iterations/15_diagnostic_live_readiness/operational'
manifest=json.loads((QA/'cata_render/manifest.json').read_text('utf8'))
cases=manifest['cases']
assert len(cases)==4
for case in cases:
    assert case['full_instruction_in_published_text'] and not case['safety_guard_issues']
    case.update(grade='PASS_KNOWN_SAFETY_CASE',visual_review='PASS',
        png_sha256=sha256(Path(case['png']).read_bytes()).hexdigest())
result=dict(scope='FOUR_KNOWN_CATA_ONLY_NOT_FULL_DOCUMENT_QUALITY',reviewer='Codex; not independent human certification',
    known_cata_remaining=0,published_cases_reviewed=4,rendered_pages_reviewed=4,cases=cases,
    conclusion='Jack/tool and edge/below/support relations retained before mount removal; bleed screw tightened; assistant presses fully and holds pedal depressed. All four are legible, complete and without overlap in their instruction areas.',
    other_blocks_not_regraded=True,whole_document_semantic_acceptance=False,
    known_table_overlaps_24_25_remain_open=True)
(QA/'cata_publication_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
print('KNOWN_CATA_REMAINING',result['known_cata_remaining'])
