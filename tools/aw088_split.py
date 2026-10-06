"""Freeze whole-document corpus groups before any development knowledge build."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw088_prepare import QA,save,ZIP
from tools.aw087_build import stats
from app.knowledge.profile import DocumentProfiler


def main():
    if (QA/'frozen_holdout_manifest.json').exists():
        print('Already frozen');return
    start=perf_counter();profiler=DocumentProfiler();documents=[];groups=defaultdict(list)
    con=sqlite3.connect(QA/'native_corpus.db')
    for member,digest,size,raw in con.execute('SELECT * FROM documents ORDER BY member'):
        if not member.lower().endswith('.pdf'):continue
        payload=json.loads(raw);lines=payload.get('lines',[])
        p=profiler.profile('zh','ru',segments=lines,filename=Path(member).name,folders=(member,))
        branches=dict(p.subdomains)
        branch=max(branches,key=branches.get) if branches else 'general'
        # Identical native content, even with different PDF metadata/images,
        # remains a single group. Opaque/image-only documents use file SHA.
        text='\n'.join(' '.join(line.split()) for line in lines)
        group=sha256(text.encode()).hexdigest() if len(text)>40 else digest
        item=dict(member=member,sha256=digest,bytes=size,pages=payload.get('pages',0),
            native_chars=payload.get('native_chars',0),domain=p.primary_domain,
            subdomains=list(branches),stratum=branch,group=group,profile=p.summary())
        documents.append(item);groups[group].append(item)
    # Stratify groups by their dominant branch; nearest whole-group 20% target.
    strata=defaultdict(list)
    for group,items in groups.items():
        strata[Counter(i['stratum'] for i in items).most_common(1)[0][0]].append((group,items))
    held=set()
    for branch,items in sorted(strata.items()):
        target=round(sum(len(ds) for _,ds in items)*.2);count=0
        for group,ds in sorted(items,key=lambda x:sha256(('aw088-frozen:'+x[0]).encode()).hexdigest()):
            if abs(count+len(ds)-target)<abs(count-target):held.add(group);count+=len(ds)
    holdout=[d for d in documents if d['group'] in held]
    development=[d for d in documents if d['group'] not in held]
    assert not {d['sha256'] for d in holdout}&{d['sha256'] for d in development}
    assert not {d['group'] for d in holdout}&{d['group'] for d in development}
    inventory=json.loads((QA/'archive_inventory.json').read_text('utf-8'))
    basis=dict(corpus_id='CN7C_2022_REPAIR_MAINTENANCE',archive=str(ZIP),
        source_sha256=inventory['sha256_before'],zip_sha256=inventory['zip_sha256'],
        policy='Whole PDF; identical native text/content SHA grouped; deterministic stratified approx 20%; no split inside PDFs',
        baseline_knowledge=stats(),frozen_before_knowledge_build=True)
    save('knowledge_before.json',stats())
    baseline=QA/'baseline';baseline.mkdir(exist_ok=True)
    for name in ['assets/knowledge/aw083-body-repair-zh-ru.db','assets/config/knowledge-templates.json',
                 'assets/config/automotive-slot-forms.json','assets/config/technical-actions.json','assets/config/knowledge-context.json']:
        shutil.copy2(ROOT/name,baseline/Path(name).name)
    save('frozen_holdout_manifest.json',dict(basis,documents=holdout))
    save('development_manifest.json',dict(basis,documents=development))
    save('corpus_split.json',dict(total=len(documents),holdout=len(holdout),development=len(development),
        holdout_percent=len(holdout)*100/len(documents),groups=len(groups),
        hash_overlap=0,text_group_overlap=0,
        by_stratum={b:dict(total=sum(d['stratum']==b for d in documents),holdout=sum(d['stratum']==b for d in holdout)) for b in sorted({d['stratum'] for d in documents})},
        manifest_sha256=sha256((QA/'frozen_holdout_manifest.json').read_bytes()).hexdigest()))
    save('corpus_map.json',dict(documents=len(documents),pages=sum(d['pages'] for d in documents),
        native_documents=sum(bool(d['native_chars']) for d in documents),
        by_domain=dict(Counter(d['domain'] for d in documents)),by_subdomain=dict(Counter(d['stratum'] for d in documents)),
        archive_branches=dict(Counter(d['member'].split('/')[1] for d in documents)),seconds=perf_counter()-start,
        no_ocr_yet=True,profiles=[{k:v for k,v in d.items() if k!='profile'} for d in documents]))
    print('Frozen',len(development),'development',len(holdout),'holdout',len(groups),'groups',flush=True)

if __name__=='__main__':main()
