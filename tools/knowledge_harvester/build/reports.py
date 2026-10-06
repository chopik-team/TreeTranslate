import json
import random
from collections import Counter
from pathlib import Path
from ..provenance import canonical_json, digest_json


def report(store):
    with store.connect() as con:
        quality = {}
        for row in con.execute('SELECT payload FROM candidates ORDER BY domain,id'):
            candidate = json.loads(row[0])
            counts = quality.setdefault(candidate['domain'], Counter())
            counts['candidates'] += 1; counts[candidate['status']] += 1
            counts[candidate['link_type']] += 1
            counts['manual_review'] += bool(candidate['manual_review'])
            counts['has_zh_variants'] += bool(candidate['zh_variants'])
            counts['source_declares_traditional'] += any(
                any(k in p['labels'] for k in ('zh-hant','zh-tw')) for p in candidate['provenance'])
        for counts in quality.values():
            counts['direct_percent'] = round(100 * counts['DIRECT_CONCEPT'] / counts['candidates'], 2)
            counts['pivot_percent'] = round(100 * (counts['ENGLISH_PIVOT_EXACT'] + counts['ENGLISH_PIVOT_AMBIGUOUS']) / counts['candidates'], 2)
            counts['manual_review_percent'] = round(100 * counts['manual_review'] / counts['candidates'], 2)
        return {
            'raw_records': con.execute('SELECT count(*) FROM raw_records').fetchone()[0],
            'concepts': con.execute('SELECT count(*) FROM concepts').fetchone()[0],
            'statuses': dict(con.execute('SELECT status,count(*) FROM candidates GROUP BY status')),
            'domains': [dict(r) for r in con.execute('SELECT domain,status,count(*) AS count FROM candidates GROUP BY domain,status')],
            'links': dict(con.execute('SELECT link_type,count(*) FROM candidates GROUP BY link_type')),
            'sources': dict(con.execute('SELECT source,count(*) FROM raw_records GROUP BY source')),
            'conflict_edges': con.execute('SELECT count(*) FROM conflicts').fetchone()[0],
            'rejected_records': con.execute('SELECT count(*) FROM errors').fetchone()[0],
            'review_decisions': con.execute('SELECT count(*) FROM reviews').fetchone()[0],
            'domain_quality': quality,
            'metadata': dict(con.execute('SELECT key,value FROM metadata ORDER BY key')),
            'integrity': [r[0] for r in con.execute('PRAGMA integrity_check')],
            'input_files': [dict(r) for r in con.execute('SELECT hash,source,adapter,offset,records,config,complete FROM files ORDER BY hash,source')],
        }


def export_queue(store, destination, *, sample=None, seed=1729, conflicts_only=False):
    destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed); reservoirs = {}; totals = {}; count = 0
    with store.connect() as con, destination.open('w', encoding='utf-8', newline='\n') as output:
        query = 'SELECT payload FROM candidates ORDER BY domain,id'
        for row in con.execute(query):
            candidate = json.loads(row[0])
            conflicts = [dict(r) for r in con.execute('SELECT other,reason FROM conflicts WHERE candidate=? ORDER BY other', (candidate['id'],))]
            if conflicts_only and not conflicts:
                continue
            item = dict(candidate, candidate_id=candidate['id'], evidence_sha256=digest_json(candidate['provenance']),
                        conflicts=conflicts, suggested_decision='REVIEW', decision='', reviewer='')
            if sample is None:
                output.write(canonical_json(item) + '\n'); count += 1
            else:
                domain = candidate['domain']; totals[domain] = totals.get(domain, 0) + 1
                pool = reservoirs.setdefault(domain, [])
                if len(pool) < sample:
                    pool.append(item)
                else:
                    index = rng.randrange(totals[domain])
                    if index < sample:
                        pool[index] = item
        for domain, pool in sorted(reservoirs.items()):
            for item in sorted(pool, key=lambda r:r['id']):
                output.write(canonical_json(item) + '\n'); count += 1
    return {'exported': count, 'seed': seed, 'manual_validation': False}
