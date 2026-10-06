"""Explicit semantic review evidence; never consumed by pack builders."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw087_build import QA,save

def held():
    result=json.loads((QA/'semantic_holdout_results.json').read_text('utf-8'))
    major={'body-014','engine-044','suspension-059','brakes-074','electrical-089','diagnostics-104','service_procedure-119'}
    for row in result['rows']:
        if row['exact']:reason='Exact frozen reference';grade='PASS'
        elif row['id'] in major:reason='Wrong component concept in condition; stopping action remains present';grade='MAJOR'
        else:reason='Entity and condition preserved; Russian grammar, infinitive or omitted repetition';grade='MINOR'
        row.update(grade=grade,review_reason=reason)
    result.update(grades=dict(Counter(r['grade'] for r in result['rows'])),reviewer='Codex explicit semantic review; not independent human certification',
        reference_errata='Several frozen prose references use a masculine predicate with feminine/neuter objects. Original references are preserved; grades use source meaning, not those grammar errors.',
        knowledge_not_updated_from_failures=True)
    save('semantic_holdout_results.json',result);print('Reviewed held',result['grades'])

def coolant():
    before=json.loads((ROOT/'qa/aw086/coolant_e2e.json').read_text('utf-8'))['documents'][0]['segments']
    after=json.loads((QA/'coolant_e2e.json').read_text('utf-8'))['documents'][0]['segments']
    # Review of every published semantic block, including diagnostic UI labels;
    # preserved OCR noise is explicitly excluded, not counted as correct text.
    noise={i for i,s in enumerate(after) if s['text']=='目'}
    old_major={0,2,3,4,5,6,7,8,11,13,16,19,20,24,25,28,29,30,31,32,33,34,35,36,37,38,
        42,43,45,47,49,60,61,63,65,67,69,71,72,73,76,78,81,84,85,89,90,91,92,93,94,97,98,99,100,102,103,104,105,106,107}
    new_major={8,18,36,49,60,65,73,83,107}
    old_major.update({18,83})
    new_minor={21,22,23,86,87,88}
    rows=[]
    for i,(old,new) in enumerate(zip(before,after)):
        assert old['text']==new['text']
        grade='EXCLUDED_OCR_NOISE' if i in noise else 'MAJOR' if i in new_major else 'MINOR' if i in new_minor else 'PASS'
        old_grade='EXCLUDED_OCR_NOISE' if i in noise else 'MAJOR' if i in old_major else 'MINOR' if i in new_minor else 'PASS'
        rows.append(dict(index=i,source=new['text'],before=old['translated'],after=new['translated'],before_grade=old_grade,after_grade=grade,
            reason='Converted capacity units are not reliable; values alone do not certify unit meaning' if i in {18,83} else
                'Malformed cross-reference or ambiguous diagnostic/OCR label still incorrectly rendered' if i in new_major else
                'Source concentration wording/converted-unit label remains ambiguous; values preserved' if i in new_minor else
                'Noise deliberately preserved' if i in noise else 'Action/object/condition and identifiers preserved; Russian construction reviewed'))
    save('coolant_semantic_review.json',dict(rows=rows,before_grades=dict(Counter(r['before_grade'] for r in rows)),
        after_grades=dict(Counter(r['after_grade'] for r in rows)),reviewer='Codex source/output review; not independent human or OEM certification',
        cata_policy='Negation inversion, dangerous action reversal or corrupted protected quantity. None observed in this review.'))
    print('Coolant reviewed',Counter(r['after_grade'] for r in rows))

if __name__=='__main__':held();coolant()
