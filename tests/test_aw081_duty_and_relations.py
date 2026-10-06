"""Whole clauses, code invariants and unknown-tail rejection for review 03."""
from dataclasses import replace
from pathlib import Path
import json
from unittest.mock import Mock
import pytest
from app.engine.types import TranslationRequest
from app.glossary.bundled import bundled_paths
from app.glossary.engine import GlossaryEngine
from app.knowledge.profile import ContextProfile
from app.knowledge.references import breadcrumb
from app.translation_memory.knowledge import TranslationKnowledgeEngine

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def engine(tmp_path):
    router=Mock();router.policy.max_text_chars=20000
    router.languages.resolve.return_value=('zh','ru')
    memory=Mock();memory.lookup.return_value=None
    return TranslationKnowledgeEngine(router,memory,GlossaryEngine(tmp_path/'user.db',builtin_paths=bundled_paths()))

def request(text,branch,facts=(),kind='PROSE'):
    profile=ContextProfile('zh','ru','automotive',(('automotive',1.),),
        (('automotive.'+branch,1.),),(),(),(),branch+repr(facts),semantic_facts=facts)
    return TranslationRequest(text,'zh','ru',domain='automotive',context_profile=profile,segment_type=kind)

def test_mounting_reference_is_not_a_separate_edge(engine):
    source='安装时,首先箭头所示内侧部分（组装基点）接触车门框架,进行安装。'
    result=engine.lookup_direct(request(source,'body',('weatherstrip_mounting',),'PROCEDURE_STEP'))
    assert result.translated_text=='При установке сначала приложите к рамке двери внутренний участок уплотнителя, указанный стрелкой (базовую точку монтажа).'
    assert engine.lookup_direct(request(source,'body',kind='PROCEDURE_STEP')) is None
    engine.router.translate.assert_not_called()

def test_breadcrumb_preserves_engine_code_and_known_nodes(engine):
    source='2022 > G 1.4 T-GDI > 连接器形状 > 主线束 > 示意图'
    result=engine.lookup_direct(request(source,'electrical',kind='DIAGRAM_LABEL'))
    assert result.translated_text=='2022 > G 1.4 T-GDI > Вид разъёмов > основной жгут проводов > схема'
    assert 'распинов' not in result.translated_text
    engine.router.translate.assert_not_called()

@pytest.mark.parametrize('source',[
    '2022 > G 1.4 T-GDI > 未知标题 > 主线束 > 示意图',
    '2022 > > 主线束','2022 > 主线束。然后拆卸',
    '2022 > 未知标题',
])
def test_unknown_breadcrumb_node_or_prose_tail_backs_off(engine,source):
    assert engine.lookup_direct(request(source,'electrical',kind='DIAGRAM_LABEL')) is None

def test_fault_causes_retain_lexical_bad_condition_and_separate_damage(engine):
    source='电气系统内的很多故障可能是由线束和端子不良造成的。也可能是由其它电气系统的干涉、机械或化学损坏导致的。'
    result=engine.lookup_direct(request(source,'electrical',kind='PROCEDURE_STEP'))
    assert result.translated_text==('Многие неисправности электрической системы могут быть вызваны неисправностями жгута проводов и клемм. '
        'Неисправности также могут быть вызваны помехами от других электрических систем, а также механическими или химическими повреждениями.')
    assert engine.lookup_direct(request(source.replace('机械或化学损坏','未知原因'),'electrical')) is None
    assert engine.lookup_direct(request(source+'然后执行未知程序。','electrical')) is None
    engine.router.translate.assert_not_called()

def test_coordinated_egr_signal_and_load_clauses(engine):
    source='此阀门通过ECM的工作比控制信号来控制EGR（废气再循环）数量,而工作比控制信号取决于发动机载荷与进气需求。'
    result=engine.lookup_direct(request(source,'engine'))
    assert result and 'сигналу ECM с коэффициентом заполнения' in result.translated_text
    assert 'зависит от нагрузки двигателя и потребности во впускном воздухе' in result.translated_text
    assert 'ШИМ' not in result.translated_text
    assert result.translated_text.index('ECM')<result.translated_text.index('EGR')
    assert engine.lookup_direct(request(source.replace('进气需求','未知需求'),'engine')) is None
    engine.router.translate.assert_not_called()

def test_egr_purpose_preserves_oem_air_and_temperature(engine):
    source='废气再循环（EGR）系统用于将废气加入到进气中,以减少燃烧室的过量空气和降低温度。'
    result=engine.lookup_direct(request(source,'engine'))
    assert result and 'уменьшить избыток воздуха и снизить температуру в камере сгорания' in result.translated_text
    assert not any(word in result.translated_text for word in ('кислород','лямбда','коэффициент избытка'))
    engine.router.translate.assert_not_called()

def test_sensor_has_windshield_and_detects_moisture(engine):
    source='自动除湿传感器安装在前窗户玻璃上。如果出现湿气,传感器就会判断和发出信号来吹风除雾。'
    result=engine.lookup_direct(request(source,'hvac',('auto_defog_sensor',),'CONDITION'))
    assert result and 'на ветровом стекле' in result.translated_text
    assert 'определяет её наличие и передаёт сигнал' in result.translated_text
    assert 'прогноз' not in result.translated_text
    assert engine.lookup_direct(request(source,'hvac',kind='CONDITION')) is None
    engine.router.translate.assert_not_called()

LIST=['进气促动器','空调','自动除雾促动器','鼓风电动机转速','模式促动器']

@pytest.mark.parametrize('items',[LIST,LIST[::-1],LIST[:2]])
def test_known_control_list_preserves_order_and_distinct_actuators(engine,items):
    source='空调控制模块接收传感器的信号,通过控制'+'、'.join(items[:-1])+'和'+items[-1]+'来抑制湿气和除雾。'
    result=engine.lookup_direct(request(source,'hvac'))
    assert result
    forms=engine.context_router.slot_forms
    controls=result.translated_text.split('управляя ',1)[1]
    positions=[controls.index(forms[item]['instrumental']) for item in items]
    assert positions==sorted(positions)
    engine.router.translate.assert_not_called()

@pytest.mark.parametrize('items',[
    ['进气促动器','未知促动器'],LIST+['空调','进气促动器'],['进气促动器'],['进气促动器','','空调'],
])
def test_control_list_requires_every_whole_known_member_and_bound(engine,items):
    source='空调控制模块接收传感器的信号,通过控制'+'、'.join(items)+'来抑制湿气和除雾。'
    assert engine.lookup_direct(request(source,'hvac')) is None

@pytest.mark.parametrize('case,branch,facts',[('6:1','engine',()),('15:1','hvac',('auto_defog_sensor',))])
def test_actual_native_block_keeps_heading_and_wraps_without_missing_tail(engine,case,branch,facts):
    records=json.loads((ROOT/'qa/aw081/major_root_causes.json').read_text('utf8'))['rows']
    source=next(row for row in records if row['id']==case)['native_layout_matches'][0]['text']
    result=engine.lookup_direct(request(source,branch,facts,'CONDITION' if branch=='hvac' else 'PROSE'))
    assert result and result.translated_text.startswith('Описание\n')
    assert not any('\u4e00'<=c<='\u9fff' for c in result.translated_text)
    assert engine.lookup_direct(request(source.rstrip('。'),branch,facts,'PROSE')) is None
    engine.router.translate.assert_not_called()

def test_raw_broken_line_cannot_borrow_document_continuation(engine):
    assert engine.lookup_direct(request('号,通过控制进气促动器、空调、自动除雾促动器来抑制湿气和除雾。','hvac',('auto_defog_sensor',))) is None


def test_lexical_fault_is_not_a_lost_prohibition():
    from app.knowledge.relations import negative_relation
    assert negative_relation('连接不良','неисправность соединения')
    assert not negative_relation('连接不良','исправное соединение')
    assert not negative_relation('不要安装不良连接器','Установите неисправный разъём')
    assert negative_relation('不要安装不良连接器','Не устанавливайте неисправный разъём')
    assert not negative_relation('不要安装连接器','Установите разъём')


def test_camera_activation_requires_all_literal_states(engine):
    source='点火开关ON,变速杆挂到R档,倒车灯亮时,后视摄像头启动。'
    result=engine.lookup_direct(request(source,'adas'))
    assert result.translated_text=='Камера заднего вида включается, когда замок зажигания находится в положении ON, рычаг переключения передач — в положении R и горит фонарь заднего хода.'
    for changed in (source.replace('ON','OFF'),source.replace('R档','D档'),source.replace('灯亮','灯灭')):
        assert engine.lookup_direct(request(changed,'adas')) is None
    engine.router.translate.assert_not_called()


def test_component_procedure_header_has_column_roles(engine):
    result=engine.lookup_direct(request('部件 程序','brakes',kind='DIAGRAM_LABEL'))
    assert result.translated_text=='Компонент — процедура'
    assert engine.lookup_direct(request('部件 程序','electrical',kind='DIAGRAM_LABEL')) is None
    assert engine.lookup_direct(request('部件 未知程序','brakes',kind='DIAGRAM_LABEL')) is None
    assert engine.lookup_direct(request('部件程序','brakes',kind='DIAGRAM_LABEL')) is None


def test_short_ac_label_does_not_replace_a_control_unit_fragment(engine):
    req=engine.contextualize(request('根据加热器与空调控制单元的电信号,改变旋转斜盘的角度。','hvac'))
    matches=engine.glossary.lookup(req.text,'zh','ru','automotive',snapshot=req.knowledge_snapshot,request=req)
    safe=engine.glossary.sentence_safe_matches(req.text,matches)
    assert not any(m.entry.source_term=='空调' for m in safe)
    assert engine.lookup_direct(request('空调','hvac',kind='DIAGRAM_LABEL')).translated_text=='кондиционер'
