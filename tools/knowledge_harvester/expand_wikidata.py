"""Bounded breadth-first technical subset through the official Wikidata API.

Reuses the pinned AW0.7.2 cache/downloader; no multilingual SPARQL join.
Raw responses and the exact plan remain build-only and support resuming.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlencode

from .acquire_wikidata import cached_json
from .config import load, fingerprint
from .licenses import require_approved
from .models import HarvestError
from .provenance import canonical_json, file_hash


def expand(output, *, allow_network=False, per_domain=1500, depth=3, seed=None, config_path=None):
    if not allow_network:
        raise HarvestError('Сеть запрещена: нужен --allow-network.')
    if not 1 <= per_domain <= 5000 or not 1 <= depth <= 4:
        raise HarvestError('Недопустимый предел API subset.')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    config = load(config_path)
    plan = dict(per_domain=per_domain, depth=depth, policy=fingerprint(config), query_syntax='haswbstatement-pipe-v1',
                seed_sha256=file_hash(seed) if seed else None)
    plan_path = output / 'plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text('utf-8')) != plan:
        raise HarvestError('План изменился; нужен новый output каталог.')
    plan_path.write_text(canonical_json(plan) + '\n', 'utf-8')
    metadata = dict(json.loads(Path(__file__).with_name('source_catalog.json').read_text('utf-8'))['wikidata'],
                    source_id='wikidata-technical-20260925', acquired_at=datetime.now(timezone.utc).isoformat(),
                    revision='API technical subtree subset; individual lastrevid retained', license_checked_at='2026-09-25')
    require_approved(metadata)
    all_ids = set(); queries = []; domains = {}
    if seed:
        with open(seed, encoding='utf-8') as stream:
            all_ids.update(json.loads(line)['id'] for line in stream if line.strip())
    for domain, rule in config['domains'].items():
        found = {root.split(':', 1)[1] for root in rule['roots'] if root.startswith('wikidata:')}
        frontier = sorted(found)
        for level in range(depth):
            next_frontier = set()
            for group in range(0, len(frontier), 16):
                query = 'haswbstatement:' + '|'.join('P279=' + uid for uid in frontier[group:group + 16])
                offset = 0
                while len(found) < per_domain:
                    request = dict(action='query', list='search', srsearch=query, srnamespace=0,
                                   srlimit=min(500, per_domain-len(found)), sroffset=offset, format='json', maxlag=5)
                    path = output / f'{domain}-depth{level}-group{group}-offset{offset}.json'
                    path, response = cached_json('https://www.wikidata.org/w/api.php?' + urlencode(request), path, 'query', True)
                    batch = {row['title'] for row in response['query']['search']}
                    next_frontier.update(batch-found); found.update(batch)
                    queries.append(dict(domain=domain, level=level, query=query, offset=offset,
                                        response=path.name, sha256=file_hash(path), total_hits=response['query'].get('searchinfo',{}).get('totalhits')))
                    continuation = response.get('continue', {}).get('sroffset')
                    if continuation is None or continuation <= offset:
                        break
                    offset = continuation
                    time.sleep(.1)
                if len(found) >= per_domain:
                    break
            frontier = sorted(next_frontier)
            if not frontier or len(found) >= per_domain:
                break
        all_ids.update(found); domains[domain] = len(found)
        print(f'{domain}: {len(found)} source IDs; union {len(all_ids)}', flush=True)
    ids = sorted(all_ids); responses = []
    for index in range(0, len(ids), 50):
        request = dict(action='wbgetentities', ids='|'.join(ids[index:index+50]),
                       props='info|labels|aliases|descriptions|claims', languages='zh|zh-hans|zh-hant|zh-cn|zh-tw|ru|en', format='json', maxlag=5)
        path, _ = cached_json('https://www.wikidata.org/w/api.php?' + urlencode(request), output/f'entities-{index:05d}.json', 'entities', True)
        responses.append(path)
        if index % 500 == 0:
            print(f'entity data: {min(index+50,len(ids))}/{len(ids)}', flush=True)
        time.sleep(.1)
    destination = output / 'entities.jsonl'
    if destination.exists():
        raise HarvestError('Pinned entities.jsonl уже существует.')
    missing = []
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        for path in responses:
            for uid, entity in sorted(json.loads(path.read_text('utf-8'))['entities'].items()):
                if 'missing' in entity:
                    missing.append(uid)
                else:
                    stream.write(canonical_json(entity) + '\n')
    metadata.update(input_sha256=file_hash(destination), acquisition=dict(plan=plan, domains=domains,
                    queries=queries, missing_ids=missing, responses={p.name:file_hash(p) for p in responses}))
    (output/'source.json').write_text(canonical_json(metadata)+'\n', 'utf-8')
    return dict(entities=len(ids)-len(missing), sha256=metadata['input_sha256'], domains=domains)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-network', action='store_true')
    parser.add_argument('--per-domain', type=int, default=1500)
    parser.add_argument('--depth', type=int, default=3)
    parser.add_argument('--seed', type=Path)
    parser.add_argument('--config', type=Path)
    args=parser.parse_args()
    print(canonical_json(expand(args.output, allow_network=args.allow_network,
                               per_domain=args.per_domain, depth=args.depth, seed=args.seed, config_path=args.config)))
