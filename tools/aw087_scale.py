"""Actual indexed snapshot QA with synthetic rows outside production assets."""
from statistics import median
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw087_build import QA,PACK,save
from app.glossary.engine import GlossaryEngine
from app.knowledge.router import KnowledgeRouter

def run():
    results=[];scratch=[]
    folder=ROOT/'build/aw087-scale';folder.mkdir(exist_ok=True)
    for size in [1000,5000,10000,25000]:
        path=folder/f'scale-{size}.db';shutil.copy2(PACK,path)
        with sqlite3.connect(path) as con:
            fields=[r[1] for r in con.execute('PRAGMA table_info(entries)')]
            sample=list(con.execute('SELECT * FROM entries LIMIT 1').fetchone());max_id=con.execute('SELECT MAX(id) FROM entries').fetchone()[0]
            count=con.execute('SELECT COUNT(*) FROM entries').fetchone()[0];data=[];index=[]
            for n in range(size-count):
                values=list(sample);uid=max_id+n+1
                for name,value in [('id',uid),('source_term',f'SYNTHETIC_{n}'),('source_normalized',f'SYNTHETIC_{n}'),
                    ('target_term',f'synthetic {n}'),('notes',json.dumps(dict(type='term',concept_id=f'scale:{n}',subdomains=['inactive-scale'],segment_types=[])))]:values[fields.index(name)]=value
                data.append(values);index.append((uid,'zh','ru','automotive','inactive-scale','TERM',f'scale:{n}',100))
            con.executemany(f'INSERT INTO entries VALUES({",".join("?" for f in fields)})',data)
            con.executemany('INSERT INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',index)
            plan=con.execute("EXPLAIN QUERY PLAN SELECT entry_id FROM knowledge_context_index WHERE source_language='zh' AND target_language='ru' AND domain='automotive' AND subdomain='cooling'").fetchall()
            assert con.execute('SELECT COUNT(*) FROM entries').fetchone()[0]==size
            con.commit();con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        con.close()
        engine=GlossaryEngine(folder/f'user-{size}.db',builtin_paths=[path]);router=KnowledgeRouter(engine)
        profile=router.profile('zh','ru',segments=['冷却液 散热器 冷却风扇']);times=[]
        for trial in range(7):
            router.cache.clear();started=perf_counter();snapshot=router.snapshot(profile);times.append(perf_counter()-started)
        started=perf_counter()
        for n in range(200):snapshot.candidates('散热器盖','automotive','',set())
        lookup=(perf_counter()-started)/200
        results.append(dict(total_entries=size,active_snapshot_entries=len(snapshot.entries),snapshot_median_seconds=median(times),
            snapshot_trials=times,candidate_lookup_seconds=lookup,query_plan=plan,db_bytes=path.stat().st_size,
            no_full_scan=all('SCAN knowledge_context_index' not in row[3] for row in plan)))
        scratch.extend(p for p in [path,folder/f'user-{size}.db'] if p.exists())
    save('scale_benchmark.json',dict(rows=results,scope='Synthetic inactive metadata; actual production snapshot SQL and candidates. Not NMT or all-relevant stress accuracy.',
        ratios=dict(snapshot_25k_vs_1k=results[-1]['snapshot_median_seconds']/results[0]['snapshot_median_seconds'],
            lookup_25k_vs_1k=results[-1]['candidate_lookup_seconds']/results[0]['candidate_lookup_seconds'])))
    save('cleanup_inventory.json',[dict(path=str(p.resolve()),size=p.stat().st_size,reason='Synthetic scale scratch; results and query plans retained',owner_cycle='AW0.8.7',deleted=False) for p in scratch])
    print(json.dumps(results),flush=True)

if __name__=='__main__':run()
