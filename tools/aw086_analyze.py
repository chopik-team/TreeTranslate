"""Evaluate immutable AW083 gold and AW085 references; never rewrite sources."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw086'
from tools.aw085_metrics import concept_found,residue_class
from tools.qa_aw083_metrics import normalize,effective
from app.documents.measurements import collect
from app.documents.pdf_ocr_policy import compact_label


def read(path):return json.loads((ROOT/path).read_text('utf-8'))
def save(name,value):(QA/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')


def body():
    run=read('qa/aw086/body_e2e.json');gold=read('qa/aw083/body_dimensions_gold.json');totals=Counter();rows=[]
    for doc,reference in zip(run['documents'],gold['documents']):
        assert doc['file']==reference['file']
        actual={(s['page'],s['block_id']):s for s in doc['segments']}
        counts=Counter(source_pages=doc['source_pages'],output_pages=doc['output_pages'],segments=len(actual))
        for sample in reference['samples']:
            s=actual[(sample['page'],sample['block_id'])];visible=effective(s);translated=s['translated'] or s['text']
            for term in sample['critical_terms']:
                expected=normalize(compact_label(term['expected']));counts['canonical_total']+=1
                counts['canonical_translation_concepts']+=concept_found(term,translated)
                counts['canonical_published_concepts']+=concept_found(term,visible)
                counts['canonical_translation_strict']+=expected in normalize(compact_label(translated))
                counts['canonical_published_strict']+=expected in normalize(compact_label(visible))
            values=Counter(sample['protected_values']);counts['protected_total']+=sum(values.values())
            counts['protected_preserved']+=sum(min(n,visible.count(v)) for v,n in values.items())
            overlay=bool(s.get('visible_text') or s.get('overflow_text')) and translated!=s['text']
            counts['OCR_noise_overlays']+=s['origin']=='ocr' and sample['ocr_kind']=='noise' and overlay
            counts['OCR_continuations']+=s['origin']=='ocr' and bool(s.get('overflow_text'))
            cls=residue_class(s,sample['ocr_kind'])
            if cls:counts['residue_'+cls[0]]+=1
        rows.append(dict(file=doc['file'],metrics=dict(counts)));totals.update(counts)
    stable=[]
    for case in gold['semantic_review_cases']:
        s=next(s for d in run['documents'] if d['file']==case['file'] for s in d['segments'] if s['text']==case['source'])
        translated=s['translated'];clean=re.sub(r'^\d+\.\s*','',translated)
        stable.append(dict(source=case['source'],reference=case['expected'],output=translated,
                           status='PASS' if clean==case['expected'] else 'REVIEW_REQUIRED'))
    baseline=read('qa/aw085/quality_metrics.json')['after']
    result=dict(before=baseline['totals'],after=dict(totals),stable_instructions=stable,documents=rows,
                wall_seconds=run['elapsed'],baseline_job_seconds=64.27,baseline_wall_seconds=baseline['wall_seconds'],
                overhead_vs_job_percent=100*(run['elapsed']/64.27-1),crc_ok=run['crc_ok'],source_immutable=run['source_hash_before']==run['source_hash_after'])
    save('body_quality.json',result);print('BODY',dict(totals),flush=True)


def contextual():
    profiles=[];snapshots=[];decisions=[];metrics={};types={};timings={}
    collected=collect()
    for name in ('body','coolant','general','mixed'):
        run=read('qa/aw086/'+name+'_e2e.json');context=run['context'];metrics[name]=context
        profiles.extend(dict(p,corpus=name) for p in context['profiles'])
        snapshots.extend(dict(s,corpus=name) for s in context['snapshots'])
        decisions.extend(dict(d,corpus=name) for d in context['decisions'])
        counts=context['metrics'];types[name]={k.removeprefix('segment_'):v for k,v in counts.items() if k.startswith('segment_') and not k.endswith('_time')}
        processes=collected.get(run['run'],{}).get('processes',{})
        measured={k:v for k,v in counts.items() if k.endswith('_time') or k=='knowledge_lookup_total'}
        measured['routing_total']=sum(measured.get(k,0) for k in ('archive_profile_time','folder_profile_time','document_profile_time','snapshot_build_time','segment_classification_time','knowledge_lookup_total'))
        measured['routing_total']+=measured.get('archive_sample_time',0)
        timings[name]=dict(wall_seconds=run['elapsed'],routing=measured,processes=processes,
            caches_released=context['profile_cache_size']==context['snapshot_cache_size']==0,
            snapshot_peak_bound_entries=2048,snapshot_cache_bound=12,
            cached_snapshot_bytes_estimate=sum(s['bytes_estimate'] for s in context['snapshots']))
    for filename,value in [('document_profiles.json',profiles),('knowledge_snapshots.json',snapshots),('routing_decisions.json',decisions),
        ('knowledge_hit_metrics.json',metrics),('segment_classification.json',types),('timings.json',timings)]:save(filename,value)
    save('taxonomy.json',read('assets/config/knowledge-taxonomy.json'))


def coolant():
    run=read('qa/aw086/coolant_e2e.json');reference=read('tests/fixtures/pdf/semantic-corpus.json')
    texts=[s for d in run['documents'] for s in d['segments']];joined='\n'.join(s['translated'] or s['text'] for s in texts)
    checks=[]
    for source,target in [('冷却液','охлаждающ'),('散热器盖','крышк'),('排放螺塞','сливн'),('冷却风扇总成','узел вентилятора'),('防锈剂','антикоррозион'),('空转','холостом ходу'),('连接器','разъём')]:
        candidates=[s for s in texts if source in s['text']]
        checks.append(dict(source=source,expected_concept=target,occurrences=len(candidates),
            matched=sum(target in (s['translated'] or '').casefold() for s in candidates),
            published_matched=sum(target in effective(s).casefold() for s in candidates),
            outputs=[s['translated'] for s in candidates]))
    forbidden=['холодильная жидкость','нагревательного покрытия','обезболивающие продукты']
    save('coolant_quality.json',dict(checks=checks,forbidden_errors={s:s in joined.casefold() for s in forbidden},
        pages=[dict(source=d['source_pages'],output=d['output_pages']) for d in run['documents']],
        warning_review=[dict(source=s['text'],output=s['translated']) for s in texts if '绝不能' in s['text']],
        reference_source_sha256=sha256((ROOT/'tests/fixtures/pdf/semantic-corpus.json').read_bytes()).hexdigest(),
        scope='Term/negation and strict writer checks; remaining sentences require semantic review',outputs=run['outputs']))
    print('COOLANT',[(c['source'],c['matched'],c['occurrences']) for c in checks],flush=True)


def holdout():
    result=read('qa/aw086/holdout_regression.json');review=read('qa/aw085/holdout_semantic_review.json')['rows']
    counts=Counter();changes=[]
    for row,old in zip(result['rows'],review):
        if row['same_as_aw085']:grade=old['after_status'];reason='Output unchanged from frozen AW085 reviewed result'
        elif row['id']=='prose-01' and 'не деформированы' in row['after']:grade='PASS';reason='Deformation condition and both panel concepts preserved'
        elif row['exact']:grade='PASS';reason='Exact frozen reference'
        elif row['id']=='prose-03':grade='MAJOR';reason='Crack concept restored but whether-condition remains grammatically ambiguous; conservative major grade retained'
        elif row['id']=='prose-10':grade='MINOR';reason='No-crack condition and mounting-hole entity preserved; incorrect Russian noun case'
        else:grade='REVIEW_REQUIRED';reason='Changed output requires explicit semantic review'
        row.update(after_status=grade,before_status=old['after_status'],review_reason=reason)
        counts[grade]+=1
        if not row['same_as_aw085']:changes.append(row)
    result.update(after_summary=dict(counts),changed_outputs=changes,reviewer='Codex; not independent human certification')
    save('holdout_regression.json',result);print('HOLDOUT',dict(counts),flush=True)


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='body':body()
    elif mode=='holdout':holdout()
    elif mode=='coolant':coolant()
    elif mode=='context':contextual()
