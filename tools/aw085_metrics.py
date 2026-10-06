"""Measure the unchanged PDF acceptance invariants and distinguish residue causes."""
import json
import re
import sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw085_knowledge import QA,save
from tools.qa_aw083_metrics import normalize,effective
from app.documents.pdf_ocr_policy import compact_label
from app.documents.measurements import collect,MEASUREMENTS_DIR

# Evaluation-only declension/coordination variants; production never reads these.
# The original strict substring score remains alongside this concept score.
FORMS={
 '卷尺':r'рулетк\w*', '轨距仪':r'кузовн\w+\s+(?:измерительн\w+\s+)?линейк\w*',
 '探头':r'измерительн\w+\s+наконечник\w*','量规':r'линейк\w*',
 '测量点':r'точ(?:к|ек)\w*\s+измерени\w*','车身尺寸':r'размер\w+\s+кузов\w*',
 '投影尺寸':r'проекционн\w+(?:\s+и\s+фактическ\w+)?\s+размер\w*',
 '实际':r'фактическ\w+\s+размер\w*','高度':r'высот\w*',
 '前门':r'передн\w+\s+двер\w*','后门':r'задн\w+\s+двер\w*',
 '前侧构件':r'передн\w+\s+лонжерон\w*','前副车架':r'передн\w+\s+подрамник\w*',
}

def concept_found(term,text):
    return normalize(compact_label(term['expected'])) in normalize(compact_label(text)) or bool(
        term['source'] in FORMS and re.search(FORMS[term['source']],text,re.I))

def residue_class(segment,ocr_kind=''):
    visible=effective(segment)
    if not re.search('[\u4e00-\u9fff]',visible):return None
    if ocr_kind=='noise':return 'C_OCR_noise_intentionally_preserved'
    if segment.get('translated') and segment['translated']!=segment['text']:
        return 'B_translation_available_placement_preserved'
    return 'A_translation_unavailable'

def main():
    collect()
    gold=json.loads((ROOT/'qa/aw083/body_dimensions_gold.json').read_text('utf-8'))
    after=json.loads((QA/'accepted_segments.json').read_text('utf-8'))
    before=json.loads((ROOT/'qa/aw083/accepted_segments.json').read_text('utf-8'))
    reviews=[];metrics={}
    for mode,run in [('before',before),('after',after)]:
        docs=[];residues=[]
        for doc,ref in zip(run['documents'],gold['documents']):
            assert doc['file']==ref['file']
            actual={(s['page'],s['block_id']):s for s in doc['segments']}
            row=dict(file=doc['file'],source_pages=doc['source_pages'],output_pages=doc['output_pages'],segments=len(actual),
                canonical_total=0,canonical_translation_strict=0,canonical_published_strict=0,
                canonical_translation_concepts=0,canonical_published_concepts=0,
                protected_total=0,protected_preserved=0,OCR_noise_overlays=0,OCR_continuations=0,native_continuations=0,
                residue_A=0,residue_B=0,residue_C=0)
            for sample in ref['samples']:
                s=actual[(sample['page'],sample['block_id'])];visible=effective(s)
                translated=s['translated'] or s['text']
                for term in sample['critical_terms']:
                    expected=normalize(compact_label(term['expected']));row['canonical_total']+=1
                    row['canonical_translation_strict']+=expected in normalize(compact_label(translated))
                    row['canonical_published_strict']+=expected in normalize(compact_label(visible))
                    row['canonical_translation_concepts']+=concept_found(term,translated)
                    row['canonical_published_concepts']+=concept_found(term,visible)
                values=Counter(sample['protected_values']);row['protected_total']+=sum(values.values())
                row['protected_preserved']+=sum(min(n,visible.count(v)) for v,n in values.items())
                overlay=bool(s.get('visible_text') or s.get('overflow_text')) and translated!=s['text']
                row['OCR_noise_overlays']+=s['origin']=='ocr' and sample['ocr_kind']=='noise' and overlay
                if s.get('overflow_text'):row['OCR_continuations' if s['origin']=='ocr' else 'native_continuations']+=1
                cls=residue_class(s,sample['ocr_kind'])
                if cls:
                    row['residue_'+cls[0]]+=1
                    residues.append(dict(file=doc['file'],page=s['page']+1,source=s['text'],translation=translated,
                        visible=visible,class_=cls,preserve_reason=s.get('preserve_reason','')))
            docs.append(row)
        timing=json.loads((MEASUREMENTS_DIR/(run['run']+'.json')).read_text('utf-8'))
        save(mode+'_timings.json',timing)
        metrics[mode]=dict(run=run['run'],job_seconds=timing['elapsed'],wall_seconds=run['elapsed'],crc_ok=run['crc_ok'],
            source_immutable=run['source_hash_before']==run['source_hash_after'],documents=docs,
            totals={k:sum(d[k] for d in docs) for k in docs[0] if k!='file'},outputs=run['outputs'])
        save(mode+'_residue.json',residues)
    for case in gold['semantic_review_cases']:
        item=dict(source=case['source'],reference=case['expected'])
        for mode,run in [('before',before),('after',after)]:
            s=next(s for d in run['documents'] if d['file']==case['file'] for s in d['segments'] if s['text']==case['source'])
            item[mode]=s['translated'];item[mode+'_published']=effective(s)
        clean=re.sub(r'^\d+\.\s*','',item['after'])
        item['status']='PASS' if clean==item['reference'] else 'REVIEW_REQUIRED'
        reviews.append(item)
    save('quality_metrics.json',metrics);save('semantic_cases.json',reviews)
    print(json.dumps(metrics['after']['totals'],ensure_ascii=False),flush=True)
    print('JOB',metrics['before']['job_seconds'],'->',metrics['after']['job_seconds'],flush=True)

if __name__=='__main__':main()
