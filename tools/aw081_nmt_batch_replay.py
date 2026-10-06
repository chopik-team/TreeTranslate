"""Replay captured native requests only; never opens or translates a PDF."""
import hashlib
import json
from collections import defaultdict
from time import perf_counter
from tools.aw081_nmt_batch_scheduler_5pdf import QA,read,save


def run():
    assert not (QA/'batch_replay.json').exists(),'Captured replay already recorded; no implicit repetition'
    from app.engine.runtime.cuda_libraries import load_cuda_libraries
    load_cuda_libraries()
    import ctranslate2
    baseline=read(QA/'baseline.json')['nmt']
    groups=defaultdict(list)
    for row in baseline['batches']:
        if row['device']=='cuda' and 'm2m100' in row['model'] and row['sequences']==1 and row['tokens']<=32 and 'outputs' in row:
            groups[(row['model'],json.dumps(row['settings'],sort_keys=True))].append(row)
    results={str(n):dict(calls=0,sequences=0,seconds=0.,mismatches=[],exact_prepared_inputs=True) for n in (1,2,4,8)}
    options=next(r['options'] for r in baseline['requests'] if r['backend']=='m2m100' and r['options']['device']=='cuda')
    for (model,setting),rows in groups.items():
        translator=ctranslate2.Translator(model,device=options['device'],compute_type=options['compute_type'],intra_threads=options['threads'],inter_threads=1)
        settings=json.loads(setting)
        translator.translate_batch(rows[0]['source'],**settings)  # Excluded native replay warmup.
        for size in (1,2,4,8):
            stat=results[str(size)]
            for start in range(0,len(rows),size):
                group=rows[start:start+size]
                source=[r['source'][0] for r in group]
                cfg=dict(settings,target_prefix=[r['settings']['target_prefix'][0] for r in group])
                t=perf_counter();output=translator.translate_batch(source,**cfg)
                stat['seconds']+=perf_counter()-t;stat['calls']+=1;stat['sequences']+=len(group)
                for index,(captured,actual) in enumerate(zip(group,output,strict=True)):
                    if actual.hypotheses!=captured['outputs'][0]:
                        stat['mismatches'].append(dict(captured_index=start+index,member=captured['member'],source=captured['source'],before=captured['outputs'][0],after=actual.hypotheses))
            stat['exact_outputs']=not stat['mismatches']
        translator.unload_model(to_cpu=False)
    save(QA/'batch_replay.json',dict(scope='Captured single-sequence CUDA M2M inputs <=32 source pieces; no PDF jobs',options=options,groups=len(groups),results=results,pass_=all(x['exact_outputs'] for x in results.values())))
    print(json.dumps({n:{k:v for k,v in r.items() if k!='mismatches'}|{'mismatches':len(r['mismatches'])} for n,r in results.items()}),flush=True)


if __name__=='__main__':run()
