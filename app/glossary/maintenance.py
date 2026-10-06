from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
from .database import Database


def all_stores(engine):
    with engine.db.connect() as con:
        packs=[dict(r) for r in con.execute('SELECT pack_id,version,enabled,path FROM packs')]
    stores=[('user',engine.db)]+[(f'builtin:{i}',db) for i,db in enumerate(engine.builtins)]
    stores.extend((p['pack_id'],Database(p['path'],readonly=True)) for p in packs)
    return stores,packs


def integrity(db):
    with db.connect() as con:return [r[0] for r in con.execute('PRAGMA integrity_check')]


def duplicates(db):
    with db.connect() as con:
        return [dict(r) for r in con.execute('''SELECT source_language,target_language,domain,source_normalized,target_term,count(*) AS count
          FROM entries GROUP BY source_language,target_language,domain,source_normalized,target_term HAVING count(*)>1''')]


def conflicts(db):
    with db.connect() as con:
        return [dict(r) for r in con.execute('''SELECT source_language,target_language,domain,source_normalized,count(DISTINCT target_term) AS targets
          FROM entries WHERE status NOT IN ('DISABLED','REJECTED') GROUP BY source_language,target_language,domain,source_normalized
          HAVING count(DISTINCT target_term)>1''')]


def variant_overlaps(db):
    with db.connect() as con:
        return [dict(r) for r in con.execute('''SELECT pair,domain,term,count(DISTINCT entry_id) AS entries
          FROM aliases GROUP BY pair,domain,term HAVING count(DISTINCT entry_id)>1''')]


def stats(engine):
    counts={};pairs=set();domains=set()
    stores,packs=all_stores(engine)
    for name,db in stores:
        with db.connect() as con:
            counts[name]=con.execute('SELECT count(*) FROM entries').fetchone()[0]
            pairs.update(tuple(r) for r in con.execute('SELECT DISTINCT source_language,target_language FROM entries'))
            domains.update(r[0] for r in con.execute('SELECT DISTINCT domain FROM entries'))
    return dict(entries_total=sum(counts.values()),user_entries=counts.get('user',0),
        builtin_entries=sum(v for k,v in counts.items() if k!='user'),language_pairs=sorted(pairs),domains=sorted(domains),
        enabled_packs=[{k:p[k] for k in ('pack_id','version','enabled')} for p in packs if p['enabled']],counters=dict(engine.counters),conflicts=len(conflicts(engine.db)),conflict_scope='user',
        cache_entries=len(engine.cache),compiled_indexes=len(engine.indexes))


def knowledge_conflicts(engine,limit=1000):
    """Explicit disk-backed audit across stores, including disabled installed packs."""
    stores,_=all_stores(engine)
    with tempfile.TemporaryDirectory(prefix='glossary-audit-') as folder:
        with closing(sqlite3.connect(Path(folder)/'audit.db')) as audit:
            audit.row_factory=sqlite3.Row
            audit.execute('CREATE TABLE terms(pair TEXT,domain TEXT,source TEXT,target TEXT,store TEXT)')
            audit.execute('CREATE TABLE variants(pair TEXT,domain TEXT,term TEXT,store TEXT,entry_id INTEGER)')
            for name,db in stores:
                with db.connect() as con:
                    audit.executemany('INSERT INTO terms VALUES(?,?,?,?,?)',
                        ((r[0]+'>'+r[1],r[2],r[3],r[4],name) for r in con.execute("SELECT source_language,target_language,domain,source_normalized,target_term FROM entries WHERE status NOT IN ('REJECTED','DISABLED')")))
                    audit.executemany('INSERT INTO variants VALUES(?,?,?,?,?)',
                        ((r[0],r[1],r[2],name,r[3]) for r in con.execute('SELECT pair,domain,term,entry_id FROM aliases')))
            audit.commit()
            queries={
                'conflicts':'SELECT pair,domain,source,count(DISTINCT target) AS targets FROM terms GROUP BY pair,domain,source HAVING count(DISTINCT target)>1',
                'duplicates':'SELECT pair,domain,source,target,count(*) AS count FROM terms GROUP BY pair,domain,source,target HAVING count(*)>1',
                'variant_overlaps':'SELECT pair,domain,term,count(*) AS count FROM variants GROUP BY pair,domain,term HAVING count(*)>1'}
            result={'scope':'all_registered_stores','limit':limit}
            for name,query in queries.items():
                result[name+'_total']=audit.execute('SELECT count(*) FROM ('+query+')').fetchone()[0]
                result[name]=[dict(r) for r in audit.execute(query+' LIMIT ?',(limit,))]
            return result
