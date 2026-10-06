"""User-reviewed senses retain context boundaries and existing concept identity."""
import json
from pathlib import Path
from unittest.mock import Mock
import pytest

from app.engine.types import TranslationRequest
from app.glossary.bundled import bundled_paths
from app.glossary.engine import GlossaryEngine
from app.glossary.models import GlossaryEntry, TermMatch
from app.knowledge.profile import ContextProfile
from app.translation_memory.knowledge import TranslationKnowledgeEngine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def engine(tmp_path):
    router = Mock()
    router.policy.max_text_chars = 20000
    router.languages.resolve.return_value = ('zh', 'ru')
    memory = Mock()
    memory.lookup.return_value = None
    return TranslationKnowledgeEngine(router, memory,
        GlossaryEngine(tmp_path/'user.db', builtin_paths=bundled_paths()))


def request(text, branch):
    profile = ContextProfile('zh','ru','automotive',(('automotive',1.),),
                             (('automotive.'+branch,1.),),(),(),(),branch)
    return TranslationRequest(text,'zh','ru',domain='automotive',context_profile=profile)


@pytest.mark.parametrize('source,target', [
    ('活塞皮碗和润滑脂杯检查','Проверка поршневой манжеты и напорной манжеты'),
    ('润滑脂杯和活塞皮碗检查','Проверка напорной манжеты и поршневой манжеты'),
    ('润滑脂杯检查','Проверка напорной манжеты'),
    ('制动系统（抖动检查）','Тормозная система (проверка вибрации при торможении)'),
])
def test_known_inspection_headings_compose_without_model(engine, source, target):
    result = engine.lookup_direct(request(source,'brakes'))
    assert result and result.translated_text == target
    engine.router.translate.assert_not_called()
    engine.memory.remember.assert_not_called()


@pytest.mark.parametrize('source,branch', [
    ('活塞皮碗和未知杯检查','brakes'),
    ('润滑脂杯检查','engine'),
    ('制动系统（抖动检查）','suspension'),
    ('活塞皮碗和润滑脂杯检查。然后更换未知部件。','brakes'),
])
def test_unknown_tail_or_wrong_context_cannot_use_nominal_template(engine,source,branch):
    assert engine.lookup_direct(request(source,branch)) is None


def test_reference_typo_reuses_existing_under_cover_concept(engine):
    glossary = engine.glossary
    correct = glossary.lookup('发动机室底盖','zh','ru','automotive')[0]
    typo = glossary.lookup('发电机室底盖','zh','ru','automotive')[0]
    assert correct.entry.id == typo.entry.id
    assert json.loads(correct.entry.notes)['concept_id'] == 'aw087:e3725f72dfd6ab1feac3'
    result = engine.lookup_direct(request('（参考发动机机械系统-“发电机室底盖”）','electrical'))
    assert result.translated_text == 'См. раздел «механическая часть двигателя», подраздел «нижняя защита моторного отсека».'


def test_hvac_actuators_remain_three_separate_concepts(engine):
    results = []
    for source in ['进气促动器','模式促动器','自动除雾促动器']:
        item = engine.lookup_direct(request(source,'hvac'))
        assert item and 'привод заслонки' in item.translated_text
        results.append(item.translated_text)
    assert len(set(results)) == 3


@pytest.mark.parametrize('source,branch,hydraulic', [
    ('制动软管存在机油泄漏','brakes',True),
    ('制动总缸漏油','brakes',True),
    ('发动机存在机油泄漏','engine',False),
    ('制动真空泵机油泄漏','brakes',False),
    ('机油泄漏','brakes',False),
])
def test_brake_fluid_normalization_requires_hydraulic_component(engine,source,branch,hydraulic):
    prepared = engine.contextualize(request(source,branch))
    matches = engine.glossary.lookup(source,'zh','ru','automotive',
        snapshot=prepared.knowledge_snapshot,request=prepared)
    leakage = [m for m in matches if json.loads(m.entry.notes or '{}').get('semantic_key')=='brake_fluid_leakage']
    assert bool(leakage) == hydraulic


def test_unprofiled_lookup_and_cache_cannot_leak_context_sense(engine):
    assert not engine.glossary.lookup('润滑脂杯','zh','ru','automotive')
    assert engine.glossary.lookup('润滑脂杯','zh','ru','automotive',request=request('润滑脂杯','brakes'))
    assert not engine.glossary.lookup('润滑脂杯','zh','ru','automotive',request=request('润滑脂杯','engine'))


def test_context_restrictions_do_not_override_user_terminology():
    entry = GlossaryEntry('漏油','мой термин','zh','ru',notes=json.dumps(dict(required_subdomains=['brakes'])))
    match = TermMatch(0,2,entry,'user')
    assert GlossaryEngine.reviewed_context_matches('漏油',[match],request('漏油','engine')) == [match]


def test_cord_damage_does_not_invent_exposure(engine):
    result = engine.lookup_direct(request('绳线磨损','engine'))
    assert result and result.translated_text == 'повреждение нитей корда'
    assert 'огол' not in result.translated_text
