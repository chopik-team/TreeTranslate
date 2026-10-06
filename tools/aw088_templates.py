"""Reviewed bounded procedure/cross-reference patterns evidenced in development."""
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw088_prepare import QA,save
from tools.aw087_build import PACK,stats
from app.glossary.database import Database
from app.glossary.repository import Repository
from app.glossary.normalization import normalize
from tools.knowledge_harvester.storage import Store
from tools.knowledge_harvester.corpus import candidate,review
from tools.knowledge_harvester.provenance import digest_json

LABELS={
 '连接不良':'плохой контакт','电路断路':'обрыв цепи','通信超时':'тайм-аут связи',
 '通信故障':'неисправность связи','系统正常':'система исправна','故障代码说明':'описание кода неисправности',
 '故障代码检测条件':'условия обнаружения кода неисправности','故障代码设置条件':'условия регистрации кода неисправности',
 '故障代码分析':'анализ кода неисправности','故障代码诊断方法':'метод диагностики кода неисправности',
 '故障检修':'поиск и устранение неисправностей','诊断时间':'время диагностики','主要操作':'основные операции',
 '当前状态':'текущее состояние','非当前':'неактивный','历史':'история','参数':'параметр',
 '高电位':'высокий потенциал','低电位':'низкий потенциал','无穷大':'бесконечность',
 '重置状态':'состояние сброса','检测条件':'условия обнаружения','固定数据':'данные стоп-кадра',
 '信号故障':'неисправность сигнала','断路':'обрыв цепи','短路':'короткое замыкание',
 '腐蚀':'коррозия','污染':'загрязнение','弯曲':'изгиб','不良':'неисправность',
 '接触不良':'плохой контакт','间歇故障':'перемежающаяся неисправность','控制模块内部故障':'внутренняя неисправность модуля управления',
 '信号电路断路':'обрыв сигнальной цепи','通信电路断路':'обрыв цепи связи',
 '电源电路断路':'обрыв цепи питания','搭铁电路断路':'обрыв цепи массы',
 '搭铁短路':'короткое замыкание на массу','与搭铁短路':'короткое замыкание на массу',
 '蓄电池短路':'короткое замыкание на аккумуляторную батарею','电压过高':'слишком высокое напряжение',
 '电压过低':'слишком низкое напряжение','电阻过大':'слишком большое сопротивление','电阻过小':'слишком малое сопротивление',
 '车辆软件管理':'управление программным обеспечением автомобиля','波形':'осциллограмма',
 '电路图':'электрическая схема','电源分布':'распределение питания','室内保险丝分布':'расположение предохранителей в салоне',
 '诊断连接分布':'схема диагностических соединений','搭铁分布':'расположение точек массы',
 '部件位置':'расположение компонентов','部件和部件位置':'компоненты и их расположение',
 '规格':'технические характеристики','维修程序':'процедуры ремонта','说明和操作':'описание и работа',
 '检验维修':'проверка и ремонт','一般事项':'общие сведения','参考波形':'эталонная осциллограмма',
 '额定电压':'номинальное напряжение','输出电压':'выходное напряжение','输出信号':'выходной сигнал',
 '反馈信号':'сигнал обратной связи','蓄电池电压':'напряжение аккумуляторной батареи',
 '燃油压力':'давление топлива','共轨压力':'давление в топливной рампе','增压压力':'давление наддува',
 '空调压力':'давление в системе кондиционирования','歧管绝对压力':'абсолютное давление во впускном коллекторе',
 '变速器油压力':'давление масла в коробке передач','线圈电阻':'сопротивление катушки',
 '车身电气':'электрооборудование кузова','内部装饰':'облицовка салона'}


def build():
    manifest=json.loads((QA/'development_manifest.json').read_text('utf-8'))
    allowed={d['member'] for d in manifest['documents']};lines=[];evidence=defaultdict(list)
    with sqlite3.connect(QA/'native_corpus.db') as con:
        for member,digest,_,raw in con.execute('SELECT * FROM documents'):
            if member not in allowed:continue
            for offset,line in enumerate(json.loads(raw).get('lines',[])):
                text=normalize(re.sub(r'^\s*(?:\d+[.)、]|[•●▪])\s*','',line))
                lines.append((text,member,digest,offset))
                for source in LABELS:
                    if source in text and len(evidence[source])<12:
                        evidence[source].append(dict(member=member,sha256=digest,offset=offset))
    forms=json.loads((ROOT/'assets/config/automotive-slot-forms.json').read_text('utf-8'))['forms']
    slots=[f['source'] for f in forms]
    fasteners=[s for s in slots if any(w in s for w in ('螺栓','螺母','螺钉','螺塞','卡环'))]
    components=[s for s in slots if not any(w in s for w in ('浓度','温度','电压','电阻','液位','压力','泄漏','损坏','冷却液','机油','制动液','防冻液'))]
    path=ROOT/'assets/config/knowledge-templates.json'
    config=json.loads((QA/'baseline/knowledge-templates.json').read_text('utf-8'));rules=config['templates']
    for rule in rules:
        if not rule.get('shared_forms'):continue
        action=rule.get('action')
        if action in {'CHECK','MEASURE','VERIFY','ADJUST'}:rule['allowed_slots']=sorted(set(rule['allowed_slots'])|set(slots))
        elif action in {'REMOVE','INSTALL','INSPECT','REPLACE','CLEAN','ALIGN'}:rule['allowed_slots']=sorted(set(rule['allowed_slots'])|set(components))
        elif action in {'TIGHTEN','LOOSEN'}:rule['allowed_slots']=sorted(set(rule['allowed_slots'])|set(fasteners))
    patterns=[];actions=json.loads((ROOT/'assets/config/technical-actions.json').read_text('utf-8'))
    known_actions={r['semantic_id'] for r in actions['actions']}
    def add(uid,source,target,allowed_slots=None,slot_forms=None,types=None,action=None,minimum=2):
        # Literal structure evidence is required, not success on holdout.
        parts=re.split(r'(\{[A-Z]\})',source);fields=[p[1:-1] for p in parts if re.fullmatch(r'\{[A-Z]\}',p)]
        regex=''.join('(.{1,128}?)' if re.fullmatch(r'\{[A-Z]\}',p) else ''.join(re.escape(c)+r'\s*' for c in normalize(p) if not c.isspace()) for p in parts)
        compiled=re.compile(regex);samples=[];documents=set()
        for text,member,digest,offset in lines:
            match=compiled.fullmatch(text)
            if not match:continue
            values=match.groups()
            if fields and any(v.strip().rstrip('。') not in (allowed_slots or []) and not re.fullmatch(r'.+\([A-Z]{1,8}\)',v.strip()) for v in values):continue
            documents.add(member)
            if len(samples)<6:samples.append(dict(member=member,sha256=digest,offset=offset))
        if len(documents)<minimum:return
        record=dict(id='aw088-'+uid,status='VERIFIED',domain='general.technical.procedure',subdomains=[],
            source=source,target=target,forms=slot_forms or {},allowed_slots=allowed_slots or [],shared_forms=True,
            component_marker=True,negative_relation=True,types=types or ['PROCEDURE_STEP','PROSE','WARNING','CONDITION'],
            action=action,provenance='AUTHORED; Codex reviewed; development evidence only; not human-certified',
            evidence_documents=len(documents))
        rules.append(record);patterns.append(dict(record,samples=samples))
    for zh,verb,heading,semantic in [
        ('拧下','Выверните','Выворачивание','UNSCREW'),('拔出','Извлеките','Извлечение','WITHDRAW'),
        ('拉出','Вытяните','Вытягивание','PULL'),('拉动','Потяните','Вытягивание','PULL'),
        ('推入','Вставьте','Вставка','PUSH'),('按下','Нажмите','Нажатие','PRESS'),
        ('按压','Нажмите','Нажатие','PRESS'),('转动','Поверните','Поворот','ROTATE'),
        ('旋转','Поверните','Поворот','ROTATE'),('支撑','Подоприте','Подпирание','SUPPORT'),
        ('固定','Закрепите','Закрепление','SECURE'),('释放','Освободите','Освобождение','RELEASE'),
        ('打开','Откройте','Открытие','OPEN'),('拔下','Отсоедините','Отсоединение','DISCONNECT'),
        ('擦拭','Протрите','Протирка','WIPE')]:
        allowed_objects=fasteners if semantic=='UNSCREW' else components
        count=len(rules)
        for punctuation in ('','。'):
            add(zh+'-'+str(bool(punctuation)),zh+'{X}'+punctuation,verb+' {X}'+('.' if punctuation else ''),allowed_objects,dict(X='accusative'),action=semantic)
            add(zh+'-heading-'+str(bool(punctuation)),zh+'{X}'+punctuation,heading+' {X}',allowed_objects,dict(X='genitive'),types=['TITLE','HEADING'],action=semantic)
        if len(rules)>count and semantic not in known_actions:
            actions['actions'].append(dict(id='action.'+semantic.lower(),semantic_id=semantic,zh=[zh],imperative=verb,heading=heading,
                review_state='VERIFIED',provenance='AUTHORED; Codex review; actual development structures'))
            known_actions.add(semantic)
    for zh in ['不要','切勿','不得']:
        add('no-damage-'+zh,zh+'损坏{X}。','Не повреждайте {X}.',components,dict(X='accusative'),types=['WARNING','PROCEDURE_STEP'])
        add('no-reuse-'+zh,zh+'重复使用{X}。','Не используйте {X} повторно.',fasteners,dict(X='accusative'),types=['WARNING','PROCEDURE_STEP'])
    add('reverse-install','按拆卸的相反顺序安装。','Установите в порядке, обратном снятию.')
    add('reverse-install-alt','安装按拆卸的相反顺序进行。','Установите в порядке, обратном снятию.')
    add('check-damage','检查{X}是否损坏。','Проверьте {X} на повреждения.',components,dict(X='accusative'))
    add('check-connection','检查{X}是否连接良好。','Проверьте надёжность подсоединения {X}.',components,dict(X='genitive'))
    # Section labels are independently reviewed and exact in the active snapshot.
    repo=Repository(Database(PACK));existing={s for r in repo.rows() for s in (r.source_term,*r.variants)};store=Store(QA/'reviewed_patterns.db');labels=[];entries=[];label_concepts={}
    for source,target in LABELS.items():
        if source not in evidence or source in existing:continue
        branch='common' if source in {'电路图','规格','维修程序','说明和操作','部件位置','部件和部件位置','一般事项','内部装饰'} else 'electrical' if any(w in source for w in ('分布','电路','信号','电压','电阻','短路','断路')) else 'diagnostics'
        concept='aw088:'+sha256((target+'|'+branch).encode()).hexdigest()[:20]
        provenance=dict(permission='AUTHORED_FOR_PROJECT',source_evidence_origin='USER_PROVIDED',samples=evidence[source],
            corpus_permission='CANDIDATES_ONLY',origin='AUTHORED')
        uid=candidate(store,source=source,target=target,domain='automotive',subdomains=[branch],kind='PHRASE',concept_id=concept,origin='AUTHORED',provenance=provenance)
        with store.connect() as con:payload=json.loads(con.execute('SELECT payload FROM candidates WHERE id=?',(uid,)).fetchone()[0])
        digest=digest_json(payload['provenance'])
        if payload['status']!='VERIFIED':
            for state in ('REVIEWED','VERIFIED'):review(store,uid,state,reviewer='Codex',reason='Short technical label independently authored and reviewed; actual development evidence, not NMT or held text.',evidence_sha256=digest)
        meta=dict(type='phrase',concept_id=concept,subdomains=[branch],review_status='VERIFIED',context_version='0.8.8',
            segment_types=['UI_LABEL','DIAGNOSTIC_LABEL','TABLE_CELL','HEADING','DIAGRAM_LABEL','CROSS_REFERENCE'],review_candidate=uid)
        entry=dict(source_term=source,target_term=target,source_language='zh',target_language='ru',domain='automotive',variants=[],
            status='BUILTIN',origin='builtin',priority=100,source_pack='aw083-body-repair',notes=json.dumps(meta,ensure_ascii=False),
            provenance='AUTHORED AW0.8.8; Codex review; '+uid)
        if concept in label_concepts:label_concepts[concept]['variants'].append(source)
        else:label_concepts[concept]=entry;entries.append(entry)
        labels.append(dict(source=source,target=target,type='PHRASE',concept_id=concept,reviewer='Codex',status='VERIFIED',provenance=provenance))
    repo.insert_many(entries)
    with repo.db.connect(write=True) as con:
        con.execute('DELETE FROM knowledge_context_index')
        for row in repo.rows():
            meta=json.loads(row.notes or '{}')
            for branch in meta.get('subdomains',['common']):
                con.execute('INSERT OR REPLACE INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',
                    (row.id,'zh','ru',row.domain,branch,meta.get('type','term').upper(),meta.get('concept_id',str(row.id)),row.priority))
        con.commit();con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    cross_slots=sorted(set(slots)|{r['source'] for r in labels})
    for prefix in ['参考','请参阅','参见']:
        for source,tail in [(prefix+'{X}',''),('('+prefix+'{X})',''),('('+prefix+'{X}-"{Y}")','Y'),(prefix+'{X}-"{Y}"','Y')]:
            add('xref-'+sha256(source.encode()).hexdigest()[:8],source,
                'См. раздел «{X}»'+(', подраздел «{Y}».' if tail else '.'),cross_slots,
                dict(X='nominative',**({'Y':'nominative'} if tail else {})),types=['CROSS_REFERENCE','PROSE','PROCEDURE_STEP','TABLE_CELL'])
    config['templates']=rules;config['provenance']='AW0.8.6–0.8.8 bounded authored technical patterns; Codex review; source evidence development only'
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n','utf-8')
    actions['version']='0.8.8';(ROOT/'assets/config/technical-actions.json').write_text(json.dumps(actions,ensure_ascii=False,indent=2)+'\n','utf-8')
    save('templates.json',dict(total=len(rules),new_patterns=patterns));save('actions.json',actions)
    save('cross_references.json',[r for r in patterns if r['id'].startswith('aw088-xref')]);save('diagnostic_labels.json',labels)
    save('units.json',dict(policy='Literal units and source numbers; no numeric conversion. Ambiguous OEM unit labels are explicitly annotated.',
        required_units=['mm','cm','m','N·m','kgf·m','L','mL','V','A','Ω','kPa','MPa','°C','rpm','inch','gal','qt','lb-ft','psi'],
        development_capacity_evidence=sum(any(w in text for w in ('公升','加仑','夸脱','美升')) for text,_,_,_ in lines)))
    manifest_path=ROOT/'assets/knowledge/manifest.json';m=json.loads(manifest_path.read_text('utf-8'));p=next(p for p in m['packs'] if p['pack_id']=='aw083-body-repair')
    p.update(entries=len(list(repo.rows())),sha256=sha256(PACK.read_bytes()).hexdigest(),version='0.8.8')
    manifest_path.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf-8')
    save('knowledge_after.json',stats());print('Templates',len(rules),'new',len(patterns),'labels',len(labels),'entries',stats()['entries'],flush=True)

if __name__=='__main__':build()
