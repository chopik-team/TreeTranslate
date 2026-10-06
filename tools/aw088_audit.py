from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random
import sqlite3
import sys
from tempfile import TemporaryDirectory
from statistics import median
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw088_prepare import QA,save
from tools.aw087_build import PACK,stats
from tools.knowledge_harvester.storage import Store
from tools.knowledge_harvester.corpus import review
from tools.knowledge_harvester.provenance import digest_json
from app.glossary.database import Database
from app.glossary.repository import Repository
from app.glossary.engine import GlossaryEngine
from app.knowledge.router import KnowledgeRouter


def audit():
    reviews=json.loads((QA/'candidate_review.json').read_text('utf8'))
    valid={r['candidate_id'] for r in reviews};store=Store(QA/'reviewed_harvester_v3.db')
    with store.connect() as con:
        stale=[json.loads(r[0]) for r in con.execute("SELECT payload FROM candidates WHERE status='VERIFIED'") if json.loads(r[0])['id'] not in valid]
    for payload in stale:
        review(store,payload['id'],'DEPRECATED',reviewer='Codex',reason='Pre-holdout development review rejected abstract-parent composition or verb/position collision.',evidence_sha256=digest_json(payload['provenance']))
    groups=defaultdict(list)
    for r in reviews:
        if r['new']:groups[r['subdomains'][0]].append(r)
    samples=[]
    for branch,rows in sorted(groups.items()):
        samples.extend(random.Random('aw088-final-review:'+branch).sample(rows,min(25,len(rows))))
    save('knowledge_hit_review.json',dict(reviewer='Codex; not human-certified',sampling='Deterministic stratified random 25 new verified surfaces per subdomain or all if fewer',
        pre_final_holdout=True,rows=samples,review_status='PENDING_EXPLICIT_REVIEW',deprecated_previous_proposals=len(stale)))
    counts=stats();save('knowledge_after.json',counts);save('knowledge_by_type.json',counts['types']);save('knowledge_by_domain.json',counts['subdomains'])
    inventory=json.loads((QA/'candidate_inventory.json').read_text('utf8'))
    save('candidate_frequency.json',dict(documents=inventory['documents'],raw_candidates=len(inventory['candidates']),
        types=dict(Counter(r['type'] for r in inventory['candidates'])),frequency_source='candidate_inventory.json',
        fields=['document_frequency','total_frequency','subdomain_frequency','segment_types','contexts','samples','priority_factors'],
        holdout_excluded=True,automatic_verified=0))
    families=json.loads((QA/'concepts.json').read_text('utf8'))
    save('aliases.json',[dict(concept_id=r['concept_id'],source=r['source'],aliases=r['aliases']) for r in families if r['aliases']])
    save('development_revision_review.json',dict(before_final_holdout=True,reviewer='Codex',
        removed_generated_errors=['verb-position collision: 下 in 拆下 is not lower','abstract parent: 损坏线束 is not wiring harness of damage','enumeration: 螺母螺栓 is not bolt of a nut'],
        corrected_full_phrase_cases=['后车门装饰板: облицовка задней двери','前座椅安全带拉紧器: преднатяжитель ремня безопасности переднего сиденья'],
        deprecated_previous_proposals=len(stale),old_review_store_retained=True))
    print('Review sample',len(samples),'domains',len(groups),'entries',counts['entries'],flush=True)


def snapshots():
    glossary=GlossaryEngine(QA/'snapshot-isolated-user.db',builtin_paths=[PACK]);router=KnowledgeRouter(glossary)
    manifest=json.loads((QA/'development_manifest.json').read_text('utf8'));selected=[]
    for branch in sorted({d['stratum'] for d in manifest['documents']}):
        docs=[d for d in manifest['documents'] if d['stratum']==branch]
        selected.extend(sorted(docs,key=lambda d:sha256(d['member'].encode()).hexdigest())[:25])
    mapping={d['member']:d for d in selected};rows=[];start=perf_counter()
    with sqlite3.connect(QA/'native_corpus.db') as con:
        for member,_,_,raw in con.execute('SELECT * FROM documents'):
            if member not in mapping:continue
            d=json.loads(raw);t=perf_counter();p=router.profile('zh','ru',segments=d.get('lines',[]),filename=member,folders=(member,))
            snapshot=router.snapshot(p)
            rows.append(dict(member=member,domain=p.primary_domain,subdomains=list(dict(p.subdomains)),
                entries=len(snapshot.entries),bytes=snapshot.bytes_estimate,seconds=perf_counter()-t))
    body=router.profile('zh','ru',segments=['车身维修 车门 钣金 车身尺寸']);s=router.snapshot(body)
    forbidden=set()
    for r in s.entries:
        scopes=json.loads(r.notes or '{}').get('subdomains',[])
        if any(b in scopes for b in ['engine','hvac','brakes']) and not any(b=='body' or b.startswith('body.') for b in scopes):forbidden.add(r.source_term)
    save('snapshot_metrics.json',dict(documents=len(rows),average_entries=sum(r['entries'] for r in rows)/len(rows),
        max_entries=max(r['entries'] for r in rows),average_bytes=sum(r['bytes'] for r in rows)/len(rows),max_bytes=max(r['bytes'] for r in rows),
        seconds=perf_counter()-start,body_entries=len(s.entries),body_forbidden_specific_terms=sorted(forbidden),
        metrics=dict(router.metrics),rows=rows))
    assert not forbidden
    print('Snapshots',len(rows),'body',len(s.entries),'max',max(r['entries'] for r in rows),flush=True)


def scale():
    import shutil
    results=[]
    with TemporaryDirectory(prefix='TreeTranslate-aw088-scale-') as temporary:
        folder=Path(temporary)
        for size in [stats()['entries'],5000,10000,25000]:
            path=folder/f'scale-{size}.db';shutil.copy2(PACK,path)
            with sqlite3.connect(path) as con:
                fields=[r[1] for r in con.execute('PRAGMA table_info(entries)')]
                sample=list(con.execute('SELECT * FROM entries LIMIT 1').fetchone());maximum=con.execute('SELECT MAX(id) FROM entries').fetchone()[0]
                count=con.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
                for n in range(size-count):
                    values=list(sample);uid=maximum+n+1
                    for name,value in [('id',uid),('source_term',f'SYNTHETIC_{n}'),('source_normalized',f'SYNTHETIC_{n}'),('target_term',f'synthetic {n}'),
                        ('notes',json.dumps(dict(type='term',concept_id=f'scale:{n}',subdomains=['inactive-scale'],segment_types=[])))]:values[fields.index(name)]=value
                    con.execute(f'INSERT INTO entries VALUES({",".join("?" for _ in fields)})',values)
                    con.execute('INSERT INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',(uid,'zh','ru','automotive','inactive-scale','TERM',f'scale:{n}',100))
                plan=con.execute("EXPLAIN QUERY PLAN SELECT entry_id FROM knowledge_context_index WHERE source_language='zh' AND target_language='ru' AND domain='automotive' AND subdomain='cooling'").fetchall()
                con.commit()
            con.close()
            router=KnowledgeRouter(GlossaryEngine(folder/f'user-{size}.db',builtin_paths=[path]));p=router.profile('zh','ru',segments=['冷却液 散热器 冷却风扇']);times=[]
            for _ in range(7):
                router.cache.clear();t=perf_counter();s=router.snapshot(p);times.append(perf_counter()-t)
            t=perf_counter()
            for _ in range(200):s.candidates('散热器盖','automotive','',set())
            lookup=(perf_counter()-t)/200
            results.append(dict(total_entries=size,active_entries=len(s.entries),snapshot_median_seconds=median(times),snapshot_trials=times,
                candidate_lookup_seconds=lookup,query_plan=plan,no_full_scan=not any('SCAN knowledge_context_index' in r[3] for r in plan)))
    save('scale_benchmark.json',dict(rows=results,temporary_cleanup=True,scope='Actual production snapshot SQL; synthetic inactive rows; no NMT throughput claim'))
    print('Scale',[(r['total_entries'],r['active_entries'],round(r['snapshot_median_seconds'],5)) for r in results],flush=True)

if __name__=='__main__':
    {'audit':audit,'snapshots':snapshots,'scale':scale}[sys.argv[1]]()
