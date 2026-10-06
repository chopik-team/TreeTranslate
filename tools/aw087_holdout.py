"""Freeze before evaluation; evaluation never changes knowledge or references."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw087_build import QA,save,PACK

def knowledge_hashes():
    names=['assets/knowledge/aw083-body-repair-zh-ru.db','assets/knowledge/aw087-authored-families.txt',
        'assets/config/knowledge-templates.json','assets/config/automotive-slot-forms.json','assets/config/knowledge-context.json']
    return {name:sha256((ROOT/name).read_bytes()).hexdigest() for name in names}

def validate_revision(held):
    current=knowledge_hashes()
    changes={name for name,digest in current.items() if held['knowledge_hashes'][name]!=digest}
    if not changes:return current
    assert changes=={'assets/config/knowledge-templates.json'}
    old=json.loads((QA/'frozen_template_definitions.json').read_text('utf-8'))
    new=json.loads((ROOT/'assets/config/knowledge-templates.json').read_text('utf-8'))
    old_rules={r['id']:r for r in old['templates']};new_rules={r['id']:r for r in new['templates']}
    assert old_rules.keys()==new_rules.keys()
    changed={uid for uid in old_rules if old_rules[uid]!=new_rules[uid]}
    assert changed=={'drain-plug-loosen','drain-plug-tighten'}
    for uid in changed:
        expected=dict(old_rules[uid]);expected['target']=expected['target'].replace('охлаждающую воду','охлаждающую жидкость').replace('охлаждающей воды','охлаждающей жидкости')
        assert expected==new_rules[uid]
        assert new_rules[uid]['source'] not in {r['source'] for r in held['rows']}
    assert sha256((QA/'frozen_template_definitions.json').read_bytes()).hexdigest()==held['knowledge_hashes']['assets/config/knowledge-templates.json']
    save('post_freeze_development_correction.json',dict(changed_templates=sorted(changed),
        evidence='Existing coolant development corpus steps 4/5 (AW086 and AW087), identified before freeze; corrected legacy literal coolant wording. No holdout failed example used.',
        changes={name:dict(before=held['knowledge_hashes'][name],after=current[name]) for name in changes},
        no_new_entries_or_patterns=True))
    return current

def freeze():
    path=QA/'automotive_semantic_holdout.json'
    if path.exists():print('Already frozen');return
    forms={f['source']:f for f in json.loads((ROOT/'assets/config/automotive-slot-forms.json').read_text('utf-8'))['forms']}
    areas={
        'body':(['焊接电极','定位夹具','车身密封胶','防腐涂层'],'车身维修 车门 钣金'),
        'cooling':(['水泵','节温器壳体','膨胀水箱盖','冷却液温度传感器'],'冷却液 散热器 冷却风扇'),
        'engine':(['点火线圈','机油泵','空气滤清器','发动机支座'],'发动机 机油 燃油'),
        'suspension':(['稳定杆衬套','转向节','轮毂轴承','悬架衬套'],'悬架 减振器 副车架'),
        'brakes':(['制动卡钳','制动主缸','制动盘','制动软管'],'制动 制动液 刹车'),
        'electrical':(['继电器','线束连接器','发电机','起动机'],'电压 线束 接地'),
        'diagnostics':(['诊断接口','故障指示灯','车辆识别码','故障历史'],'诊断 故障码 DTC'),
        'service_procedure':(['螺母','垫圈','卡箍','密封垫'],'发动机 机油 散热器 冷却液'),
    }
    rows=[]
    for area,(objects,cues) in areas.items():
        combos=[('检查','Проверьте'),('测量','Измерьте'),('确认','Проверьте'),('更换','Замените')]
        # Only physically replaceable objects use replace; diagnostic scalar
        # labels exercise inspection/measurement rather than nonsensical action.
        if area=='diagnostics':combos=[('检查','Проверьте'),('测量','Измерьте'),('确认','Проверьте'),('检查','Проверьте')]
        candidates=[]
        for zh,ru in combos:
            for obj in objects:
                source=zh+obj+'。'
                if source not in {r['source'] for r in candidates}:candidates.append(dict(source=source,reference=ru+' '+forms[obj]['accusative']+'.',expected_route='safe_template'))
        # Diagnostic set gets a distinct reviewed heading, not duplicate examples.
        while len(candidates)<13:
            obj=objects[len(candidates)%4];candidates.append(dict(source='检查'+obj,reference='Проверка '+forms[obj]['genitive'],expected_route='heading_template',segment_type='HEADING'))
        for case in candidates[:13]:rows.append(dict(case,id=f'{area}-{len(rows):03}',area=area,profile_cues=cues,segment_type=case.get('segment_type','PROCEDURE_STEP')))
        obj=objects[0]
        for source,reference in [(f'维修后应再次确认{obj}没有损坏。',f'После ремонта следует повторно убедиться, что {forms[obj]["base"]} не повреждён.'),
            (f'如果{obj}损坏,应先停止操作。',f'Если {forms[obj]["base"]} повреждён, следует сначала прекратить работу.')]:
            rows.append(dict(id=f'{area}-{len(rows):03}',area=area,source=source,reference=reference,profile_cues=cues,segment_type='PROSE',expected_route='model_or_constraints'))
    assert len(rows)==120 and len({r['source'] for r in rows})==120
    save('automotive_semantic_holdout.json',dict(frozen_before_evaluation=True,knowledge_hashes=knowledge_hashes(),
        source='AUTHORED new combinations after knowledge development; synthetic evaluation, not unseen OEM documents',
        development_separate=True,reviewer='Codex; references not independent human certification',rows=rows))
    print('Frozen',len(rows),'rows',flush=True)

def evaluate():
    from app.engine.factory import create_translation_engine
    from app.engine.types import TranslationRequest
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    path=QA/'automotive_semantic_holdout.json';digest=sha256(path.read_bytes()).hexdigest();held=json.loads(path.read_text('utf-8'))
    revision=validate_revision(held)
    engine=create_translation_engine(memory=TranslationMemoryEngine(QA/'semantic-isolated-tm.db'),
        glossary=GlossaryEngine(QA/'semantic-isolated-user.db',builtin_paths=bundled_paths()))
    rows=[]
    try:
        with engine.runtime.keep_warm():
            for case in held['rows']:
                p=engine.profile_document('zh','ru',segments=[case['profile_cues']])
                r=engine.translate(TranslationRequest(case['source'],'zh','ru',context_profile=p,segment_type=case['segment_type']))
                exact=r.translated_text==case['reference'];rows.append(dict(case,output=r.translated_text,knowledge_source=r.knowledge_source,
                    backend=r.backend,grade='PASS' if exact else 'REVIEW_REQUIRED',exact=exact,profile=p.summary()))
        assert sha256(path.read_bytes()).hexdigest()==digest and revision==knowledge_hashes()
        save('semantic_holdout_results.json',dict(holdout_sha256=digest,references_unchanged=True,knowledge_unchanged_since_freeze=held['knowledge_hashes']==revision,
            evaluated_knowledge_hashes=revision,post_freeze_development_correction=held['knowledge_hashes']!=revision,
            rows=rows,grades=dict(Counter(r['grade'] for r in rows)),reviewer='Codex; pending explicit review of non-exact outputs'))
        print('Holdout',Counter(r['grade'] for r in rows),flush=True)
    finally:engine.shutdown()

if __name__=='__main__':freeze() if sys.argv[1]=='freeze' else evaluate()
