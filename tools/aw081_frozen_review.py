"""Apply explicit reviewer annotations; never infer PASS from routing/confidence."""
from collections import Counter
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.documents.pdf_ocr_policy import protected_kind
from app.documents.run_metrics import content_hash
QA=ROOT/'qa/aw081/iterations/14_phase_a_closure/frozen_A_whole'

def eligible(s):
    if s.get('ocr_kind') in {'noise','identifier','measurement'} or protected_kind(s['text']):return False
    # Unchanged bare electrical identifiers/values are separate protected evidence.
    normalized=lambda t:''.join((t or '').split()).replace('：',':')
    if not re.search(r'[\u4e00-\u9fff]',s['text']) and normalized(s['translated'])==normalized(s['text']):
        if len(re.findall(r'[A-Za-z]{3,}',s['text']))<2 or not re.search('[a-z]',s['text']):return False
    return True

def run():
    recipes=json.loads((QA/'manual_annotations.json').read_text('utf8'))
    documents=[json.loads(line) for line in (QA/'documents.jsonl').read_text('utf8').splitlines()]
    rows=[];totals=Counter();reviewed=[]
    for d in documents:
        recipe=recipes.get(str(d['index']))
        if d['validation']!='PASS':continue
        for s in d['segments']:
            grade='UNREVIEWED';reason='Independent semantic review pending.'
            if not eligible(s):grade='EXCLUDED_PROTECTED_OR_OCR_NOISE';reason='Protected bare identifier/value or OCR noise; outside semantic denominator.'
            elif recipe:
                grade=recipe.get('default','UNREVIEWED')
                reason=recipe['reason']
                if recipe.get('preserved_labels') and s['policy']=='CONSERVATIVE_PRESERVE' and s.get('ocr_kind')=='diagram_label':
                    grade=recipe['preserved_labels']
                for label,ids in recipe.get('grades',{}).items():
                    if s['block_id'] in ids or f"p{s['page']+1}/{s['block_id']}" in ids:grade=label
            assert grade in {'PASS','MINOR','MAJOR','CATA','SOURCE_AMBIGUOUS','SOURCE_DAMAGED','NOT_EVALUABLE_FRAGMENT','EXCLUDED_PROTECTED_OR_OCR_NOISE','UNREVIEWED'}
            rows.append(dict(index=d['index'],block_id=s['block_id'],source=s['text'],
                candidate_translation=s['translated'],published_text=s['visible_text'],
                overflow_text=s['overflow_text'],policy=s['policy'],grade=grade,reason=reason,
                source_sha256=content_hash(s['text']),candidate_sha256=content_hash(s['translated'] or ''),
                root_cause=('ACTION_GUARD / MODEL_LIMITATION: support-device meaning lost' if grade=='CATA' else 'MODEL_LIMITATION / KNOWLEDGE_GAP / ROUTER_ERROR' if grade=='MAJOR' else None)))
            totals[grade]+=1
        if recipe:reviewed.append(d['index'])
    result=dict(reviewer='Codex; not human-certified',reviewed_documents=reviewed,
        semantic_status='COMPLETE' if totals['UNREVIEWED']==0 and len(documents)==46 else 'PARTIAL',
        grades=dict(totals),semantic_denominator=sum(totals[g] for g in ('PASS','MINOR','MAJOR','CATA')),
        document_structural_grades=dict(Counter(d['validation'] for d in documents)),rows=rows,
        quality_gate='FAIL' if totals['MAJOR'] or totals['CATA'] or any(d['validation']!='PASS' for d in documents) else 'PENDING',
        first_use_consumed=True,no_fixes_allowed=True,next_untouched_evaluation_requires='FROZEN_B',
        policy='Short diagram labels conservatively retained as source are reviewed as publication MINOR if no wrong target is inserted. Full untranslated prose or lost technical meaning is MAJOR. Protected values are reported separately, not semantic PASS.')
    (QA/'semantic_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(result['semantic_status'],dict(totals),flush=True)

if __name__=='__main__':run()
