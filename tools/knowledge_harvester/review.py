import json
from .models import HarvestError
from .provenance import canonical_json, digest_json
from .normalization import normalize

DECISIONS = {'ACCEPT', 'REJECT', 'CHANGE_TARGET', 'CHANGE_DOMAIN', 'MERGE', 'KEEP_AUTO'}


def apply_saved_reviews(con, config):
    for review in con.execute('SELECT * FROM reviews ORDER BY candidate'):
        found = con.execute('SELECT payload FROM candidates WHERE id=?', (review['candidate'],)).fetchone()
        if not found:
            continue
        payload = json.loads(found[0]); decision = json.loads(review['payload'])
        # Evidence changes invalidate old acceptance, even if labels remained equal.
        if decision['evidence_sha256'] != digest_json(payload['provenance']):
            continue
        action = review['decision']
        if action == 'CHANGE_TARGET':
            if not decision.get('target') or len(decision['target']) > 512:
                raise HarvestError('Нужен допустимый target.')
            payload['ru'] = decision['target']; payload['ru_variants'] = []
        if action == 'CHANGE_DOMAIN':
            if decision.get('domain') not in config['domains']:
                raise HarvestError('Неизвестный domain.')
            payload['domain'] = decision['domain']
        if action == 'MERGE':
            target = con.execute('SELECT payload FROM candidates WHERE id=?', (decision.get('merge_into'),)).fetchone()
            if not target:
                raise HarvestError('MERGE target отсутствует.')
            other = json.loads(target[0])
            if (payload['zh'],payload['ru'],payload['domain']) != (other['zh'],other['ru'],other['domain']):
                raise HarvestError('MERGE разрешён только для идентичной пары/domain.')
            other['provenance'] = sorted(other['provenance'] + [p for p in payload['provenance'] if p not in other['provenance']], key=canonical_json)
            con.execute('UPDATE candidates SET payload=? WHERE id=?', (canonical_json(other), other['id']))
            payload['status'] = 'REJECTED'
        else:
            payload['status'] = 'REJECTED' if action == 'REJECT' else 'AUTO' if action == 'KEEP_AUTO' else 'VERIFIED'
        payload['manual_review'] = True; payload['review'] = decision
        con.execute('UPDATE candidates SET ru=?,domain=?,status=?,payload=? WHERE id=?',
                    (normalize(payload['ru']),payload['domain'],payload['status'],canonical_json(payload),payload['id']))
        con.execute('UPDATE candidate_aliases SET domain=? WHERE candidate=?', (payload['domain'],payload['id']))


def scan_conflicts(con, config=None):
    con.execute('DELETE FROM conflicts')
    con.execute('''INSERT OR IGNORE INTO conflicts
        SELECT a.candidate,b.candidate,'same_source_domain_different_target'
        FROM candidate_aliases a JOIN candidate_aliases b ON a.alias=b.alias AND a.domain=b.domain AND a.candidate!=b.candidate
        JOIN candidates ca ON ca.id=a.candidate JOIN candidates cb ON cb.id=b.candidate
        WHERE ca.ru!=cb.ru AND ca.ru!='' AND cb.ru!='' AND ca.status!='REJECTED' AND cb.status!='REJECTED' ''')
    if (config or {}).get('pivot_version') == 2:
        # An English retrieval hypothesis is not an observed bilingual assertion.
        # It cannot invalidate a direct concept unless the target source also
        # declares the Chinese form (or another real direct conflict exists).
        for row in con.execute("""SELECT a.id AS hypothesis,b.id AS direct,a.payload FROM conflicts f
            JOIN candidates a ON a.id=f.candidate JOIN candidates b ON b.id=f.other
            WHERE a.link_type IN ('ENGLISH_PIVOT_EXACT','ENGLISH_PIVOT_AMBIGUOUS')
              AND b.link_type IN ('DIRECT_CONCEPT','CROSS_SOURCE_CONCEPT')"""):
            hypothesis=json.loads(row['payload'])
            if not hypothesis.get('link_evidence',{}).get('shared_zh'):
                con.execute("""UPDATE conflicts SET reason='retrieval_only_challenge'
                    WHERE (candidate=? AND other=?) OR (candidate=? AND other=?)""",
                    (row['hypothesis'],row['direct'],row['direct'],row['hypothesis']))
    for row in con.execute("SELECT id,payload FROM candidates WHERE id IN (SELECT candidate FROM conflicts WHERE reason!='retrieval_only_challenge')"):
        payload = json.loads(row['payload']); payload['status'] = 'REVIEW'
        payload['reasons'].append('unresolved_conflict')
        con.execute("UPDATE candidates SET status='REVIEW',payload=? WHERE id=?", (canonical_json(payload),row['id']))
    return con.execute('SELECT count(*) FROM conflicts').fetchone()[0]


def import_reviews(store, path, config, *, dry_run=False):
    if dry_run:
        return {'action': 'review-import', 'path': str(path)}
    with store.connect() as con, open(path, encoding='utf-8') as stream:
        count = 0
        for line in stream:
            if len(line) > 65536:
                raise HarvestError('review_record_limit')
            decision = json.loads(line)
            if decision.get('decision') not in DECISIONS or not decision.get('reviewer') or not decision.get('evidence_sha256'):
                raise HarvestError('Нужны decision, reviewer, evidence_sha256.')
            if not con.execute('SELECT 1 FROM candidates WHERE id=?', (decision.get('candidate_id'),)).fetchone():
                raise HarvestError('Неизвестный candidate_id.')
            con.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?)', (decision['candidate_id'],decision['decision'],canonical_json(decision)))
            count += 1
        apply_saved_reviews(con,config); scan_conflicts(con,config)
        return {'decisions': count}
