"""Synthetic glossary scaling test in a disposable DB; not production population."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psutil
from app.glossary.engine import GlossaryEngine
from app.glossary.importer import import_terms
from app.glossary.maintenance import integrity


def timed(call,repeats=5):
    values=[]
    for _ in range(repeats):
        t=perf_counter();call();values.append((perf_counter()-t)*1000)
    return dict(median_ms=statistics.median(values),max_ms=max(values),samples=repeats)


def entry(i):
    source,target=(('en','ru'),('zh','ru'),('ru','en'))[i%3]
    text={'en':f'component {i:06d}','zh':f'部件{i:06d}','ru':f'деталь {i:06d}'}[source]
    return dict(source_term=text,target_term=f'деталь {i:06d}' if target=='ru' else f'component {i:06d}',
                source_language=source,target_language=target,domain='general',status='CONFIRMED')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sizes',type=int,nargs='+',default=[10,100,1000,10000,100000,500000])
    p.add_argument('--output',type=Path,default=Path('docs/qa/aw071/benchmark.json'))
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    rows=[];process=psutil.Process()
    with tempfile.TemporaryDirectory(prefix='glossary-benchmark-') as folder:
        path=Path(folder)/'glossary.db';g=GlossaryEngine(path);previous=0
        for size in sorted(set(a.sizes)):
            rss_before=process.memory_info().rss
            source=Path(folder)/'input.jsonl'
            with source.open('w',encoding='utf-8') as stream:
                for i in range(previous,size):stream.write(json.dumps(entry(i),ensure_ascii=False)+'\n')
            start=perf_counter();inserted=import_terms(g.repository,source,trusted=True);duration=perf_counter()-start
            def startup():
                fresh=GlossaryEngine(path)
                with fresh.db.connect() as c:c.execute('SELECT revision FROM metadata').fetchone()
            def index():
                g.indexes.clear();g.cache.clear();assert g.lookup('component 000000','en','ru')
            def scan(text,lang='en',target='ru'):
                g.cache.clear();return g.lookup(text,lang,target)
            row=dict(entries=size,inserted=inserted,import_insert_seconds=duration,
                db_startup=timed(startup),lazy_index_first_lookup=timed(index),
                exact=timed(lambda:scan('component 000000')),
                chinese=timed(lambda:scan('检查部件000001。','zh')),
                cyrillic=timed(lambda:scan('деталь 000002','ru','en')))
            for n in (1,10,100):
                count=min(n,(size+2)//3)
                text='; '.join(f'component {i*3:06d}' for i in range(count))
                def terms():assert len(scan(text))==count
                row[f'{n}_terms']=dict(actual=count,**timed(terms,3))
            corpus=[f'Check component {i*3:06d}.' for i in range(min(100,(size+2)//3))]
            def batch():
                g.cache.clear()
                for text in corpus:assert g.lookup(text,'en','ru')
            row['batch']=dict(segments=len(corpus),**timed(batch,3))
            row.update(rss_before_bytes=rss_before,rss_after_bytes=process.memory_info().rss,
                       rss_peak_working_set_bytes=process.memory_info().peak_wset if hasattr(process.memory_info(),'peak_wset') else None,
                       database_bytes=path.stat().st_size,integrity=integrity(g.db),length_catalogs=len(g.indexes))
            with g.db.connect() as c:
                row['query_plan']=[tuple(r) for r in c.execute('EXPLAIN QUERY PLAN SELECT * FROM aliases WHERE pair=? AND domain=? AND hash=?',('en>ru','general','x'))]
            rows.append(row);a.output.write_text(json.dumps(rows,indent=2),'utf-8');previous=size
            print(f'{size}: import={duration:.2f}s exact={row["exact"]["median_ms"]:.2f}ms 100terms={row["100_terms"]["median_ms"]:.2f}ms',flush=True)


if __name__=='__main__':main()
