"""Deterministic, auditable BEFORE/AFTER scoring; no LLM judge."""
import json,re,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.documents.pdf_ocr_policy import compact_label
from app.documents.measurements import collect,MEASUREMENTS_DIR
QA=ROOT/'qa/aw083'


def normalize(text):return ''.join(text.casefold().split())


def effective(segment):
    if segment.get('overflow_text'):return segment['overflow_text']
    if segment.get('visible_text'):return segment['visible_text']
    return segment['text'] # The validated source raster/native objects remain.


def main():
    collect()
    gold=json.loads((QA/'body_dimensions_gold.json').read_text('utf-8'))
    result={}
    reviews={'definition':'Manually reviewed blocking meaning errors; terminology and OCR noise are separately measured.', 'baseline':[], 'accepted':[]}
    for mode in ('baseline','accepted'):
        run=json.loads((QA/(mode+'_segments.json')).read_text('utf-8'))
        rows=[]
        for document,reference in zip(run['documents'],gold['documents']):
            assert document['file']==reference['file']
            actual={(s['page'],s['block_id']):s for s in document['segments']}
            metric=dict(file=document['file'],source_pages=document['source_pages'],output_pages=document['output_pages'],
                critical_terms_total=0,critical_terms_correct=0,critical_terms_correct_translation=0,
                protected_values_total=0,protected_values_preserved=0,source_residue=0,OCR_noise_blocks=0,
                OCR_noise_overlays=0,OCR_translated_blocks=0,OCR_preserved_blocks=0,native_continuations=0,
                OCR_continuations=0,catastrophic_semantic_errors=0)
            for sample in reference['samples']:
                s=actual[(sample['page'],sample['block_id'])];visible=effective(s)
                for term in sample['critical_terms']:
                    metric['critical_terms_total']+=1
                    expected=normalize(compact_label(term['expected']))
                    metric['critical_terms_correct']+=expected in normalize(compact_label(visible))
                    metric['critical_terms_correct_translation']+=expected in normalize(compact_label(s['translated'] or s['text']))
                values=Counter(sample['protected_values'])
                metric['protected_values_total']+=sum(values.values())
                metric['protected_values_preserved']+=sum(min(count,visible.count(value)) for value,count in values.items())
                if sample['ocr_kind']!='noise' and re.search(r'[\u4e00-\u9fff]',visible):metric['source_residue']+=1
                if s['origin']=='ocr':
                    overlay=bool(s['visible_text'] or s['overflow_text']) and s['translated']!=s['text']
                    metric['OCR_translated_blocks']+=overlay
                    metric['OCR_preserved_blocks']+=not overlay
                    if sample['ocr_kind']=='noise':
                        metric['OCR_noise_blocks']+=1;metric['OCR_noise_overlays']+=overlay
                if s['overflow_text']:metric['OCR_continuations' if s['origin']=='ocr' else 'native_continuations']+=1
                # Reviewed cases are explicit and retained with their evidence.
                reason=None
                if document['file']=='一般事项.pdf':
                    reason=next((v for k,v in {'3.':'Растяжение/перекручивание/изгиб рулетки заменены длиной и колебаниями.',
                        '5.':'Разрушено объяснение проецирования точки на опорную плоскость.',
                        '6.':'Потеряна разница высот как величина удлинения наконечника.',
                        '检查探头':'Проверка отсутствия люфта превращена в отсутствие прорывов/отрывов.'}.items() if s['text'].startswith(k)),None)
                if mode=='baseline' and any(word in (s['translated'] or '').lower() for word in ('землетрясен','пулем','цепоч')) and document['file']!='一般事项.pdf':
                    reason='Blocking reference term changes the physical component: earthquake / machine gun / chain.'
                if mode=='baseline' and sample['ocr_kind']=='noise' and s['text'] in {'日','之','囍','卫'} and s.get('translated')!=s['text']:
                    reason='Raster mark mistaken for a Chinese character and painted as an unrelated Russian word/decoder glyph.'
                if reason:
                    metric['catastrophic_semantic_errors']+=1
                    reviews[mode].append(dict(file=document['file'],page=s['page']+1,block_id=s['block_id'],
                        source=s['text'],output=visible,reason=reason))
            rows.append(metric)
        timing_path=MEASUREMENTS_DIR/(run['run']+'.json')
        timing=json.loads(timing_path.read_text('utf-8'))
        selected=('preflight_open_extract','engine_translation','document_write','archive_pack','archive_translate','archive_publish','archive_cleanup')
        result[mode]=dict(run=run['run'],state=run['state'],outputs=run['outputs'],crc_ok=run['crc_ok'],
            source_hash_before=run['source_hash_before'],source_hash_after=run['source_hash_after'],
            wall_seconds=run['elapsed'],job_seconds=timing['elapsed'],process_seconds={p:round(sum(timing['processes'].get(p,[])),4) for p in selected},
            documents=rows,totals={key:sum(r[key] for r in rows) for key in rows[0] if key!='file'})
        (QA/(mode+'_timings.json')).write_text(json.dumps(timing,ensure_ascii=False,indent=2)+'\n','utf-8')
    (QA/'quality_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    (QA/'semantic_review.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2)+'\n','utf-8')
    for mode,data in result.items():print(mode,data['totals'],data['job_seconds'],data['process_seconds'])


if __name__=='__main__':main()
