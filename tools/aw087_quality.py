"""Reuse frozen body gold and existing evaluators with an isolated read adapter."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import aw086_analyze as analysis
from tools.aw087_build import QA,save
original_read=analysis.read
def routed_read(path):
    return original_read(path.replace('qa/aw086/','qa/aw087/'))

if __name__=='__main__':
    analysis.QA=QA;analysis.read=routed_read
    analysis.body();analysis.coolant()
    # No import of a script with top-level evaluation; reroute its existing
    # source in this isolated QA namespace, keeping historical artifacts intact.
    source=(ROOT/'tools/aw086_coverage.py').read_text('utf-8').replace("QA=ROOT/'qa/aw086'","QA=ROOT/'qa/aw087'")
    exec(compile(source,str(ROOT/'tools/aw086_coverage.py'),'exec'),{'__file__':str(ROOT/'tools/aw086_coverage.py'),'__name__':'aw087_coverage'})
    runs={name:json.loads((QA/(name+'_e2e.json')).read_text('utf-8')) for name in ['body','coolant']}
    from app.documents.measurements import collect
    processes=collect()
    save('timings.json',{name:dict(wall_seconds=r['elapsed'],routing={k:v for k,v in r['context']['metrics'].items() if k.endswith('_time') or k=='knowledge_lookup_total'},
        processes=processes.get(r['run'],{}).get('processes',{}),snapshots=r['context']['snapshots']) for name,r in runs.items()})
    save('knowledge_metrics.json',{name:r['context'] for name,r in runs.items()})
    save('body_regression.json',json.loads((QA/'body_quality.json').read_text('utf-8')))
