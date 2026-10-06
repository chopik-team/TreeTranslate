"""Bounded official API subset, after local fixtures pass. No HTML scraping."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from time import sleep
from .network import download
from .licenses import require_approved
from .models import HarvestError
from .config import load
from .provenance import file_hash, canonical_json


def cached_json(url, path, key, allow_network):
    request_path=path.with_suffix('.request.json')
    request={'url':url,'expected_key':key}
    if request_path.exists():
        if json.loads(request_path.read_text('utf-8')) != request:
            raise HarvestError('Cached API request отличается; выберите новый output каталог.')
    else:
        if path.exists() or any(path.parent.glob(path.stem+'-retry-*'+path.suffix)):
            raise HarvestError('У cached API response нет pinned request; выберите новый каталог.')
        request_path.write_text(canonical_json(request)+'\n','utf-8')
    for attempt in range(3):
        candidate=path if attempt==0 else path.with_name(path.stem+f'-retry-{attempt}'+path.suffix)
        if not candidate.exists():
            if attempt:sleep(5*attempt)
            download(url,candidate,allow_network=allow_network,max_bytes=32000000)
        data=json.loads(candidate.read_text('utf-8'))
        if key in data:return candidate,data
    raise HarvestError('Официальный API занят или вернул ошибку; ответы сохранены для повторного запуска.')


def acquire(output, *, allow_network=False, sample=100, domains=('automotive','metallurgy','technical-core')):
    if not allow_network:
        raise HarvestError('Сеть запрещена: нужен --allow-network.')
    if not 1 <= sample <= 10000:
        raise HarvestError('Ограниченный API sample: 1..10000.')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    config=load();catalog=json.loads(Path(__file__).with_name('source_catalog.json').read_text('utf-8'))
    metadata=dict(catalog['wikidata'],acquired_at=datetime.now(timezone.utc).isoformat(),revision='API subset; individual lastrevid retained')
    require_approved(metadata)
    roots=sorted({q.split(':')[1] for domain in domains for q in config['domains'][domain]['roots']})
    # Avoid expensive multilingual joins on the public query service. The official
    # search API supports indexed haswbstatement queries; labels are checked locally.
    queries=[]; ids=set(roots)
    for root in roots:
        query='haswbstatement:P279='+root
        query_file=output/('query-'+root+'.json')
        url='https://www.wikidata.org/w/api.php?'+urlencode(dict(action='query',list='search',srsearch=query,srnamespace=0,srlimit=min(100,max(10,sample//len(roots))),format='json'))
        query_file,data=cached_json(url,query_file,'query',allow_network)
        ids.update(r['title'] for r in data['query']['search'])
        queries.append({'query':query,'sha256':file_hash(query_file)})
    ids=roots[:sample]+sorted(ids-set(roots))[:max(0,sample-len(roots))]
    paths=[]
    for index in range(0,len(ids),20):
        batch=ids[index:index+20];path=output/f'entities-{index:05d}.json'
        url='https://www.wikidata.org/w/api.php?'+urlencode(dict(action='wbgetentities',ids='|'.join(batch),props='info|labels|aliases|descriptions|claims',languages='zh|zh-hans|zh-hant|zh-cn|zh-tw|ru|en',format='json'))
        path,_=cached_json(url,path,'entities',allow_network)
        paths.append(path)
    destination=output/'entities.jsonl'
    if destination.exists():raise HarvestError('Pinned entities.jsonl уже существует.')
    count=0
    with destination.open('w',encoding='utf-8',newline='\n') as stream:
        for path in paths:
            entities=json.loads(path.read_text('utf-8'))['entities']
            for uid,entity in sorted(entities.items()):
                if entity.get('missing') is not None:continue
                stream.write(canonical_json(entity)+'\n');count+=1
    metadata.update(source_id='wikidata-preview',input_sha256=file_hash(destination),
                    acquisition={'queries':queries,'responses':{p.name:file_hash(p) for p in paths}})
    (output/'source.json').write_text(canonical_json(metadata)+'\n','utf-8')
    return {'entities':count,'sha256':file_hash(destination),'source':str(output/'source.json')}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-network',action='store_true');parser.add_argument('--sample',type=int,default=100)
    parser.add_argument('--domains',nargs='+',default=['automotive','metallurgy','technical-core'])
    args=parser.parse_args();print(canonical_json(acquire(args.output,allow_network=args.allow_network,sample=args.sample,domains=args.domains)))


if __name__=='__main__':main()
