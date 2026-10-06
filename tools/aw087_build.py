"""Reviewed authored concept-family expansion; frozen holdout is never read."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.glossary.database import Database
from app.glossary.repository import Repository
from tools.knowledge_harvester.storage import Store
from tools.knowledge_harvester.corpus import candidate,review
from tools.knowledge_harvester.provenance import digest_json

QA=ROOT/'qa/aw087';QA.mkdir(exist_ok=True)
PACK=ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db'

def save(name,value):
    (QA/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')

def stats():
    rows=list(Repository(Database(PACK)).rows());meta=[json.loads(r.notes or '{}') for r in rows]
    return dict(entries=len(rows),bytes=PACK.stat().st_size,sha256=sha256(PACK.read_bytes()).hexdigest(),
        types=dict(Counter(m.get('type','term') for m in meta)),
        subdomains=dict(Counter(b for m in meta for b in m.get('subdomains',[]))),
        review_states=dict(Counter(m.get('review_status','LEGACY_BUILTIN') for m in meta)),
        concepts=len({m.get('concept_id',r.id) for r,m in zip(rows,meta)}),aliases=sum(len(r.variants) for r in rows))

def build():
    if not (QA/'knowledge_before.json').exists():save('knowledge_before.json',stats())
    repo=Repository(Database(PACK));existing=list(repo.rows());by_source={r.source_term:r for r in existing}
    aliases={alias:r for r in existing for alias in r.variants}
    # Merge only this cycle's redundant authored alias rows; original entries and
    # translations remain unchanged. Alias spellings still get explicit forms.
    for row in existing:
        other=aliases.get(row.source_term)
        if other and other.id!=row.id and json.loads(row.notes or '{}').get('context_version')=='0.8.7' and row.target_term.casefold()==other.target_term.casefold():
            repo.remove(row.id);by_source.pop(row.source_term,None)
    form_path=ROOT/'assets/config/automotive-slot-forms.json';form_config=json.loads(form_path.read_text('utf-8'))
    forms={f['source']:f for f in form_config['forms']};store=Store(QA/'harvester.db')
    family_path=ROOT/'assets/knowledge/aw087-authored-families.txt';digest=sha256(family_path.read_bytes()).hexdigest()
    additions=[];reviews=[];relations=[];branch='common';conflicts=[]
    for line in family_path.read_text('utf-8').splitlines():
        if not line or line.startswith('#'):continue
        if line.startswith('['):branch=line[1:-1];continue
        source,nom,gen,acc=line.split('|')
        kind='TERM' if len(source)<=3 else 'COMPOUND'
        old=by_source.get(source) or aliases.get(source)
        if old and old.target_term.casefold()!=nom.casefold():
            conflicts.append(dict(source=source,existing=old.target_term,proposed=nom,decision='PRESERVE_EXISTING; candidate deferred'))
            continue
        concept='aw087:'+sha256((nom+'|'+branch).encode()).hexdigest()[:20]
        uid=candidate(store,source=source,target=nom,domain='automotive',subdomains=[branch],kind=kind,origin='AUTHORED',
            concept_id=concept,provenance=dict(source='aw087-authored',sha256=digest,permission='AUTHORED_FOR_PROJECT',family=branch))
        with store.connect() as con:payload=json.loads(con.execute('SELECT payload FROM candidates WHERE id=?',(uid,)).fetchone()[0])
        evidence=digest_json(payload['provenance'])
        if payload['status']!='VERIFIED':
            review(store,uid,'REVIEWED',reviewer='Codex',reason='Technical meaning and explicit Russian case forms reviewed; short reusable noun, no manual paragraph.',evidence_sha256=evidence)
            review(store,uid,'VERIFIED',reviewer='Codex',reason='Reviewed independently authored concept family; not independent human certification.',evidence_sha256=evidence)
        reviews.append(dict(candidate_id=uid,source=source,target=nom,subdomains=[branch],review_state='VERIFIED',
            provenance='AUTHORED',evidence_sha256=evidence,reviewer='Codex; not independent human certification'))
        forms[source]=dict(source=source,base=nom.lower(),nominative=nom.lower(),genitive=gen,accusative=acc)
        if old:continue
        meta=dict(type=kind.lower(),entry_type=kind,concept_id=concept,subdomains=[branch],review_status='VERIFIED',
            context_version='0.8.7',segment_types=['TITLE','HEADING','TABLE_CELL','COMPONENT_LABEL','DIAGRAM_LABEL','FILENAME','FOLDER_NAME'],
            review_candidate=uid,reviewer='Codex; not independent human certification')
        additions.append(dict(source_term=source,target_term=nom,source_language='zh',target_language='ru',domain='automotive',
            status='BUILTIN',origin='builtin',priority=100,source_pack='aw083-body-repair',notes=json.dumps(meta,ensure_ascii=False),
            provenance='AUTHORED AW0.8.7 technical families; reviewed '+uid+'; source SHA '+digest))
    repo.insert_many(additions)
    # Context-specific meanings are separate rows; no global forced priority.
    source='排气';target='выпуск отработавших газов';concept='aw087:engine-exhaust'
    repo.insert_many([dict(source_term=source,target_term=target,source_language='zh',target_language='ru',domain='automotive',
        status='BUILTIN',origin='builtin',priority=100,source_pack='aw083-body-repair',
        notes=json.dumps(dict(type='term',concept_id=concept,subdomains=['engine'],review_status='VERIFIED',
        segment_types=['COMPONENT_LABEL','HEADING','TABLE_CELL'],context_version='0.8.7'),ensure_ascii=False),
        provenance='AUTHORED; Codex reviewed contextual exhaust sense, distinct from cooling air bleeding.')])
    with repo.db.connect(write=True) as con:
        row=con.execute('SELECT id,notes FROM entries WHERE source_term=? AND target_term=?',('排气','Удаление воздуха')).fetchone()
        meta=json.loads(row['notes']);meta['segment_types']=list(dict.fromkeys([*meta['segment_types'],'HEADING','COMPONENT_LABEL','TABLE_CELL']))
        con.execute('UPDATE entries SET notes=? WHERE id=?',(json.dumps(meta,ensure_ascii=False),row['id']))
        for row in repo.rows():
            meta=json.loads(row.notes or '{}')
            for b in meta.get('subdomains',['common']):
                con.execute('INSERT OR REPLACE INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',
                    (row.id,'zh','ru',row.domain,b,meta.get('type','term').upper(),meta.get('concept_id',str(row.id)),row.priority))
        con.commit();con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    form_config['forms']=list(forms.values());form_config['provenance']='AW0.8.6 + AW0.8.7 authored and Codex-reviewed explicit forms; no morphology guessing'
    form_path.write_text(json.dumps(form_config,ensure_ascii=False,indent=2)+'\n','utf-8')
    # Lightweight reviewed semantic relations stay in the existing Harvester store.
    for child,predicate,parent in [('散热器盖','PART_OF','散热器'),('冷却液','USED_WITH','冷却系统'),
                                  ('冷却风扇电机','PART_OF','冷却风扇总成'),('拆卸','ACTION_ON','component'),
                                  ('机油滤清器','IS_A','filter'),('散热器上软管','RELATED_TO','散热器下软管')]:
        relations.append(dict(child=child,predicate=predicate,parent=parent,provenance='AUTHORED',review_state='VERIFIED'))
        with store.connect() as con:con.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?)',(child,predicate,parent))
    manifest_path=ROOT/'assets/knowledge/manifest.json';manifest=json.loads(manifest_path.read_text('utf-8'))
    p=next(p for p in manifest['packs'] if p['pack_id']=='aw083-body-repair')
    p.update(entries=len(list(repo.rows())),sha256=sha256(PACK.read_bytes()).hexdigest(),version='0.8.7')
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    save('candidate_review.json',reviews);save('candidate_conflicts.json',conflicts);save('concept_relations.json',relations)
    for kind,name in [('TERM','candidate_terms.json'),('COMPOUND','candidate_compounds.json')]:save(name,[r for r in reviews if len(r['source'])<=3 if kind=='TERM'] if kind=='TERM' else [r for r in reviews if len(r['source'])>3])
    save('knowledge_after.json',stats());print(json.dumps(stats(),ensure_ascii=False),flush=True)

if __name__=='__main__':build()
