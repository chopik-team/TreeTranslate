"""Publish only explicitly reviewed development evidence; preserve old entries."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.glossary.database import Database
from app.glossary.repository import Repository
from app.glossary.normalization import normalize, key
from tools.knowledge_harvester.storage import Store
from tools.knowledge_harvester.corpus import candidate, review
from tools.knowledge_harvester.provenance import digest_json

QA = ROOT / 'qa/aw081'
DEFERRED = {'助力器': 'Ambiguous booster battery / brake booster; no forced generic object.',
            '制动行程': 'Pedal stroke probable, but truncated development contexts insufficient.'}
NOTES = {
    '自动除湿传感器': 'Windshield humidity and HVAC controller explicitly described in development source.',
    '除湿传感器': 'Same evidenced sensor; generic humidity sensor without inventing system role.',
    '工作比': '100 percent signal to cooling fan: duty factor, not inverse duty ratio.',
    '张紧装置': 'Generic tensioning device only; no belt-specific meaning imposed on ratchet/filler contexts.',
    '进气促动器': 'Recirculation position establishes HVAC intake flap actuator.'}
DECLARED_ALIASES = {'前车门':'前门', '后车门':'后门'}
QUANTITIES = {'容量','容积','电压','压力','温度'}
LABEL_ONLY = {'说明','容量','容积'}


def reviewed_template_slots(reviews, rule):
    """A noun review does not grant every action to that noun."""
    excluded = {'转速','盲区','工作比','说明','总容量','储液容量','离合器位置'} | QUANTITIES
    return {row['source'] for row in reviews if row['status']=='VERIFIED'
            and row.get('semantic_role') not in {'quantity','diagnostic_relation'}
            and row['source'] not in excluded
            and (rule['id'] in row.get('template_rule_ids',[])
                 or row.get('alias_of') in rule.get('allowed_slots',[]))}


def run(evidence_name='component_development_evidence.json', authored_name='aw081-semantic-components.txt', review_name='component_review.json'):
    evidence_path = QA / evidence_name
    data = json.loads(evidence_path.read_text('utf8'))
    authored = ROOT / 'assets/knowledge' / authored_name
    assert sha256(authored.read_bytes()).hexdigest() == data['authored_sha256']
    pack = ROOT / 'assets/knowledge/aw083-body-repair-zh-ru.db'
    stage = QA / 'component-pack-stage.db'
    # SQLite backup includes any committed WAL state; it never resets the pack.
    with sqlite3.connect(pack) as source, sqlite3.connect(stage) as target:
        source.backup(target)
    source.close()
    target.close()
    repo = Repository(Database(stage))
    existing = list(repo.rows())
    by_source = {surface: row for row in existing for surface in (row.source_term, *row.variants)}
    forms_path = ROOT / 'assets/config/automotive-slot-forms.json'
    forms_data = json.loads(forms_path.read_text('utf8'))
    forms = {f['source']: f for f in forms_data['forms']}
    store = Store(QA / 'semantic_harvester.db')
    additions, reviews, alias_updates, metadata_updates = [], [], [], []
    for item in data['rows']:
        item = dict(item)
        role = item.get('semantic_role')
        if role not in (None,'quantity','diagnostic_relation'):
            raise ValueError('Unknown reviewed semantic role')
        if 'label_only' in item and not isinstance(item['label_only'],bool):
            raise ValueError('Invalid reviewed label scope')
        source = item['source']
        old = by_source.get(source)
        parent_source = DECLARED_ALIASES.get(source)
        if parent_source and old is None:
            old = by_source.get(parent_source)
            assert old is not None, 'Declared alias requires an existing reviewed parent.'
        reason = DEFERRED.get(source)
        if not item['frequency']:
            reason = 'No independent development evidence; not published.'
        if old and old.target_term.casefold().replace('ё', 'е') != item['target'].casefold().replace('ё', 'е'):
            reason = 'Existing target differs; preserve old concept and defer explicit conflict review.'
        if reason:
            item.update(status='DEFERRED', reason=reason)
            reviews.append(item)
            continue
        provenance = dict(revision='AW0.81', source='USER_PROVIDED_DEVELOPMENT',
            authored_sha256=data['authored_sha256'], evidence_sha256=sha256(evidence_path.read_bytes()).hexdigest(),
            development_manifest_sha256=data['development_manifest_sha256'], samples=item['samples'],
            permission='AUTHORED_FOR_PROJECT', references_not_used=True)
        concept = json.loads(old.notes or '{}').get('concept_id') if old else 'aw081.component.' + sha256(item['target'].encode()).hexdigest()[:16]
        kind = 'ALIAS' if parent_source else ('TERM' if len(source) <= 4 else 'COMPOUND')
        uid = candidate(store, source=source, target=item['target'], domain='automotive', subdomains=[item['subdomain']], kind=kind,
                        origin='AUTHORED', concept_id=concept, provenance=provenance)
        with store.connect() as connection:
            payload = json.loads(connection.execute('SELECT payload FROM candidates WHERE id=?', (uid,)).fetchone()[0])
        for state in ('REVIEWED', 'VERIFIED'):
            review(store, uid, state, reviewer='Codex',
                   reason=NOTES.get(source, 'Independent technical target and complete Russian noun forms reviewed; not human certification.'),
                   evidence_sha256=digest_json(payload['provenance']))
        forms[source] = dict(source=source, base=item['target'], nominative=item['target'],
                             genitive=item['genitive'], accusative=item['accusative'])
        if source in QUANTITIES:
            forms[source]['gender'] = item['gender']
        item.update(status='VERIFIED', candidate_id=uid, concept_id=concept, reviewer='Codex; not human-certified',
                    new_entry=old is None, reason=NOTES.get(source, 'Unambiguous development component evidence.'))
        if parent_source:
            item['type'] = 'ALIAS'
            item['alias_of'] = parent_source
            if source not in old.variants and source != old.source_term:
                alias_updates.append((old,source,uid))
            if parent_source not in forms:
                forms[parent_source] = dict(forms[source],source=parent_source)
        reviews.append(item)
        if old:
            if source in LABEL_ONLY:
                meta = json.loads(old.notes or '{}')
                meta.update(label_only=True,scope_review=dict(reviewer='Codex',revision='AW0.81',candidate_id=uid))
                metadata_updates.append((old.id,json.dumps(meta,ensure_ascii=False)))
            continue
        meta = dict(type=kind.lower(), entry_type=kind, concept_id=concept, subdomains=[item['subdomain']],
                    review_status='VERIFIED', context_version='0.81', review_candidate=uid,
                    reviewer='Codex', evidence_count=item['frequency'],
                    segment_types=['HEADING','COMPONENT_LABEL','DIAGRAM_LABEL','TABLE_CELL','FILENAME','FOLDER_NAME'])
        if role:
            meta['semantic_role'] = role
        if item.get('label_only'):
            meta['label_only'] = True
        if source in QUANTITIES:
            meta['semantic_role'] = 'quantity'
        if source in LABEL_ONLY:
            meta['label_only'] = True
        if source == '说明':
            meta['sentence_constraints'] = False  # Also a verb in prose; nominal heading only.
        additions.append(dict(source_term=source, target_term=item['target'], source_language='zh', target_language='ru',
            domain='automotive', status='BUILTIN', origin='builtin', priority=100, source_pack='aw083-body-repair',
            notes=json.dumps(meta, ensure_ascii=False), provenance='AUTHORED AW0.81; DEV evidence; Codex reviewed; '+uid))
    added = repo.insert_many(additions)
    with repo.db.connect(write=True) as connection:
        for uid,notes in metadata_updates:
            assert len(notes) <= 2048
            connection.execute('UPDATE entries SET notes=? WHERE id=?',(notes,uid))
        for row,source,uid in alias_updates:
            variants = sorted(set(row.variants)|{source})
            assert len(variants) <= 32
            meta = json.loads(row.notes or '{}')
            meta.setdefault('alias_reviews',{})[source] = dict(candidate_id=uid,reviewer='Codex',revision='AW0.81',
                evidence_sha256=sha256(evidence_path.read_bytes()).hexdigest())
            encoded_meta = json.dumps(meta,ensure_ascii=False)
            assert len(encoded_meta) <= 2048
            connection.execute('UPDATE entries SET variants=?,notes=? WHERE id=?',
                               (json.dumps(variants,ensure_ascii=False),encoded_meta,row.id))
            normalized = normalize(source,fold=True)
            pair = row.source_language+'>'+row.target_language
            connection.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?)',(pair,row.domain,key(normalized),row.id,normalized))
            connection.execute('INSERT OR IGNORE INTO lengths VALUES(?,?,?)',(pair,row.domain,len(normalized)))
        connection.execute('DELETE FROM knowledge_context_index')
        for row in repo.rows():
            meta = json.loads(row.notes or '{}')
            for branch in meta.get('subdomains', ['common']):
                connection.execute('INSERT OR REPLACE INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',
                    (row.id, 'zh', 'ru', row.domain, branch, meta.get('type','term').upper(), meta.get('concept_id',str(row.id)), row.priority))
        connection.commit()
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    # Atomically replace one verified staged pack, without changing original references.
    stage.replace(pack)
    forms_data['forms'] = list(forms.values())
    forms_path.write_text(json.dumps(forms_data, ensure_ascii=False, indent=2)+'\n', 'utf8')
    templates_path = ROOT / 'assets/config/knowledge-templates.json'
    templates = json.loads(templates_path.read_text('utf8'))
    for rule in templates['templates']:
        if rule.get('shared_forms'):
            rule['allowed_slots'] = sorted(set(rule.get('allowed_slots', [])) | reviewed_template_slots(reviews,rule))
    templates_path.write_text(json.dumps(templates, ensure_ascii=False, indent=2)+'\n', 'utf8')
    manifest_path = ROOT / 'assets/knowledge/manifest.json'
    manifest = json.loads(manifest_path.read_text('utf8'))
    entry = next(p for p in manifest['packs'] if p['pack_id'] == 'aw083-body-repair')
    entry.update(entries=len(existing)+added, sha256=sha256(pack.read_bytes()).hexdigest(), version='0.81')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', 'utf8')
    (QA / review_name).write_text(json.dumps(dict(rows=reviews, added=added,
         reviewed=sum(r['status']=='VERIFIED' for r in reviews), forms=len(forms)), ensure_ascii=False, indent=2), 'utf8')
    print(dict(added=added, aliases_added=len(alias_updates), forms=len(forms)))


if __name__ == '__main__':
    run(*sys.argv[1:])
