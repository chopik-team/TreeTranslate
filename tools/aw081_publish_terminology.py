"""Apply explicit user terminology review through the existing official pack."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.glossary.database import Database
from app.glossary.models import entry_metadata
from app.glossary.normalization import normalize, key
from app.glossary.repository import Repository

QA = ROOT / 'qa/aw081'
ITERATION = QA / 'iterations/09_user_terminology'


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf8')


def run(authored_name='aw081-user-terminology.json', iteration='09_user_terminology', review_name='user_terminology_review.json'):
    global ITERATION
    ITERATION = QA / 'iterations' / iteration
    authored = ROOT / 'assets/knowledge' / authored_name
    review = json.loads(authored.read_text('utf8'))
    assert review['revision'] == 'AW0.81' and review['references_evaluation_only']
    pack = ROOT / 'assets/knowledge/aw083-body-repair-zh-ru.db'
    forms_path = ROOT / 'assets/config/automotive-slot-forms.json'
    templates_path = ROOT / 'assets/config/knowledge-templates.json'
    manifest_path = ROOT / 'assets/knowledge/manifest.json'
    ITERATION.mkdir(parents=True, exist_ok=True)
    for path in (pack, forms_path, templates_path, manifest_path,
                 QA/'diagnostic_after.json', QA/'diagnostic/holdout_after_production.json',
                 QA/'text_regression_results.json', QA/'work_state.json',
                 ROOT/'app/glossary/engine.py'):
        destination = ITERATION / ('production_before.json' if path.name=='holdout_after_production.json' else path.name)
        if not destination.exists():
            if path == pack:
                with sqlite3.connect(pack) as source, sqlite3.connect(destination) as target:
                    source.backup(target)
                source.close()
                target.close()
            else:
                shutil.copy2(path, destination)
    stage = ITERATION / 'stage.db'
    with sqlite3.connect(pack) as source, sqlite3.connect(stage) as target:
        source.backup(target)
    source.close()
    target.close()
    repository = Repository(Database(stage))
    before = list(repository.rows())
    forms = json.loads(forms_path.read_text('utf8'))
    indexed = {row['source']: row for row in forms['forms']}
    records = []
    for item in review['entries']:
        old = next((row for row in repository.rows() if row.source_term == item['source']), None)
        if old:
            assert old.target_term in {item['target'], item.get('expected_old_target')}, 'Unreviewed target conflict'
        meta = entry_metadata(old) if old else {}
        concept = meta.get('concept_id') or 'aw081:' + item['semantic_key']
        kind = item.get('type', 'COMPOUND')
        meta.update(type=kind.lower(), entry_type=kind, concept_id=concept,
                    semantic_key=item['semantic_key'], subdomains=item.get('subdomains',[item['subdomain']]),
                    review_status='VERIFIED', context_version='0.81',
                    segment_types=['TITLE','HEADING','COMPONENT_LABEL','DIAGRAM_LABEL','TABLE_CELL','FILENAME','FOLDER_NAME'],
                    terminology_review=dict(authored_sha256=sha256(authored.read_bytes()).hexdigest(),
                                            manual=item['manual'], source=review.get('review_origin','USER_TECHNICAL_REVIEW')))
        for field in ('required_subdomains', 'required_context_terms', 'label_only',
                      'required_semantic_facts', 'alias_context_terms', 'reference_only_aliases',
                      'open_reference_aliases', 'semantic_role', 'relation_to', 'introduced_identifiers',
                      'assembly_components', 'operation_unit'):
            if field in item:
                meta[field] = item[field]
        encoded = json.dumps(meta, ensure_ascii=False)
        assert len(encoded) <= 2048
        aliases = sorted(set(old.variants if old else ()) | set(item.get('aliases', [])))
        assert len(aliases) <= 32
        provenance = review.get('review_source','User terminology review 2026-10-04')+'; '+review['manuals'][item['manual']]['verification']
        if old:
            with repository.db.connect(write=True) as connection:
                connection.execute('UPDATE entries SET target_term=?, notes=?, variants=?, provenance=? WHERE id=?',
                    (item['target'], encoded, json.dumps(aliases, ensure_ascii=False), provenance, old.id))
            uid = old.id
        else:
            repository.insert_many([dict(source_term=item['source'], target_term=item['target'],
                source_language='zh', target_language='ru', domain='automotive', status='BUILTIN',
                origin='builtin', priority=100, source_pack='aw083-body-repair', notes=encoded,
                provenance=provenance, variants=aliases)])
            uid = next(row.id for row in repository.rows() if row.source_term==item['source'])
        with repository.db.connect(write=True) as connection:
            for surface in (item['source'], *aliases):
                normalized = normalize(surface, fold=True)
                connection.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?)',
                    ('zh>ru', 'automotive', key(normalized), uid, normalized))
                connection.execute('INSERT OR IGNORE INTO lengths VALUES(?,?,?)', ('zh>ru','automotive',len(normalized)))
        for surface in (item['source'], *aliases):
            indexed[surface] = dict(source=surface, base=item['target'], nominative=item['target'],
                                    genitive=item['genitive'], accusative=item['accusative'])
            for case in ('instrumental', 'locative', 'dative', 'same_nominative'):
                if case in item:
                    indexed[surface][case] = item[case]
        records.append(dict(source=item['source'], concept_id=concept, semantic_key=item['semantic_key'],
                            new_entry=old is None, target=item['target'], aliases=aliases,
                            previous_target=old.target_term if old else None))
    with repository.db.connect(write=True) as connection:
        connection.execute('DELETE FROM knowledge_context_index')
        for row in repository.rows():
            meta = entry_metadata(row)
            for branch in meta.get('subdomains', ['common']):
                connection.execute('INSERT INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',
                    (row.id,'zh','ru',row.domain,branch,meta.get('type','term').upper(),meta.get('concept_id',str(row.id)),row.priority))
        connection.commit()
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    after = list(repository.rows())
    stage.replace(pack)
    forms['forms'] = list(indexed.values())
    save(forms_path, forms)
    templates = json.loads(templates_path.read_text('utf8'))
    cups = ['活塞皮碗','润滑脂杯']
    additions = [
        dict(id='aw081-paired-inspection-heading', source='{X}和{Y}检查',
             target='Проверка {X} и {Y}', forms=dict(X='genitive',Y='genitive'), allowed_slots=cups),
        dict(id='aw081-single-inspection-heading', source='{X}检查',
             target='Проверка {X}', forms=dict(X='genitive'), allowed_slots=cups),
        dict(id='aw081-qualified-inspection-heading', source='{X}（{Y}）',
             target='{X} ({Y})', forms=dict(X='nominative',Y='nominative'),
             allowed_slots=['制动系统','抖动检查'], slot_allowed=dict(X=['制动系统'],Y=['抖动检查']), capitalize=True)
    ]
    additions = review.get('templates', additions)
    for rule in additions:
        defaults = dict(status='VERIFIED', domain='automotive', subdomains=['brakes'],
                        types=['TITLE','HEADING','DIAGRAM_LABEL','COMPONENT_LABEL','TABLE_CELL'], shared_forms=True,
                        provenance='Authored reusable grammar; user-reviewed service concepts; no reference sentence copy.')
        for field, value in defaults.items():
            rule.setdefault(field, value)
    existing_ids = {rule['id'] for rule in additions}
    templates['templates'] = [rule for rule in templates['templates'] if rule['id'] not in existing_ids] + additions
    for extension in review.get('template_extensions', []):
        assert extension['manual'] in review['manuals']
        for rule in templates['templates']:
            if rule.get('action')==extension['action'] and rule['source'] in extension['source_patterns']:
                assert rule['status']=='VERIFIED' and rule.get('shared_forms')
                rule['allowed_slots']=sorted(set(rule['allowed_slots']) | set(extension['slots']))
    save(templates_path, templates)
    manifest = json.loads(manifest_path.read_text('utf8'))
    item = next(row for row in manifest['packs'] if row['pack_id']=='aw083-body-repair')
    item.update(entries=len(after), sha256=sha256(pack.read_bytes()).hexdigest(), version='0.81')
    save(manifest_path, manifest)
    result = dict(revision='AW0.81', status='PUBLISHED_PENDING_LEVEL_2', entries_before=len(before),
                  entries_after=len(after), rows=records, templates_added=len(additions),
                  existing_concept_ids_preserved=True, references_not_modified=True,
                  no_full_segment_additions=True, scope='Terminology and bounded nominal templates; long prose remains open.')
    save(QA/review_name, result)
    print(dict(entries_before=len(before),entries_after=len(after),templates_added=len(additions)))


if __name__ == '__main__':
    run(*sys.argv[1:])
