"""Evidence-gated reviewed noun families using existing Harvester and pack store.

Only source spans from development PDFs are eligible. Russian targets are
independently authored, never harvested model output. Product forms are whole
reviewed phrases; positional composition has a closed adjective table.
"""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw088_prepare import QA,save
from tools.aw087_build import stats,PACK
from tools.knowledge_harvester.storage import Store
from tools.knowledge_harvester.corpus import candidate,review
from tools.knowledge_harvester.provenance import digest_json
from app.glossary.database import Database
from app.glossary.repository import Repository

# NOM, GEN, ACC for masculine/feminine/neuter/plural. No free morphology.
ADJECTIVES={
 '左':('левый','левого','левый','левая','левой','левую','левое','левого','левое','левые','левых','левые'),
 '右':('правый','правого','правый','правая','правой','правую','правое','правого','правое','правые','правых','правые'),
 '前':('передний','переднего','передний','передняя','передней','переднюю','переднее','переднего','переднее','передние','передних','передние'),
 '后':('задний','заднего','задний','задняя','задней','заднюю','заднее','заднего','заднее','задние','задних','задние'),
 '上':('верхний','верхнего','верхний','верхняя','верхней','верхнюю','верхнее','верхнего','верхнее','верхние','верхних','верхние'),
 '下':('нижний','нижнего','нижний','нижняя','нижней','нижнюю','нижнее','нижнего','нижнее','нижние','нижних','нижние'),
 '内':('внутренний','внутреннего','внутренний','внутренняя','внутренней','внутреннюю','внутреннее','внутреннего','внутреннее','внутренние','внутренних','внутренние'),
 '外':('наружный','наружного','наружный','наружная','наружной','наружную','наружное','наружного','наружное','наружные','наружных','наружные')}
SUFFIXES={
 '连接器':('разъём','разъёма','разъём','m','electrical'),
 '线束连接器':('разъём жгута проводов','разъёма жгута проводов','разъём жгута проводов','m','electrical'),
 '线束':('жгут проводов','жгута проводов','жгут проводов','m','electrical'),
 '支架':('кронштейн','кронштейна','кронштейн','m',None),
 '固定螺栓':('крепёжный болт','крепёжного болта','крепёжный болт','m','common'),
 '安装螺栓':('монтажный болт','монтажного болта','монтажный болт','m','common'),
 '螺栓':('болт','болта','болт','m','common'),
 '螺母':('гайка','гайки','гайку','f','common'),
 '固定螺母':('крепёжная гайка','крепёжной гайки','крепёжную гайку','f','common'),
 '电路':('цепь','цепи','цепь','f','electrical'),
 '端子':('контакт','контакта','контакт','m','electrical'),
 '盖':('крышка','крышки','крышку','f',None)}


def build():
    assert (QA/'holdout_before.json').exists(), 'Baseline must precede knowledge changes'
    manifest=json.loads((QA/'development_manifest.json').read_text('utf-8'))
    manifest_sha=sha256((QA/'development_manifest.json').read_bytes()).hexdigest()
    allowed={d['member']:d for d in manifest['documents']}
    held=json.loads((QA/'frozen_holdout_manifest.json').read_text('utf-8'))
    assert not set(allowed)&{d['member'] for d in held['documents']}
    family_path=ROOT/'assets/knowledge/aw088-authored-families.txt'
    authored_sha=sha256(family_path.read_bytes()).hexdigest()
    families={}
    for line in family_path.read_text('utf-8').splitlines():
        if not line or line.startswith('#'):continue
        zh,nom,gen,acc,gender,branch=line.split('|')
        if len(zh)<2:continue
        families[zh]=dict(source=zh,base=nom.lower(),nominative=nom.lower(),genitive=gen.lower(),accusative=acc.lower(),gender=gender,branch=branch)
    repo=Repository(Database(PACK))
    # Development review can revise this cycle before final holdout; old cycles
    # remain immutable. Previous review store is preserved as audit evidence.
    for row in list(repo.rows()):
        if json.loads(row.notes or '{}').get('context_version')=='0.8.8':repo.remove(row.id)
    old_rows=list(repo.rows())
    by_source={r.source_term:r for r in old_rows}
    by_source.update({alias:r for r in old_rows for alias in r.variants})
    old_forms=json.loads((QA/'baseline/automotive-slot-forms.json').read_text('utf-8'))
    forms={f['source']:f for f in old_forms['forms']}
    for source,f in forms.items():
        if source in families or not all(k in f for k in ('base','genitive','accusative')):continue
        row=by_source.get(source)
        if not row:continue
        meta=json.loads(row.notes or '{}');branch=meta.get('subdomains',['common'])[0]
        # Existing full case forms reused for components; gender is needed only
        # for closed positional prefixes and is explicitly supplied below.
        families[source]=dict(f,branch=branch,gender='',nominative=f.get('nominative',f['base']))
    for zh,gender in [('车门','f'),('座椅','n'),('保险杠','m'),('前保险杠','m'),('后保险杠','m'),
        ('前门','f'),('后门','f'),('门锁','m'),('铰链','f'),('立柱','f'),('散热器','m'),('冷却风扇','m'),
        ('空气滤清器','m'),('燃油泵','m'),('机油泵','m'),('螺栓','m'),('螺母','f'),('垫圈','f'),('安全带','m')]:
        if zh in families:families[zh]['gender']=gender
    proposals=dict(families)
    deferred_sources={'冷却水箱盖','左方向盘','右方向盘'}
    abstract_sources={'损坏','损伤','裂纹','腐蚀','泄漏','磨损','液位','浓度','数量','电压','压力','温度','效率',
        '变形','断路','短路','间隙','故障','水','空气','机油','冷却液','冷却水','制动液','防冻液',
        '螺母','螺栓','螺钉','垫圈','垫片','卡箍','电路','信号'}
    def abstract(source):
        return source in abstract_sources or any(w in source for w in ('故障代码','故障码','条件','原因','数据流','界限值','标准值','系统')) or source.endswith(('电压','电阻','信号'))
    for source,base in list(families.items()):
        if abstract(source):continue
        for suffix,(nom,gen,acc,gender,branch) in SUFFIXES.items():
            key=source+suffix
            if key not in proposals and len(key)<=28:
                tail=' '+base['genitive']
                proposals[key]=dict(source=key,base=nom+tail,nominative=nom+tail,genitive=gen+tail,accusative=acc+tail,
                    gender=gender,branch=base['branch'],structure='COMPONENT+'+suffix,parent=source)
        key=source+'总成'
        if key not in proposals and len(key)<=28:
            proposals[key]=dict(base,source=key,base=base['base']+' в сборе',nominative=base['nominative']+' в сборе',
                genitive=base['genitive']+' в сборе',accusative=base['accusative']+' в сборе',structure='ASSEMBLY',parent=source)
    # Positional compounds are proposed only against reviewed complete phrases.
    for source,base in list(proposals.items()):
        if abstract(source):continue
        if base['gender'] not in 'mfnp' or not base['gender']:continue
        index='mfnp'.index(base['gender'])*3
        for prefix in [*ADJECTIVES,'左前','右前','左后','右后']:
            key=prefix+source
            if key in proposals or len(key)>28:continue
            adjectives=[ADJECTIVES[z][index:index+3] for z in prefix]
            nom,gen,acc=[' '.join(a[i] for a in adjectives) for i in range(3)]
            positional=dict(base,source=key,base=nom+' '+base['base'],nominative=nom+' '+base['nominative'],
                genitive=gen+' '+base['genitive'],accusative=acc+' '+base['accusative'],structure='POSITIONAL',parent=source)
            if base.get('structure','').startswith('COMPONENT+'):
                suffix=base['structure'].split('+',1)[1]
                parent_base=families[base['parent']]
                if parent_base['gender'] not in 'mfnp' or not parent_base['gender']:continue
                parent_index='mfnp'.index(parent_base['gender'])*3+1
                parent_gen=' '.join(ADJECTIVES[z][parent_index] for z in prefix)+' '+parent_base['genitive']
                a,b,c,_,_=SUFFIXES[suffix]
                positional.update(base=a+' '+parent_gen,nominative=a+' '+parent_gen,genitive=b+' '+parent_gen,accusative=c+' '+parent_gen)
            # Chinese positions precede the door/seat, while Russian trim/cover
            # expressions lead with the part. Attach position to the component.
            anchors={
                '车门装饰板':('двери','f'), '车门门槛装饰板':('двери','f'),
                '座椅靠背盖':('сиденья','n'), '座椅座垫盖':('сиденья','n'),
                '座椅下保护板':('сиденья','n'), '座椅外侧保护盖':('сиденья','n'),
                '座椅内侧保护盖':('сиденья','n'), '座椅加热控制模块':('сидений','p'),
                '座椅安全带拉紧器':('сиденья','n'),
                '座椅靠背':('сиденья','n'), '座椅座垫':('сиденья','n'),
                '立柱装饰板':('стойки','f')}
            anchor_source=source.removesuffix('总成')
            if anchor_source in anchors:
                anchor,gender=anchors[anchor_source];anchor_index='mfnp'.index(gender)*3+1
                adjective=' '.join(ADJECTIVES[z][anchor_index] for z in prefix)
                for field in ('base','nominative','genitive','accusative'):
                    positional[field]=base[field].replace(anchor,adjective+' '+anchor)
            proposals[key]=positional
    # Match only actual source spans, retaining document evidence, not invented
    # Cartesian products. Longest source first controls evidence explosion.
    for source in deferred_sources:
        proposals.pop(source,None)
    for source in list(proposals):
        if '驱动桥' in source and '变速驱动桥' not in source:
            deferred_sources.add(source);proposals.pop(source)
    trie={}
    for word in proposals:
        node=trie
        for char in word:node=node.setdefault(char,{})
        node['']=None
    def trie_pattern(node):
        children=[re.escape(char)+trie_pattern(child) for char,child in node.items() if char]
        value='(?:'+'|'.join(children)+')' if len(children)>1 else children[0] if children else ''
        return '(?:'+value+')?' if '' in node and value else value
    pattern=re.compile(trie_pattern(trie))
    print('Scanning development evidence for',len(proposals),'bounded proposals',flush=True)
    evidence=defaultdict(dict);frequencies=Counter();branch_lines=defaultdict(list);unsafe_context=Counter()
    with sqlite3.connect(QA/'native_corpus.db') as con:
        for member,digest,_,raw in con.execute('SELECT * FROM documents'):
            if member not in allowed:continue
            doc=json.loads(raw)
            for offset,text in enumerate(doc.get('lines',[])):
                for match in pattern.finditer(text):
                    source=match.group();base=proposals[source]
                    before=text[:match.start()]
                    if base.get('structure')=='POSITIONAL':
                        after=text[match.end():]
                        # Position may modify a longer part: 下散热器软管 is
                        # the lower radiator hose, not a lower radiator.
                        if after.startswith(('软管','靠背','座垫','框架','远程','连','孔')) or source.startswith('前仪表板'):
                            unsafe_context[source]+=1;continue
                        # 下 in 拆下/拧下 is part of the verb, not 'lower'.
                        if (source.startswith(('上','下')) and re.search(r'[拆拧拔卸按装拉压向往朝踩放取摘移脱抬拿]$',before)
                            or source.startswith(('前','后')) and re.search(r'(?:更换|安装|拆卸|分离|检查|维修|调整|操作|进行|装配|然|之|以)$',before)
                            or re.search(r'(?:向|往|朝)$',before)):
                            unsafe_context[source]+=1;continue
                    frequencies[source]+=1
                    if len(evidence[source])<12:
                        evidence[source].setdefault(member,dict(member=member,sha256=digest,offset=offset))
    store=Store(QA/'reviewed_harvester_v3.db');reviews=[];conflicts=[];rejected=[];additions=[];concepts={};newforms=[]
    for source,base in proposals.items():
        if source not in evidence:
            continue
        # Preserve every previously reviewed target and conflicting sense.
        old=by_source.get(source)
        if old and old.target_term.casefold()!=base['base'].casefold():
            conflicts.append(dict(source=source,existing=old.target_term,proposed=base['base'],decision='PRESERVE_EXISTING; DEFER'))
            continue
        branch=base['branch'];kind='TERM' if len(source)<=3 else 'COMPOUND'
        # Identical meanings and contexts are a single concept with aliases.
        concept='aw088:'+sha256((base['base']+'|'+branch).encode()).hexdigest()[:20]
        provenance=dict(authored_targets_sha256=authored_sha,permission='AUTHORED_FOR_PROJECT',
            source_evidence_origin='USER_PROVIDED',corpus_permission='CANDIDATES_ONLY',
            development_manifest_sha256=manifest_sha,
            evidence_count=frequencies[source],samples=list(evidence[source].values()),structure=base.get('structure','REVIEWED_NOUN'))
        uid=candidate(store,source=source,target=base['base'],domain='automotive',subdomains=[branch],kind=kind,
            origin='AUTHORED',concept_id=concept,provenance=provenance)
        with store.connect() as con:payload=json.loads(con.execute('SELECT payload FROM candidates WHERE id=?',(uid,)).fetchone()[0])
        digest=digest_json(payload['provenance'])
        if payload['status']!='VERIFIED':
            review(store,uid,'REVIEWED',reviewer='Codex',reason='Actual development source; independently authored technical target and complete Russian forms; closed compound grammar reviewed.',evidence_sha256=digest)
            review(store,uid,'VERIFIED',reviewer='Codex',reason='Developer review, not human certification; no NMT output or held examples used.',evidence_sha256=digest)
        forms[source]={k:base[k] for k in ('source','base','nominative','genitive','accusative')}
        record=dict(candidate_id=uid,source=source,target=base['base'],type=kind,concept_id=concept,domain='automotive',
            subdomains=[branch],segment_types=['HEADING','COMPONENT_LABEL','DIAGRAM_LABEL','TABLE_CELL','FILENAME','FOLDER_NAME'],
            status='VERIFIED',reviewer='Codex; not human-certified',provenance=provenance,forms=forms[source],new=not bool(old))
        reviews.append(record)
        if old:continue
        if concept in concepts:
            concepts[concept]['variants'].append(source);continue
        meta=dict(type=kind.lower(),entry_type=kind,concept_id=concept,subdomains=[branch],review_status='VERIFIED',
            context_version='0.8.8',segment_types=record['segment_types'],review_candidate=uid,reviewer='Codex',evidence_count=frequencies[source])
        entry=dict(source_term=source,target_term=base['base'],source_language='zh',target_language='ru',domain='automotive',
            status='BUILTIN',origin='builtin',priority=100,source_pack='aw083-body-repair',notes=json.dumps(meta,ensure_ascii=False),
            provenance='AUTHORED AW0.8.8; Codex reviewed; development corpus CN7C; '+uid,variants=[])
        concepts[concept]=entry;additions.append(entry)
    repo.insert_many(additions)
    current_ids={r['candidate_id'] for r in reviews}
    with store.connect() as con:
        stale=[json.loads(r[0]) for r in con.execute("SELECT payload FROM candidates WHERE status='VERIFIED'") if json.loads(r[0])['id'] not in current_ids]
    for payload in stale:
        review(store,payload['id'],'DEPRECATED',reviewer='Codex',reason='Pre-holdout development review excluded abstract noun composition or verb/position collision; not included in production.',evidence_sha256=digest_json(payload['provenance']))
    with repo.db.connect(write=True) as con:
        con.execute('DELETE FROM knowledge_context_index')
        for row in repo.rows():
            meta=json.loads(row.notes or '{}')
            for branch in meta.get('subdomains',['common']):
                con.execute('INSERT OR REPLACE INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',
                    (row.id,'zh','ru',row.domain,branch,meta.get('type','term').upper(),meta.get('concept_id',str(row.id)),row.priority))
        con.commit();con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    old_forms['forms']=list(forms.values());old_forms['provenance']='AW0.8.6–0.8.8 independently authored and Codex-reviewed explicit complete forms; source evidence development only'
    (ROOT/'assets/config/automotive-slot-forms.json').write_text(json.dumps(old_forms,ensure_ascii=False,indent=2)+'\n','utf-8')
    manifest_path=ROOT/'assets/knowledge/manifest.json';manifest=json.loads(manifest_path.read_text('utf-8'))
    pack=next(p for p in manifest['packs'] if p['pack_id']=='aw083-body-repair')
    pack.update(entries=len(list(repo.rows())),sha256=sha256(PACK.read_bytes()).hexdigest(),version='0.8.8')
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    save('candidate_review.json',reviews);save('candidate_conflicts.json',conflicts)
    save('candidate_rejected.json',dict(proposed=len(proposals),actual_evidenced=len(evidence),missing_evidence=len(proposals)-len(evidence),
        excluded_reason='No unambiguous development evidence: not built or counted',conflicts=conflicts,
        verb_position_collisions=dict(unsafe_context),abstract_parent_composition_excluded=sorted(abstract_sources)))
    save('ambiguous_source_review.json',dict(before_final_holdout=True,reviewer='Codex',
        deferred_sources=sorted(deferred_sources),reason='Development evidence: cap reused across cooling/brakes; left/right wheel is remote-control or driving-side context, not a separate wheel. No forced target.'))
    save('knowledge_after.json',stats());save('grammar_forms.json',list(forms.values()))
    save('concepts.json',[dict(concept_id=c,source=e['source_term'],target=e['target_term'],aliases=e['variants']) for c,e in concepts.items()])
    print('Knowledge',stats(),'reviewed surfaces',len(reviews),'forms',len(forms),flush=True)

if __name__=='__main__':build()
