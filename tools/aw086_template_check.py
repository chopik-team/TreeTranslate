"""Actual safe-template paths with the real curated glossary, no inference."""
import json
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.engine.types import TranslationRequest,TranslationResult
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.knowledge import TranslationKnowledgeEngine

router=Mock();router.languages.resolve.return_value=('zh','ru');router.policy.max_text_chars=20000
router.translate.return_value=TranslationResult('fallback','zh','ru','m2m100','cpu',0,'qa',False,'')
qa=ROOT/'qa/aw086'
engine=TranslationKnowledgeEngine(router,Mock(lookup=Mock(return_value=None)),GlossaryEngine(qa/'template-isolated-user.db',builtin_paths=bundled_paths()))
p=engine.profile_document('zh','ru',segments=['车身维修 车门内板 面板间隙 测量点 探头长度 卷尺 冷却液 散热器 冷却风扇 发动机 机油'])
sources=[
    '请检查车门内板和外板是否变形。','如果探头长度可以调整。','检查探头,确保无自由间隙。',
    '通过散热器盖缓慢添加冷却液和水 （45－60％） 混合物。',
    '• 绝不能在发动机热的时候拆除散热器盖。 热流体在高压作用下从散热器喷出,可能会导致严重烫伤。',
    '• 保持发动机空转。','拧下排放螺塞,并排放冷却水。','排放冷却水后,牢固拧紧散热器排放螺塞。']
rows=[]
for source in sources:
    started=perf_counter()
    r=engine.translate(TranslationRequest(source,'zh','ru',context_profile=p,segment_type='PROCEDURE_STEP' if source.startswith(('通过','拧下','排放')) else ''))
    rows.append(dict(source=source,output=r.translated_text,rule=r.route_reason,passed=r.knowledge_source=='template',seconds=perf_counter()-started))
assert all(r['passed'] for r in rows)
invalid=['请检查未知部件和外板是否变形。','前缀请检查车门内板和外板是否变形。','请检查车门内板和外板是否变形。另外检查。','甲乙'*260]
fallback=[]
for source in invalid:
    started=perf_counter();r=engine.translate(TranslationRequest(source,'zh','ru',context_profile=p))
    fallback.append(dict(source_length=len(source),backend=r.backend,passed=r.backend=='m2m100',seconds=perf_counter()-started))
assert all(r['passed'] for r in fallback)
engine.context_router.templates.append(dict(engine.context_router.templates[0]))
result=engine.translate(TranslationRequest(sources[0],'zh','ru',context_profile=p))
assert result.backend=='m2m100'
(qa/'template_results.json').write_text(json.dumps(dict(rows=rows,fallbacks=fallback,ambiguous_pattern_falls_back=True,
    max_input_chars=512,max_slot_chars=128,max_slots=3,network_used=False),ensure_ascii=False,indent=2)+'\n','utf-8')
print('TEMPLATES',len(rows),'PASS; fallbacks',len(fallback),'PASS; ambiguous PASS',flush=True)
