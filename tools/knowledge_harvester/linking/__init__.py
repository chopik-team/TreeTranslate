import json
from ..models import CanonicalConcept, LinkType
from ..normalization import preferred, variants, normalize
from ..provenance import canonical_json, digest_json
from ..config import fingerprint
from ..domains import classify
from ..quality import assess
from ..licenses import approved


def _candidate(con, canonical, records, zh, ru, en, domain, evidence, link_type, sources, config, excluded, exhausted, *, zh_records=None, ru_records=None, detail=None):
    identity = [canonical, normalize(zh), normalize(ru), domain, str(link_type)]
    uid = digest_json(identity)
    score, status, reasons = assess(zh, ru, link_type, evidence, records, sources, config, excluded, exhausted, domain)
    chinese = sorted({v for r in (records if zh_records is None else zh_records) for v in variants(r, 'zh')} - {zh})
    russian = sorted({v for r in (records if ru_records is None else ru_records) for v in variants(r, 'ru')} - {ru})
    provenance = [{'source': r['source'], 'record': r['source_record_id'], 'concept': r['concept_id'],
                   'input_sha256': r['input_hash'], 'offset': r['input_offset'], 'metadata': r['metadata'],
                   'labels': r['labels'], 'descriptions': r['descriptions']} for r in records]
    payload = dict(id=uid, concept=canonical, zh=zh, ru=ru, en=en, domain=domain, domains_evidence=evidence,
                   link_type=str(link_type), score=score, status=status, reasons=reasons,
                   zh_variants=chinese, ru_variants=russian, provenance=provenance, manual_review=False)
    if detail is not None:payload['link_evidence']=detail
    if len(chinese) > 32 or len(russian) > 32:
        payload['status'] = status = 'REVIEW'; reasons.append('runtime_variant_limit')
    con.execute('INSERT OR REPLACE INTO candidates VALUES(?,?,?,?,?,?,?,?)',
                (uid, normalize(zh), normalize(ru), domain, status, str(link_type), score, canonical_json(payload)))
    con.executemany('INSERT OR IGNORE INTO candidate_aliases VALUES(?,?,?)',
                    [(normalize(term), domain, uid) for term in [zh, *chinese] if term])


def link(store, config, *, dry_run=False):
    if dry_run:
        return {'action': 'link', 'config_sha256': fingerprint(config)}
    with store.connect() as con:
        sources = {r['id']: json.loads(r['metadata']) for r in con.execute('SELECT * FROM sources')}
        # Derived build tables only. Raw inputs and human decisions are retained.
        for table in ('conflicts', 'candidate_aliases', 'candidates', 'english_labels', 'concepts'):
            con.execute('DELETE FROM ' + table)
        count = 0; skipped_concepts = 0
        for row in con.execute('SELECT DISTINCT canonical_id FROM raw_records ORDER BY canonical_id'):
            uid = row[0]
            records = [json.loads(r[0]) for r in con.execute('SELECT payload FROM raw_records WHERE canonical_id=? ORDER BY source,record_id LIMIT 129', (uid,))]
            if len(records) > 128:
                skipped_concepts += 1
                continue  # Bounded merge; raw evidence stays in the build database.
            canonical = CanonicalConcept(uid, records)
            con.execute('INSERT INTO concepts VALUES(?,?)', (uid, canonical_json(canonical.__dict__)))
            for record in records:
                en = preferred(record['labels'], 'en')
                if en:
                    con.execute('INSERT OR IGNORE INTO english_labels VALUES(?,?)', (normalize(en).casefold(), uid))
            count += 1
        pivot = None
        if config.get('pivot_version') == 2:
            from .pivot import prepare_index, Pivot
            con.execute('CREATE TEMP TABLE concept_aliases(alias TEXT PRIMARY KEY,canonical TEXT)')
            con.executemany('INSERT OR IGNORE INTO concept_aliases VALUES(?,?)',
                ((r['concept_id'],r['canonical_id']) for r in con.execute('SELECT DISTINCT source,concept_id,canonical_id FROM raw_records WHERE concept_id!=canonical_id')
                 if approved(sources[r['source']])))
            prepare_index(con)
            pivot = Pivot(con, config)
        for row in con.execute('SELECT * FROM concepts ORDER BY id'):
            canonical = json.loads(row['payload']); records = canonical['records']; uid = row['id']
            domains, excluded, exhausted = classify(con, uid, records, config)
            if not domains:
                domains = {'unclassified': [{'kind': 'no_technical_evidence'}]}
            zh = sorted({preferred(r['labels'], 'zh') for r in records} - {''})
            ru = sorted({preferred(r['labels'], 'ru') for r in records} - {''})
            en = sorted({preferred(r['labels'], 'en') for r in records} - {''})
            for chinese in zh or ['']:
                for russian in ru or ['']:
                    kind = LinkType.DIRECT if any(preferred(r['labels'], 'zh') == chinese and preferred(r['labels'], 'ru') == russian for r in records) else LinkType.CROSS_SOURCE
                    for domain, evidence in domains.items():
                        _candidate(con, uid, records, chinese, russian, en, domain, evidence, kind, sources, config, excluded, exhausted)
            # Exact English labels/short definitions only. Never nearest-string matching.
            if zh and not ru:
                if pivot is not None:
                    for target_id, target_records, targets_ru, target_domains, target_excluded, target_exhausted, ambiguous, detail in pivot.find(uid, records, domains):
                        for russian in targets_ru:
                            for chinese in zh:
                                for domain, evidence in target_domains.items():
                                    kind = LinkType.AMBIGUOUS if ambiguous else LinkType.PIVOT
                                    _candidate(con, uid + '=>' + target_id, records + target_records, chinese, russian,
                                               sorted({m['source']['term'] for m in detail['english_matches']}), domain,
                                               evidence, kind, sources, config, excluded or target_excluded, exhausted or target_exhausted,
                                               zh_records=records, ru_records=target_records, detail=detail)
                    continue
                meanings = sorted({normalize(v).casefold() for r in records for v in [preferred(r['labels'], 'en'), *r['definitions']]
                                   if v and len(v) <= 100 and len(v.split()) <= 6})
                targets = {}
                for meaning in meanings[:64]:
                    for match in con.execute('SELECT concept FROM english_labels WHERE label=? AND concept!=? ORDER BY concept LIMIT 33', (meaning, uid)):
                        targets[match[0]] = meaning
                for target_id, meaning in sorted(targets.items()):
                    target = json.loads(con.execute('SELECT payload FROM concepts WHERE id=?', (target_id,)).fetchone()[0])
                    targets_ru = sorted({preferred(r['labels'], 'ru') for r in target['records']} - {''})
                    for russian in targets_ru:
                        for chinese in zh:
                            for domain, evidence in domains.items():
                                kind = LinkType.PIVOT if len(targets) == 1 and len(targets_ru) == 1 else LinkType.AMBIGUOUS
                                _candidate(con, uid + '=>' + target_id, records + target['records'], chinese, russian, [meaning], domain,
                                           evidence, kind, sources, config, excluded, exhausted,
                                           zh_records=records, ru_records=target['records'])
        con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('config_sha256', fingerprint(config)))
        con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('merge_limit_skipped_concepts', str(skipped_concepts)))
        revision = con.execute("SELECT value FROM metadata WHERE key='data_revision'").fetchone()
        con.execute("INSERT OR REPLACE INTO metadata VALUES('linked_revision',?)", (revision[0] if revision else '0',))
        from ..review import apply_saved_reviews, scan_conflicts
        apply_saved_reviews(con, config)
        conflicts = scan_conflicts(con, config)
        return {'concepts': count, 'merge_limit_skipped_concepts': skipped_concepts,
                'candidates': con.execute('SELECT count(*) FROM candidates').fetchone()[0], 'conflicts': conflicts}
