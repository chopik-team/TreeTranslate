"""Synthetic performance data, never a production knowledge corpus."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter
import psutil

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.knowledge_harvester.config import load
from tools.knowledge_harvester.storage import Store
from tools.knowledge_harvester.ingest import ingest
from tools.knowledge_harvester.linking import link
from tools.knowledge_harvester.domains import classify
from tools.knowledge_harvester.review import scan_conflicts
from tools.knowledge_harvester.build.packs import build_packs
from tools.knowledge_harvester.provenance import canonical_json


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sizes',type=int,nargs='+',default=[1000,10000,100000])
    parser.add_argument('--output',type=Path,default=Path('docs/qa/aw072/benchmark.json'));args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True);results=[];process=psutil.Process()
    for size in args.sizes:
        with tempfile.TemporaryDirectory(prefix='harvest-benchmark-') as folder:
            folder=Path(folder);store=Store(folder/'harvest.db');config=load()
            config['domains']={'technical-core':{'roots':['wikidata:Q900000000'],'keywords':[]}}
            source=dict(source_id='synthetic-benchmark',source_url='https://example.org/NOT-PRODUCTION',
                acquired_at='2026-09-24T00:00:00Z',revision='benchmark-v1',license='CC0-1.0',
                redistribution_status='APPROVED_FOR_REDISTRIBUTION',license_url='https://creativecommons.org/publicdomain/zero/1.0/',
                license_checked_at='2026-09-24',attribution='TreeTranslate synthetic benchmark; never production',
                independence_group='synthetic',languages=['zh','ru','en'])
            store.source_add(source);path=folder/'raw.jsonl'
            with path.open('w',encoding='utf-8',newline='\n') as stream:
                for i in range(size):
                    stream.write(canonical_json(dict(id=f'Q{900000001+i}',labels={'zh':{'value':f'测试部件{i:06d}'},'ru':{'value':f'тестовая деталь {i:06d}'}},
                        claims={'P279':[{'mainsnak':{'datavalue':{'value':{'id':'Q900000000'}}}}]}))+'\n')
            started=perf_counter();ingest(store,path,'synthetic-benchmark','wikidata',config);ingest_s=perf_counter()-started
            started=perf_counter();link(store,config);link_s=perf_counter()-started
            with store.connect() as con:
                started=perf_counter()
                for row in con.execute('SELECT * FROM concepts'):
                    classify(con,row['id'],json.loads(row['payload'])['records'],config)
                classify_s=perf_counter()-started
                started=perf_counter();scan_conflicts(con);conflict_s=perf_counter()-started
            started=perf_counter();packs=build_packs(store,config,folder/'packs');build_s=perf_counter()-started
            memory=process.memory_info()
            with store.connect() as con:integrity=[r[0] for r in con.execute('PRAGMA integrity_check')]
            row=dict(records=size,synthetic=True,ingest_seconds=ingest_s,records_per_second=size/ingest_s,
                link_including_classify_seconds=link_s,linking_per_second=size/link_s,classify_seconds=classify_s,
                classify_per_second=size/classify_s,conflicts_seconds=conflict_s,pack_build_seconds=build_s,
                process_peak_rss_bytes=getattr(memory,'peak_wset',memory.rss),db_bytes=store.path.stat().st_size,
                output_pack_bytes=sum(p['bytes'] for p in packs),integrity=integrity)
            results.append(row);args.output.write_text(json.dumps(results,indent=2)+'\n','utf-8')
            print(f'{size}: ingest={ingest_s:.2f}s link={link_s:.2f}s build={build_s:.2f}s',flush=True)


if __name__=='__main__':main()
