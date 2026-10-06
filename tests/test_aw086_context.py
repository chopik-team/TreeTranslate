"""Context integration contracts without model weights or network access."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.knowledge.profile import DocumentProfiler
from app.knowledge.segments import SegmentClassifier,SegmentType
from app.knowledge.router import KnowledgeRouter
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from app.engine.types import TranslationRequest,TranslationResult


@pytest.fixture
def engine(tmp_path):
    router=Mock();router.policy.max_text_chars=20000;router.languages.resolve.return_value=('zh','ru')
    router.translate.return_value=TranslationResult('fallback','zh','ru','m2m100','cpu',0,'qa',False,'')
    memory=Mock();memory.lookup.return_value=None
    return TranslationKnowledgeEngine(router,memory,GlossaryEngine(tmp_path/'user.db',builtin_paths=bundled_paths()))


def profile(engine,*texts):return engine.profile_document('zh','ru',segments=texts,identity='qa')


def test_content_override_and_mixed(engine):
    parent=engine.profile_document('zh','ru',segments=['车身维修 车身尺寸 前门 铰链 投影尺寸 测量点'])
    child=engine.profile_document('zh','ru',segments=['熔断器 电压 线束 接地 连接器'],parent=parent,filename='车身维修.pdf')
    assert child.primary_domain=='automotive'
    assert dict(child.subdomains)['automotive.electrical']>.8
    assert dict(child.subdomains).get('automotive.body.body_repair',0)<.5
    mixed=profile(engine,'冷却液 散热器 冷却风扇','熔断器 电压 线束')
    assert {'automotive.cooling','automotive.electrical'}<=set(dict(mixed.subdomains))
    inherited=engine.profile_document('zh','ru',parent=parent,filename='内部.pdf')
    assert inherited.primary_domain=='automotive'


def test_ambiguous_general_cache_and_failure(engine):
    weak=profile(engine,'今天的故事提到一个散热器。')
    assert weak.primary_domain=='general'
    assert dict(weak.domains)['automotive']<.6
    assert profile(engine,'今天的故事提到一个散热器。') is weak
    assert engine.context_router.profiler.cache_hits==1
    engine.context_router.profiler.profile=Mock(side_effect=ValueError())
    assert engine.profile_document('zh','ru').primary_domain=='general'


@pytest.mark.parametrize('text,hint,region,expected',[
    ('维修手册','','title','TITLE'),('一般方法','','heading','HEADING'),
    ('概述','','','HEADING'),('这是一个完整的说明句子。','','','PROSE'),
    ('1. 检查液位。','','','PROCEDURE_STEP'),('绝不能拆除散热器盖。','','','WARNING'),
    ('如果长度可以调整。','','','CONDITION'),('参数','','table_header','TABLE_HEADER'),
    ('数值','','table_cell','TABLE_CELL'),('左侧','','','DIAGRAM_LABEL'),
    ('前门上铰链安装孔','','','COMPONENT_LABEL'),('Ø13','','','MEASUREMENT'),
    ('GDS','','','IDENTIFIER'),('冷却液.pdf','FILENAME','','FILENAME')])
def test_segment_types(text,hint,region,expected):
    assert SegmentClassifier.classify(text,hint=hint,segment=SimpleNamespace(region_kind=region)).value==expected


def test_context_snapshot_selection_cache_concepts_and_longest(engine):
    body=profile(engine,'车身尺寸 测量点 投影尺寸 前门 上铰链')
    s=engine.context_router.snapshot(body)
    assert s is engine.context_router.snapshot(body)
    assert s.concepts and s.stores
    assert '冷却液' not in {e.source_term for e in s.entries}
    r=engine.translate(TranslationRequest('前门上铰链安装孔','zh','ru',context_profile=body))
    assert r.translated_text=='Отверстие крепления верхней петли передней двери'
    engine.router.translate.assert_not_called()
    cooling=profile(engine,'冷却液 散热器 冷却风扇 GDS 故障码')
    cs=engine.context_router.snapshot(cooling)
    assert {'冷却液','故障码'}<={e.source_term for e in cs.entries}
    assert '前门上铰链安装孔' not in {e.source_term for e in cs.entries}
    assert engine.lookup_direct(TranslationRequest('内部','zh','ru',context_profile=cooling)) is None
    assert engine.lookup_direct(TranslationRequest('减震器','zh','ru',context_profile=cooling)) is None
    assert s.signature!=cs.signature
    assert engine.context_router.snapshot(replace(body,version='future')).signature!=s.signature
    engine.context_router.clear();assert not engine.context_router.cache


def test_parent_body_family_includes_unsampled_child_concept(engine):
    p=profile(engine,'车身结构 车身 车门')
    assert 'automotive.body' in dict(p.subdomains)
    r=engine.lookup_direct(TranslationRequest('前门上铰链安装孔','zh','ru',context_profile=p))
    assert r and r.backend=='glossary'
    child=profile(engine,'前门 后门 铰链 纵梁')
    r=engine.lookup_direct(TranslationRequest('内部A','zh','ru',context_profile=child,segment_type='HEADING'))
    assert r and r.translated_text=='Внутренняя часть кузова A'
    r=engine.lookup_direct(TranslationRequest('前车身A','zh','ru',context_profile=child,segment_type='HEADING'))
    assert r and r.translated_text=='Передняя часть кузова A'


def test_template_structure_negation_unknown_slots_and_priorities(engine):
    p=profile(engine,'车身维修 车门内板 外板 面板间隙')
    request=TranslationRequest('请检查车门内板和外板是否变形。','zh','ru',context_profile=p)
    assert 'не деформированы' in engine.translate(request).translated_text
    engine.router.translate.assert_not_called()
    assert engine.translate(replace(request,text='请检查新型面板和外板是否变形。')).backend=='m2m100'
    assert engine.translate(replace(request,text=request.text+'另外安装。')).backend=='m2m100'
    engine.glossary.remember_term(request.text,'user exact','zh','ru','automotive')
    assert engine.translate(request).translated_text=='user exact'
    engine.memory.lookup.return_value=Mock(reusable=True,target='TM exact',match_type='exact',translation_unit_id=1)
    assert engine.translate(request).translated_text=='TM exact'


def test_spread_sample_and_bound(engine):
    texts=['一般文字。']*100
    texts[0]='冷却液 散热器';texts[52]='熔断器 电压';texts[-1]='线束 接地'
    p=profile(engine,*texts)
    assert p.primary_domain=='automotive'
    assert 'automotive.cooling' in dict(p.subdomains)
    assert 'automotive.electrical' in dict(p.subdomains)


def test_cooling_templates_protect_numbers_negation_and_idle(engine):
    p=profile(engine,'冷却液 散热器 冷却风扇 发动机 机油')
    text='通过散热器盖缓慢添加冷却液和水 （45－60％） 混合物。'
    r=engine.translate(TranslationRequest(text,'zh','ru',context_profile=p,segment_type='PROCEDURE_STEP'))
    assert r.knowledge_source=='template'
    assert '45－60％' in r.translated_text and 'крышку радиатора' in r.translated_text
    warning='• 绝不能在发动机热的时候拆除散热器盖。 热流体在高压作用下从散热器喷出,可能会导致严重烫伤。'
    r=engine.translate(TranslationRequest(warning,'zh','ru',context_profile=p))
    assert r.knowledge_source=='template' and 'Не снимайте' in r.translated_text and 'тяжёлые ожоги' in r.translated_text
    r=engine.translate(TranslationRequest('• 保持发动机空转。','zh','ru',context_profile=p))
    assert r.knowledge_source=='template' and 'холостом ходу' in r.translated_text
    for text in ('拧下排放螺塞,并排放冷却水。','排放冷却水后,牢固拧紧散热器排放螺塞。'):
        r=engine.translate(TranslationRequest(text,'zh','ru',context_profile=p,segment_type='PROCEDURE_STEP'))
        assert r.knowledge_source=='template' and 'сливную пробку' in r.translated_text


def test_offline_immutable_snapshot_legacy_and_failure(engine,monkeypatch):
    import socket
    def fail(*args,**kwargs):raise AssertionError('network forbidden')
    monkeypatch.setattr(socket.socket,'connect',fail)
    p=profile(engine,'冷却液 散热器 线束 电压')
    s=engine.context_router.snapshot(p)
    with pytest.raises(TypeError):s.exact['bad']=()
    assert engine.lookup_direct(TranslationRequest('冷却液','zh','ru',context_profile=p)) is not None
    engine.context_router._snapshot=Mock(side_effect=RuntimeError())
    assert engine.context_router.snapshot(p) is None
    engine.translate(TranslationRequest('未知文句。','zh','ru',context_profile=p))
    assert engine.router.translate.called
