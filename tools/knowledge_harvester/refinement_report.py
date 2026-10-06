"""Build-only prioritized review, conflict taxonomy and corpus comparisons."""
from collections import Counter, defaultdict
import heapq
import json
from pathlib import Path
import sqlite3
from time import perf_counter
from .normalization import normalize, variants
from .provenance import canonical_json
from .licenses import approved

PRIORITY_TERMS=('冷却液','冷却剂','散热器','散热器盖','连接器','接头','怠速')
PRIORITY_DOMAINS={'automotive':1,'metallurgy':2,'mechanical-engineering':3,'electronics':4,'electrical':4}


def conflict_category(left,right):
    if left['domain']!=right['domain']:return 'domain_separation'
    if normalize(left['ru']).casefold()==normalize(right['ru']).casefold():
        return 'duplicate_provenance' if left['ru']==right['ru'] else 'case_normalization_collision'
    if normalize(left['zh'])!=normalize(right['zh']):return 'alias_collision'
    return 'semantic_ambiguity_requires_review'


def priority(candidate,frequency):
    terms={candidate['zh'],*candidate['zh_variants']}
    automotive=any(term in terms for term in PRIORITY_TERMS)
    evidence=candidate.get('link_evidence',{})
    return (0 if automotive else PRIORITY_DOMAINS.get(candidate['domain'],5),
            -frequency.get(candidate['zh'],0),-bool(evidence.get('independent_agreement')),
            -int(evidence.get('quality_tier')=='REVIEW_HIGH'),-candidate['score'],candidate['id'])


def write_refinement_report(store,baseline,destination,*,limit=1000):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    old=sqlite3.connect(Path(baseline).resolve().as_uri()+'?mode=ro',uri=True)
    old_status=dict(old.execute('SELECT id,status FROM candidates'))
    old_counts=dict(old.execute('SELECT status,count(*) FROM candidates GROUP BY status'))
    old_unique=old.execute("SELECT count(*) FROM (SELECT DISTINCT zh,ru FROM candidates WHERE status='VERIFIED')").fetchone()[0]
    old.close()
    with store.connect() as con:
        sources={r['id']:json.loads(r['metadata']) for r in con.execute('SELECT * FROM sources')}
        frequency=Counter();term_sources=defaultdict(list)
        for (payload,) in con.execute('SELECT payload FROM raw_records'):
            r=json.loads(payload)
            for term in set(variants(r,'zh')):frequency[term]+=1
            for term in PRIORITY_TERMS:
                if term in variants(r,'zh') or term in payload:
                    term_sources[term].append(dict(source=r['source'],record=r['source_record_id'],labels=r['labels'],aliases=r['aliases'],
                        definitions=r['definitions'],declared_zh=term in variants(r,'zh'),input_sha256=r['input_hash']))
        transitions=Counter();tiers=Counter();links=Counter();heap=[];promoted=[];by_term=defaultdict(list)
        # Pair agreement is explicit evidence for review, not a canonical merge.
        agreement={}
        for row in con.execute("SELECT zh,ru,group_concat(id) AS ids FROM candidates WHERE link_type='DIRECT_CONCEPT' AND zh!='' AND ru!='' GROUP BY zh,ru HAVING count(*)>1"):
            members=[json.loads(con.execute('SELECT payload FROM candidates WHERE id=?',(uid,)).fetchone()[0]) for uid in row['ids'].split(',')]
            groups={sources[p['source']]['independence_group'] for c in members for p in c['provenance'] if approved(sources[p['source']])}
            if len(groups)>1:agreement[(row['zh'],row['ru'])]=dict(independence_groups=sorted(groups),candidate_ids=[c['id'] for c in members])
        for (payload,) in con.execute('SELECT payload FROM candidates ORDER BY id'):
            c=json.loads(payload);before=old_status.get(c['id'],'NEW');transitions[before+'->'+c['status']]+=1
            links[c['link_type']+':'+c['status']]+=1
            default_tier=('VERIFIED_CROSS_SOURCE' if c['link_type']=='CROSS_SOURCE_CONCEPT' else 'VERIFIED_DIRECT') if c['status']=='VERIFIED' else c['status']
            tier=c.get('link_evidence',{}).get('quality_tier','REVIEW') if c['status']=='REVIEW' else default_tier
            tiers[tier]+=1
            if c['status']=='VERIFIED' and before not in ('VERIFIED','NEW'):
                promoted.append(dict(id=c['id'],zh=c['zh'],ru=c['ru'],domain=c['domain'],before=before,after=c['status'],reasons=c['reasons'],evidence=c['domains_evidence']))
            for term in PRIORITY_TERMS:
                if term in {c['zh'],*c['zh_variants']}:
                    by_term[term].append(dict(id=c['id'],zh=c['zh'],ru=c['ru'],domain=c['domain'],status=c['status'],reasons=c['reasons'],link_type=c['link_type']))
            if c['status'] not in ('REVIEW','AUTO'):continue
            if (c['zh'],c['ru']) in agreement:
                c.setdefault('link_evidence',{})['independent_agreement']=agreement[(c['zh'],c['ru'])]
            key=priority(c,frequency)
            # Keep bounded top-N; reversed comparable numeric/text-independent key.
            rank=(-key[0],-key[1],-key[2],-key[3],-key[4],c['id'])
            item=(rank,c['id'],c)
            if len(heap)<limit:heapq.heappush(heap,item)
            elif rank>heap[0][0]:heapq.heapreplace(heap,item)
        conflict_started=perf_counter();counts=Counter();examples=defaultdict(list)
        for row in con.execute('SELECT a.payload,b.payload,f.reason FROM conflicts f JOIN candidates a ON a.id=f.candidate JOIN candidates b ON b.id=f.other WHERE f.candidate<f.other'):
            left,right=map(json.loads,row[:2]);kind=row[2] if row[2]=='retrieval_only_challenge' else conflict_category(left,right);counts[kind]+=1
            if len(examples[kind])<20:examples[kind].append(dict(left=left['id'],right=right['id'],zh=left['zh'],ru=[left['ru'],right['ru']],domain=left['domain']))
        counts['duplicate_provenance_pairs']=con.execute("SELECT count(*) FROM (SELECT zh,ru,domain FROM candidates WHERE zh!='' AND ru!='' GROUP BY zh,ru,domain HAVING count(*)>1)").fetchone()[0]
        counts['domain_separation_keys']=con.execute("SELECT count(*) FROM (SELECT zh FROM candidates WHERE zh!='' AND ru!='' GROUP BY zh HAVING count(DISTINCT domain)>1 AND count(DISTINCT ru)>1)").fetchone()[0]
        reverse=defaultdict(set)
        for row in con.execute("SELECT ru,domain,zh FROM candidates WHERE status='VERIFIED'"):
            reverse[(normalize(row['ru']).casefold(),row['domain'])].add(row['zh'])
        counts['reverse_only_collision_keys']=sum(len(v)>1 for v in reverse.values())
        conflict_seconds=perf_counter()-conflict_started
        with (destination/'high-value-review.jsonl').open('w',encoding='utf-8') as stream:
            for _,_,c in sorted(heap,key=lambda item:priority(item[2],frequency)):
                source_terms={normalize(v) for v in [c['zh'],*c['zh_variants']]}
                aliases={k:sorted({p['labels'][k] for p in c['provenance'] if k in p['labels'] and normalize(p['labels'][k]) in source_terms}) for k in ('zh-hans','zh-hant','zh-cn','zh-tw')}
                alternatives=[dict(r) for r in con.execute("SELECT DISTINCT ru,status,link_type FROM candidates WHERE zh=? AND domain=? AND ru!='' ORDER BY ru,status,link_type",(normalize(c['zh']),c['domain']))]
                conflicts=[dict(r) for r in con.execute('SELECT other,reason FROM conflicts WHERE candidate=? ORDER BY other',(c['id'],))]
                row=dict(candidate_id=c['id'],zh=c['zh'],traditional_simplified=aliases,source_declared_variants=c['zh_variants'],
                    ru_candidates=alternatives,en_meanings=c['en'],domain=c['domain'],sources=sorted({p['source'] for p in c['provenance']}),
                    link_evidence=c.get('link_evidence',{}),domain_evidence=c['domains_evidence'],score=c['score'],status=c['status'],
                    conflicts=conflicts,reason_for_review=c['reasons'],source_occurrences=frequency[c['zh']],
                    frequency_note='Source record occurrences, not usage frequency.',provenance=c['provenance'])
                stream.write(canonical_json(row)+'\n')
        summary=dict(before=old_counts,after=dict(con.execute('SELECT status,count(*) FROM candidates GROUP BY status')),
            unique_verified_before=old_unique,unique_verified_after=con.execute("SELECT count(*) FROM (SELECT DISTINCT zh,ru FROM candidates WHERE status='VERIFIED')").fetchone()[0],
            transitions=dict(transitions),promoted=len(promoted),promoted_examples=promoted[:100],tiers=dict(tiers),links=dict(links),
            independent_pair_agreements=len(agreement),independent_agreement_examples=[dict(zh=k[0],ru=k[1],**v) for k,v in list(agreement.items())[:50]],
            conflict_categories=dict(counts),conflict_examples=dict(examples),conflict_classification_seconds=conflict_seconds,
            removed_candidates=len(old_status)-sum(n for transition,n in transitions.items() if not transition.startswith('NEW->')),
            high_value_rows=len(heap),human_verified=0)
        (destination/'refinement-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
        (destination/'automotive-gaps.json').write_text(json.dumps({t:dict(source_records=term_sources[t],candidates=by_term[t]) for t in PRIORITY_TERMS},ensure_ascii=False,indent=2)+'\n','utf-8')
        return summary
