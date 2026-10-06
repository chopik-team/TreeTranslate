"""Build-only corpus measurements and cross-domain review, never runtime data."""
from collections import Counter
import json
from pathlib import Path

from .build.reports import report, export_queue
from .provenance import canonical_json


def write_reports(store, destination):
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    summary = report(store)
    with store.connect() as con:
        coverage = Counter()
        for (payload,) in con.execute('SELECT payload FROM raw_records'):
            row = json.loads(payload); labels = row['labels']
            chinese = [v for key,v in labels.items() if key.split('-')[0] == 'zh']
            coverage['raw_with_zh'] += bool(chinese)
            coverage['raw_direct_zh_ru'] += bool(chinese and labels.get('ru'))
            coverage['source_declared_traditional'] += bool(labels.get('zh-hant') or labels.get('zh-tw'))
            coverage['source_declared_simplified'] += bool(labels.get('zh-hans') or labels.get('zh-cn'))
            coverage['chinese_compound_records'] += any(len(v) > 1 for v in chinese)
        coverage['unique_candidate_zh_terms'] = con.execute("SELECT count(DISTINCT zh) FROM candidates WHERE zh!=''").fetchone()[0]
        coverage['unique_verified_pairs'] = con.execute("SELECT count(*) FROM (SELECT DISTINCT zh,ru FROM candidates WHERE status='VERIFIED')").fetchone()[0]
        source_status = Counter()
        for (payload,) in con.execute('SELECT payload FROM candidates'):
            row = json.loads(payload)
            for source in {p['source'] for p in row['provenance']}:
                source_status[source + ':' + row['status']] += 1
        summary.update(coverage=dict(coverage), source_candidate_status=dict(source_status))
        # Cross-domain homographs are a separate review surface: runtime already
        # requires an explicit domain and must not pick a global winning target.
        con.execute('CREATE TEMP TABLE ambiguous_domains AS SELECT zh FROM candidates WHERE zh!=? AND ru!=? AND status!=? GROUP BY zh HAVING count(DISTINCT domain)>1 AND count(DISTINCT ru)>1', ('','','REJECTED'))
        count = 0
        with (destination/'cross-domain-review.jsonl').open('w', encoding='utf-8') as output:
            for (payload,) in con.execute('SELECT payload FROM candidates WHERE zh IN (SELECT zh FROM ambiguous_domains) ORDER BY zh,domain,id'):
                row = json.loads(payload)
                row['cross_domain_review'] = 'Different target across domains; no global winner. Domain-specific source evidence must be reviewed.'
                output.write(canonical_json(row)+'\n'); count += 1
        summary['cross_domain_review_candidates'] = count
    export_queue(store, destination/'review-queue.jsonl')
    export_queue(store, destination/'stratified-review.jsonl', sample=50)
    export_queue(store, destination/'conflicts.jsonl', conflicts_only=True)
    (destination/'corpus-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
    return summary
