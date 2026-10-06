"""Idempotent authored expansion and contextual classification of the official pack.

User stores and frozen evaluation sources are never opened for writing.
"""
from collections import Counter
import csv
from hashlib import sha256
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.glossary.database import Database
from app.glossary.repository import Repository
from app.glossary.normalization import normalize,key

QA = ROOT / 'qa/aw086'
PACK = ROOT / 'assets/knowledge/aw083-body-repair-zh-ru.db'


def categories(source):
    """Multi-label relations: mounting holes retain their body context."""
    if source=='内部':return ['body.body_repair']
    if source=='实际':return ['body.body_measurement']
    labels = []
    for name, terms in (
        ('cooling', ('冷却', '散热器', '储液罐', '节温器', '热管理')),
        ('engine', ('发动机', '机油', '燃油', '火花塞', '点火', '进气', '排气歧管')),
        ('suspension', ('悬架', '减振器', '减震器', '副车架', '定位臂', '稳定杆', '球头', '车轮定位')),
        ('electrical', ('熔断器', '线束', '连接器', '电压', '接地', '蓄电池', '电路')),
        ('diagnostics', ('故障', '诊断', 'GDS', 'DTC')),
        ('body.body_measurement', ('测量', '尺寸', '孔中心', '参考平面', '轨距仪', '卷尺', '探头', '量规', '高度差', '公差')),
        ('body.doors', ('车门', '前门', '后门', '门锁', '铰链', '限位器')),
        ('body.panels', ('面板', '内板', '外板', '加强板')),
        ('body.structure', ('纵梁', '横梁', '侧构件', '立柱', '地板', '车身结构')),
    ):
        if any(term in source for term in terms):
            labels.append(name)
    if any(term in source for term in ('孔', '车身', '机罩', '保险杠', '装饰', '通风罩')):
        labels.append('body.body_repair')
    return list(dict.fromkeys(labels)) or ['common']


def build():
    QA.mkdir(parents=True, exist_ok=True)
    repo = Repository(Database(PACK))
    before = list(repo.rows())
    before_targets = {r.id: (r.source_term, r.target_term, r.variants) for r in before}
    baseline = QA / 'knowledge_base_before.json'
    if not baseline.exists():
        baseline.write_text(json.dumps(dict(entries=len(before), sha256=sha256(PACK.read_bytes()).hexdigest()), indent=2), 'utf-8')
    with (ROOT / 'assets/knowledge/aw086-automotive-reviewed.tsv').open(encoding='utf-8', newline='') as stream:
        additions = list(csv.DictReader(stream, delimiter='\t'))
    existing = {r.source_term: r for r in before}
    for row in additions:
        if row['source'] in existing and existing[row['source']].target_term != row['target']:
            raise ValueError('Existing translation conflict: ' + row['source'])
    inserted = repo.insert_many(dict(
        source_term=r['source'], target_term=r['target'], source_language='zh', target_language='ru',
        domain='automotive', status='BUILTIN', origin='builtin', priority=100, source_pack='aw083-body-repair',
        notes=json.dumps(dict(type=r['type'], sentence_constraints=False, review_status='VERIFIED',
                             reviewer='Codex; not independent human certification'), ensure_ascii=False),
        provenance='Independently authored AW0.8.6 Chinese-Russian terminology; no external paragraphs copied.'
    ) for r in additions if r['source'] not in existing)
    authored = {r['source']: r for r in additions}
    assignments = []
    with repo.db.connect(write=True) as con:
        # Explicit reviewed surface form of the same radiator drain concept.
        alias_entry=con.execute('SELECT id,variants FROM entries WHERE source_term=?',('散热器排放塞',)).fetchone()
        if alias_entry:
            variants=list(dict.fromkeys([*json.loads(alias_entry['variants']),'散热器排放螺塞']))
            con.execute('UPDATE entries SET variants=? WHERE id=?',(json.dumps(variants,ensure_ascii=False),alias_entry['id']))
            token=normalize('散热器排放螺塞',fold=True)
            con.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?)',('zh>ru','automotive',key(token),alias_entry['id'],token))
            con.execute('INSERT OR IGNORE INTO lengths VALUES(?,?,?)',('zh>ru','automotive',len(token)))
        # Optional materialized index belongs only to the bundled official pack.
        con.execute('''CREATE TABLE IF NOT EXISTS knowledge_context_index(
            entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            source_language TEXT NOT NULL, target_language TEXT NOT NULL,
            domain TEXT NOT NULL, subdomain TEXT NOT NULL, entry_type TEXT NOT NULL,
            concept_id TEXT NOT NULL, priority INTEGER NOT NULL,
            PRIMARY KEY(entry_id,subdomain)) WITHOUT ROWID''')
        con.execute('''CREATE INDEX IF NOT EXISTS context_selection ON knowledge_context_index
            (source_language,target_language,domain,subdomain,entry_type)''')
        con.execute('CREATE INDEX IF NOT EXISTS context_concept ON knowledge_context_index(concept_id)')
        con.execute('CREATE INDEX IF NOT EXISTS context_normalized ON entries(source_language,target_language,domain,source_normalized)')
        for entry in list(repo.rows()):
            meta = json.loads(entry.notes or '{}')
            branches = categories(entry.source_term)
            if entry.source_term in authored:
                specified=authored[entry.source_term]['subdomain']
                branches = [specified] if branches==['common'] else list(dict.fromkeys([specified,*branches]))
            kind = meta.get('type', 'term')
            concept = meta.get('concept_id') or 'aw:concept:' + sha256(entry.source_term.encode()).hexdigest()[:20]
            if entry.source_term in ('减震器','减振器'):
                concept='aw:concept:' + sha256('减震器'.encode()).hexdigest()[:20]
            slots = ['DIAGRAM_LABEL', 'COMPONENT_LABEL', 'TABLE_CELL', 'FILENAME', 'FOLDER_NAME']
            if kind in ('phrase', 'full_segment'):
                slots = ['PROSE', 'PROCEDURE_STEP', 'WARNING', 'CONDITION', 'DEFINITION']
            meta.update(concept_id=concept, subdomains=branches, segment_types=slots,
                        context_version='0.8.6', entry_type=kind.upper())
            con.execute('UPDATE entries SET notes=? WHERE id=?', (json.dumps(meta, ensure_ascii=False), entry.id))
            marks=','.join('?' for _ in branches)
            con.execute(f'DELETE FROM knowledge_context_index WHERE entry_id=? AND subdomain NOT IN ({marks})',
                        (entry.id,*branches))
            for branch in branches:
                con.execute('INSERT OR REPLACE INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',
                            (entry.id, entry.source_language, entry.target_language, entry.domain,
                             branch, kind.upper(), concept, entry.priority))
            assignments.append(dict(id=entry.id, source=entry.source_term, target=entry.target_term,
                                    concept_id=concept, type=kind.upper(), subdomains=branches,
                                    segment_types=slots, added=entry.id not in before_targets))
    after = list(repo.rows())
    assert all(before_targets[r.id][:2] == (r.source_term, r.target_term) and set(before_targets[r.id][2])<=set(r.variants)
               for r in after if r.id in before_targets)
    # Extend the existing bounded noun-slot component; no new runtime engine.
    forms_path = ROOT / 'assets/config/automotive-slot-forms.json'
    forms = json.loads(forms_path.read_text('utf-8'))['forms']
    grammar_path = ROOT / 'assets/config/automotive-grammar.json'
    grammar = json.loads(grammar_path.read_text('utf-8'))
    actual_terms = {r.source_term: r.target_term.casefold() for r in after}
    grammar_assignments = []
    for form in forms:
        assert actual_terms.get(form['source']) == form['base'], form['source']
        term = form['base']
        rules = grammar['patterns'].setdefault(term, [])
        bounded = [
            [r'(проверьте|проверить|снимите|замените)\s+' + re.escape(term) + r'\b', r'\1 ' + form['accusative']],
            [r'(при использовании|с помощью)\s+' + re.escape(term) + r'\b', r'\1 ' + form['genitive']],
        ]
        for rule in bounded:
            if rule not in rules:
                rules.append(rule)
        grammar_assignments.append(dict(source=form['source'], target=term, rules=bounded))
    grammar_path.write_text(json.dumps(grammar, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    with repo.db.connect(write=True) as con:
        con.commit()
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    manifest_path = ROOT / 'assets/knowledge/manifest.json'
    manifest = json.loads(manifest_path.read_text('utf-8'))
    pack = next(p for p in manifest['packs'] if p['pack_id'] == 'aw083-body-repair')
    pack.update(entries=len(after), sha256=sha256(PACK.read_bytes()).hexdigest(), version='0.8.6',
                contextual_metadata_version=1)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    stats = dict(entries=len(after), inserted_this_run=inserted,
                 added_since_aw085=len(after) - json.loads(baseline.read_text('utf-8'))['entries'],
                 types=dict(Counter(r['type'] for r in assignments)),
                 subdomains=dict(Counter(b for r in assignments for b in r['subdomains'])),
                 previous_translations_unchanged=True, bytes=PACK.stat().st_size, sha256=pack['sha256'])
    stats['existing_template_noun_slots_added'] = len(forms)
    for name, value in [('knowledge_assignments.json', assignments), ('knowledge_base_after.json', stats),
                        ('grammar_assignments.json', grammar_assignments)]:
        (QA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    build()
