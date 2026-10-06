"""Developer-only metrics. Scores are supporting evidence, never a judge."""
import json
import re
import sys
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.documents.pdf_fidelity import faithful_result,FidelityMismatch

QA=ROOT/'qa/aw084'
MODELS=['m2m100-418m','m2m100-1.2b','madlad-3b']


def flags(source,text):
    def numbers(s):return [Decimal(x.replace(',','.')) for x in re.findall(r'\d+(?:[.,]\d+)?',s)]
    fidelity='pass'
    try:faithful_result(source,text)
    except FidelityMismatch as e:fidelity=str(e)
    return dict(number_fidelity=numbers(source)==numbers(text),protected_guard=fidelity,
                source_residue=bool(re.search('[\u4e00-\u9fff]',text)),empty=not text.strip(),
                length_ratio=len(text)/max(1,len(source)),replacement='\ufffd' in text or '⁇' in text,
                repeated=bool(re.search(r'(\b\w+\b)(?:\s+\1){3,}',text,re.I)),
                prompt_garbage=bool(re.search(r'<2[a-z]+>|<unk>|<pad>|</s>|__\w+__',text)))


def main():
    from sacrebleu.metrics import CHRF,BLEU
    gold=json.loads((QA/'semantic_gold.json').read_text('utf-8'))['entries'];out={};raw={}
    for model in MODELS:
        path=QA/f'{model}-cuda.json'
        if not path.exists():continue
        data=json.loads(path.read_text('utf-8'));rows=data['rows'];lookup={r['id']:r for r in rows};raw[model]=rows
        metrics={}
        for suite in ['body','independent','body_prose','body_labels']:
            cases=[c for c in gold if (c['suite']==suite or suite=='body_prose' and c['suite']=='body' and c['category']!='compound label'
                   or suite=='body_labels' and c['suite']=='body' and c['category']=='compound label')]
            hypotheses=[lookup[c['id']].get('text','') for c in cases];references=[[c['reference_ru'] for c in cases]]
            metrics[suite]={'cases':len(cases),'chrF':CHRF().corpus_score(hypotheses,references).score,
                'chrF++':CHRF(word_order=2).corpus_score(hypotheses,references).score,
                'BLEU':BLEU().corpus_score(hypotheses,references).score,
                'flags':[{'id':c['id'],**flags(c['source_zh'],text)} for c,text in zip(cases,hypotheses)]}
        production=QA/f'{model}-production.json'
        if production.exists():
            data=json.loads(production.read_text('utf-8'));protected=[];term_counts=[0,0];model_preserved=0
            body=json.loads((ROOT/'qa/aw083/body_dimensions_gold.json').read_text('utf-8'))
            samples={(d['file'],s['page'],s['block_id']):s for d in body['documents'] for s in d['samples']}
            for row in data['rows']:
                sample=samples[(row['file'],row['page'],row['block_id'])]
                for token in sample['protected_values']:
                    protected.append(token in row['text'])
                for term in sample['critical_terms']:
                    term_counts[1]+=1;term_counts[0]+=term['expected'].casefold() in row['text'].casefold()
                model_preserved+=row['reason'].startswith('guard:')
            metrics['production']={'segments':len(data['rows']),'protected_preserved':sum(protected),
                'protected_total':len(protected),'canonical_before_placement':term_counts,
                'guard_preserved_segments':model_preserved,
                'Chinese_residue_segments':sum(bool(re.search('[\u4e00-\u9fff]',r['text'])) for r in data['rows']),
                'seconds':data['seconds'],'placement':'not evaluated in suite B'}
        out[model]=metrics
    (QA/'automatic_metrics.json').write_text(json.dumps({'tool':'sacrebleu 2.5.1; QA-only','number_policy':'ordered decimal values; grouping/chronology changes count as failures',
        'metrics':out},ensure_ascii=False,indent=2)+'\n','utf-8')
    (QA/'raw_outputs.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({m:{s:{k:v for k,v in d.items() if k!='flags'} for s,d in suites.items()} for m,suites in out.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
