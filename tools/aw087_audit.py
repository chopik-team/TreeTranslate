"""Reviewable historical fallback inventory, coverage separated from quality."""
from collections import Counter
import json
import re
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw087_build import QA,save

def audit():
    before=json.loads((QA/'baseline/coolant_e2e.json').read_text('utf-8'))
    after=json.loads((QA/'coolant_e2e.json').read_text('utf-8'))
    # New warning-region typing explains two idle differences in reconstruction.
    # Retain the 39 raw rows, never present these as original runtime logs.
    raw=[r for r in before['routes'] if r['knowledge_source']=='model']
    historical=[r for r in raw if r['source']!='保持发动机空转。']
    rows=[]
    for i,row in enumerate(historical):
        new=next((r for r in after['routes'] if r['source']==row['source']),None)
        source=row['source'];long=len(source)>35
        rows.append(dict(id=i,source=source,segment_type=row['segment_type'],context=row['context'],
            why_missed='No safe complete structure; partial terminology may still guide NMT',
            required_concepts=re.findall(r'冷却液|散热器|发动机|连接器|电源|GDS|VIN|GPF|CKPS|ITM',source),
            possible_reusable_pattern='Technical label or bounded action/condition' if not long else 'Bounded condition/action if reviewable; otherwise prose',
            model_truly_needed=bool(new and new['backend'] not in ['knowledge_template','glossary','translation_memory']),
            before=row['output'],after=new['output'] if new else None,after_route=new['knowledge_source'] if new else 'direct_lookup_or_preserved',
            reconstructed=True))
    save('coolant_fallback_audit.json',dict(historical_counter=37,reconstructed_model_counter=len(raw),
        reconstructed_historical_rows=len(historical),explanation='AW086 artifacts contain aggregate counters, not source-level route logs. Reconstruction with 301 original rows differs by two idle occurrences after warning typing; all 39 raw records retained.',
        raw_reconstructed=raw,rows=rows))
    inventory=[]
    for i,s in enumerate(after['documents'][0]['segments']):
        route=next((r for r in after['routes'] if r['source']==re.sub(r'^\s*(?:\d+[.)、]\s*|[•●▪]\s*)','',s['text'])),None)
        needs_model=bool(route and route['backend'] not in ['knowledge_template','glossary','translation_memory'])
        category='UNKNOWN_CONCEPT' if needs_model and route['knowledge_source']=='model' and len(s['text'])<30 else 'MODEL_REQUIRED' if needs_model else 'TEMPLATE_KNOWN' if route and route['knowledge_source']=='template' else 'EXACT_KNOWN' if route and route['constraint_status']=='full_segment' else 'DIRECT_KNOWN' if s['translated'] and s['translated']!=s['text'] else 'PROTECTED_OR_PRESERVED'
        inventory.append(dict(index=i,source=s['text'],output=s['translated'],category=category,requires_model=needs_model,route=route and route['knowledge_source']))
    save('coolant_before_after.json',dict(before_original=dict(model_fallbacks=37,wall_seconds=67.8156631,pages=5),
        reconstruction=dict(model_fallbacks=len(raw),model_router_calls=len(before['model_calls']),wall_seconds=before['elapsed']),
        after=dict(model_fallbacks=after['context']['metrics'].get('model_fallbacks',0),model_router_calls=len(after['model_calls']),
            template_hits=after['context']['metrics'].get('template_hits',0),wall_seconds=after['elapsed'],
            pages=sum(d['output_pages'] for d in after['documents']),source_immutable=after['source_hash_before']==after['source_hash_after']),
        segments=inventory,coverage_categories=dict(Counter(r['category'] for r in inventory))))
    save('template_metrics.json',after['context']['metrics'])
    print('Fallback audit',len(rows),'original-counter aligned rows; raw reconstruction',len(raw))

if __name__=='__main__':audit()
