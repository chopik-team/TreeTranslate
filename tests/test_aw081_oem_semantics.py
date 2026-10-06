"""OEM source corrections require explicit evidence and retain literal atoms."""
from dataclasses import replace
import json
from unittest.mock import Mock
import pytest

from app.engine.types import TranslationRequest
from app.glossary.bundled import bundled_paths
from app.glossary.engine import GlossaryEngine
from app.glossary.constraints import validate_result, units
from app.glossary.errors import ConstraintFailure
from app.knowledge.profile import ContextProfile, DocumentProfiler
from app.knowledge.units import reviewed_context_measurement
from app.translation_memory.knowledge import TranslationKnowledgeEngine


@pytest.fixture
def engine(tmp_path):
    router=Mock()
    router.policy.max_text_chars=20000
    router.languages.resolve.return_value=('zh','ru')
    memory=Mock()
    memory.lookup.return_value=None
    return TranslationKnowledgeEngine(router,memory,
        GlossaryEngine(tmp_path/'user.db',builtin_paths=bundled_paths()))


def request(text,branch='engine',facts=(),kind='PROSE'):
    profile=ContextProfile('zh','ru','automotive',(('automotive',1.),),
        (('automotive.'+branch,1.),),(),(),(),branch+repr(facts),semantic_facts=facts)
    return TranslationRequest(text,'zh','ru',domain='automotive',context_profile=profile,segment_type=kind)


@pytest.mark.parametrize('source,target',[
    ('从灯总成上拆卸灯泡插座(A)和转向信号灯灯泡(B)。',
     'Снимите патрон лампы (A) и лампу указателя поворота (B) с указателя поворота в сборе.'),
    ('从转向信号灯总成上拆卸转向信号灯灯泡(C)和灯泡插座(D)。',
     'Снимите лампу указателя поворота (C) и патрон лампы (D) с указателя поворота в сборе.'),
])
def test_remove_two_components_preserves_roles_and_markers(engine,source,target):
    result=engine.lookup_direct(request(source,'electrical',kind='PROCEDURE_STEP'))
    assert result and result.translated_text==target
    engine.router.translate.assert_not_called()


def test_generic_lamp_assembly_requires_turn_signal_anchor(engine):
    req=engine.contextualize(request('灯总成','electrical',kind='COMPONENT_LABEL'))
    assert not engine.glossary.lookup(req.text,'zh','ru','automotive',snapshot=req.knowledge_snapshot,request=req)
    assert engine.lookup_direct(request('从灯总成上拆卸灯泡插座(A)和未知灯泡(B)。','electrical',kind='PROCEDURE_STEP')) is None


def test_compressor_location_and_belt_are_contextual(engine):
    text='位于机体侧,由发动机的三角皮带驱动。'
    result=engine.lookup_direct(request(text,facts=('ac_compressor',)))
    assert result.translated_text=='Расположен сбоку блока цилиндров и приводится в действие клиновым ремнём двигателя.'
    assert engine.lookup_direct(request(text)) is None
    v=engine.lookup_direct(request('三角皮带',kind='COMPONENT_LABEL'))
    assert v.translated_text=='клиновой ремень'
    assert 'поликлин' not in v.translated_text


def test_visual_inspection_compares_wear_and_cords(engine):
    result=engine.lookup_direct(request('目视检查皮带是否过度磨损、绳线磨损等。'))
    assert result.translated_text=='Визуально проверьте ремень на чрезмерный износ и повреждение нитей корда.'
    assert engine.lookup_direct(request('目视检查皮带是否过度磨损、未知损伤等。')) is None


def test_rib_cracks_and_replacement_condition(engine):
    source='皮带侧面的裂纹被认为是可接受的。如果皮带的肋部缺少大块,则应更换。'
    result=engine.lookup_direct(request(source,facts=('drive_belt_inspection',)))
    assert result.translated_text=='Трещины на ребристой стороне ремня считаются допустимыми. Если отсутствуют крупные участки рёбер ремня, ремень следует заменить.'
    assert engine.lookup_direct(request(source)) is None
    assert engine.lookup_direct(request(source,facts=('drive_belt_inspection',),kind='CONDITION')).translated_text==result.translated_text


def test_new_assembly_keeps_existing_install_command(engine):
    result=engine.lookup_direct(request('安装转向信号灯总成。','electrical',kind='PROCEDURE_STEP'))
    assert result.translated_text=='Установите указатель поворота в сборе.'
    engine.router.translate.assert_not_called()


@pytest.mark.parametrize('source,target',[
    ('蒸发气泄漏测试','Проверка герметичности системы EVAP'),
    ('蒸发器系统泄漏测试','Проверка утечек системы улавливания паров топлива'),
    ('GPF服务生成','Сервисная регенерация GPF'),
])
def test_exact_oem_menu_labels(engine,source,target):
    result=engine.lookup_direct(request(source,'cooling',kind='TABLE_CELL'))
    assert result.translated_text==target
    assert engine.lookup_direct(request(source,'hvac',kind='TABLE_CELL')) is None
    engine.router.translate.assert_not_called()


def test_distinct_menu_concepts_and_no_prose_fragment(engine):
    req=engine.contextualize(request('蒸发气泄漏测试','cooling',kind='TABLE_CELL'))
    first=engine.glossary.lookup(req.text,'zh','ru','automotive',snapshot=req.knowledge_snapshot,request=req)[0]
    req=replace(req,text='蒸发器系统泄漏测试')
    second=engine.glossary.lookup(req.text,'zh','ru','automotive',snapshot=req.knowledge_snapshot,request=req)[0]
    assert json.loads(first.entry.notes)['concept_id']!=json.loads(second.entry.notes)['concept_id']
    assert engine.lookup_direct(replace(req,text='请执行蒸发器系统泄漏测试并检查未知部件。',segment_type='PROSE')) is None
    with pytest.raises(ConstraintFailure):
        validate_result('蒸发气泄漏测试','Проверка герметичности системы EVAP')


@pytest.mark.parametrize('source',[
    '（请参阅发动机和驱动桥总成-“机舱被掩盖“）',
    '（请参阅发动机和驱动桥总成-“机舱被掩盖',
])
def test_reviewed_reference_alias_and_missing_final_punctuation(engine,source):
    result=engine.lookup_direct(request(source,'cooling',kind='CROSS_REFERENCE'))
    assert result.translated_text=='См. раздел «двигатель и коробка передач в сборе», подраздел «нижняя защита моторного отсека».'
    known=engine.glossary.lookup('发动机室底盖','zh','ru','automotive')[0]
    assert json.loads(known.entry.notes)['concept_id']=='aw087:e3725f72dfd6ab1feac3'
    assert not engine.glossary.lookup('机舱被掩盖','zh','ru','automotive')


@pytest.mark.parametrize('title',['未知盖','机舱被掩盖然后拆卸','发动机室底盖'])
def test_unapproved_truncated_titles_are_preserved(engine,title):
    source='（请参阅发动机和驱动桥总成-“'+title
    assert engine.lookup_direct(request(source,'cooling',kind='CROSS_REFERENCE')).translated_text==source


@pytest.mark.parametrize('code,label,target',[('D','之前','первичный'),('E','秒','вторичный')])
@pytest.mark.parametrize('value,tolerance',[('44','5'),('37','5'),('51.5','2.5')])
def test_reservoir_captions_inherit_cc_and_keep_arbitrary_values(engine,code,label,target,value,tolerance):
    profile=DocumentProfiler().profile('zh','ru',segments=['DOT 4','储液器容量（cc）'])
    req=TranslationRequest(f'{code} {label}：{value} ± {tolerance}','zh','ru',context_profile=profile,segment_type='TABLE_CELL')
    assert profile.primary_domain=='general'
    result=engine.lookup_direct(req)
    assert result.translated_text==f'{code} — {target}: {value} ± {tolerance} см³'
    engine.router.translate.assert_not_called()


@pytest.mark.parametrize('header',[
    ['DOT 4'],['储液器容量（cc）'],['DOT 4','储液器容量（ml）'],['DOT 4','发动机容量（cc）'],
])
def test_unit_requires_matching_header_and_brake_fluid_type(header):
    profile=DocumentProfiler().profile('zh','ru',segments=header)
    assert reviewed_context_measurement(TranslationRequest('D 之前：44 ± 5','zh','ru',context_profile=profile)) is None


@pytest.mark.parametrize('source',['F 秒：37 ± 5','D 秒：44 ± 5','E 之前：37 ± 5','D 之前：44 ± 5 ml','D 之前：44 ± 5 然后检查'])
def test_unknown_caption_code_or_extra_tail_is_not_repaired(source):
    assert reviewed_context_measurement(request(source,facts=('brake_reservoir_cc',))) is None


def test_cc_is_volume_and_default_units_stay_strict():
    assert units('44 ± 5 cc')==units('44 ± 5 см³')==('cc',)
    with pytest.raises(ConstraintFailure):
        validate_result('44 ± 5','44 ± 5 см³')
    with pytest.raises(ConstraintFailure):
        validate_result('44 ± 5 cc','44 ± 5 см')
    with pytest.raises(ConstraintFailure):
        validate_result('44 ± 5 cc','44 ± 6 см³')


def test_washer_reuses_existing_plain_concept(engine):
    result=engine.lookup_direct(request('垫圈','common',kind='COMPONENT_LABEL'))
    assert result.translated_text=='шайба'
