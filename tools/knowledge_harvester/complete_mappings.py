"""Fetch only approved-source explicit Wikidata mappings missing from the corpus."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from .acquire_wikidata import cached_json
from .licenses import require_approved
from .models import HarvestError
from .provenance import canonical_json, file_hash
from .storage import Store


def complete(store, output, *, allow_network=False, interactive=False, priority_concepts=()):
    if not allow_network:
        raise HarvestError('Сеть запрещена: нужен --allow-network.')
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    with store.connect() as con:
        sources={r['id']:json.loads(r['metadata']) for r in con.execute('SELECT * FROM sources')}
        requests={}
        for row in con.execute('SELECT payload FROM raw_records WHERE concept_id!=canonical_id'):
            record=json.loads(row[0]);require_approved(sources[record['source']])
            for mapping in record['mappings']:
                if not re.fullmatch(r'wikidata:Q[1-9][0-9]*',mapping):continue
                if con.execute('SELECT 1 FROM raw_records WHERE concept_id=?',(mapping,)).fetchone():continue
                requests.setdefault(mapping.split(':')[1],[]).append(dict(source=record['source'],record=record['source_record_id'],input_sha256=record['input_hash']))
        # One frozen hop of explicit parent IDs for source-derived QA concepts.
        # This is not recursive discovery and never follows fetched parents.
        if len(priority_concepts)>100:raise HarvestError('Не более 100 QA concepts.')
        for concept in sorted(set(priority_concepts)):
            for row in con.execute('SELECT payload FROM raw_records WHERE concept_id=?',(concept,)):
                record=json.loads(row[0]);require_approved(sources[record['source']])
                for relation,target in record['relations']:
                    if relation not in ('P279','P31') or not re.fullmatch(r'wikidata:Q[1-9][0-9]*',target):continue
                    if con.execute('SELECT 1 FROM raw_records WHERE concept_id=?',(target,)).fetchone():continue
                    requests.setdefault(target.split(':')[1],[]).append(dict(source=record['source'],record=record['source_record_id'],
                        input_sha256=record['input_hash'],relation=relation,reason='explicit parent of source-derived QA concept; one hop only'))
    if len(requests)>1000:raise HarvestError('Targeted completion превышает лимит 1000 IDs.')
    plan=dict(ids=sorted(requests),evidence=requests,interactive=interactive,priority_concepts=sorted(set(priority_concepts)))
    plan_path=output/'plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text('utf-8'))!=plan:
        raise HarvestError('Pinned mapping plan изменился; нужен новый output.')
    plan_path.write_text(canonical_json(plan)+'\n','utf-8')
    destination=output/'entities.jsonl'
    if destination.exists():raise HarvestError('Pinned output уже существует.')
    catalog=json.loads(Path(__file__).with_name('source_catalog.json').read_text('utf-8'))
    source=dict(catalog['wikidata'],source_id='wikidata-explicit-'+datetime.now(timezone.utc).strftime('%Y%m%d'),
                acquired_at=datetime.now(timezone.utc).isoformat(),revision='Explicit mapped IDs; individual lastrevid retained')
    require_approved(source)
    responses={};entities=[];missing=[]
    ids=sorted(requests)
    for index in range(0,len(ids),50):
        request=dict(action='wbgetentities',ids='|'.join(ids[index:index+50]),props='info|labels|aliases|descriptions|claims',
                     languages='zh|zh-hans|zh-hant|zh-cn|zh-tw|ru|en',format='json')
        # MediaWiki documents omission for interactive tasks with a waiting user.
        # Background runs retain maxlag=5; this never expands the explicit ID set.
        if not interactive:request['maxlag']=5
        path,data=cached_json('https://www.wikidata.org/w/api.php?'+urlencode(request),output/f'entities-{index:05d}.json','entities',allow_network)
        responses[path.name]=file_hash(path)
        for uid,entity in sorted(data['entities'].items()):
            if uid not in requests:raise HarvestError('API returned an unrequested entity.')
            if 'missing' in entity:missing.append(uid)
            else:
                if not entity.get('lastrevid'):raise HarvestError('API entity revision отсутствует; output не принимается.')
                entities.append(entity)
    destination.write_text(''.join(canonical_json(e)+'\n' for e in entities),'utf-8')
    source.update(source_id='wikidata-explicit-'+file_hash(destination)[:16],input_sha256=file_hash(destination),acquisition=dict(plan=plan,responses=responses,missing=missing))
    (output/'source.json').write_text(canonical_json(source)+'\n','utf-8')
    return dict(requested=len(ids),received=len(entities),missing=missing,input_sha256=source['input_sha256'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-network',action='store_true')
    parser.add_argument('--interactive',action='store_true',help='Explicit interactive request, per MediaWiki maxlag etiquette')
    parser.add_argument('--priority-concepts',type=Path,help='JSON list of existing source concept IDs; one parent hop only')
    args=parser.parse_args()
    concepts=json.loads(args.priority_concepts.read_text('utf-8')) if args.priority_concepts else ()
    print(canonical_json(complete(Store(args.db),args.output,allow_network=args.allow_network,interactive=args.interactive,priority_concepts=concepts)))
