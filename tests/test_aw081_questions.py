"""Independent question predicates, known noun slots and fail-closed routes."""
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.engine.types import TranslationRequest, TranslationResult
from app.glossary.models import GlossaryEntry, TermMatch
from app.knowledge.questions import compose, features, violations


def known_request(text, *, ambiguous=False, user=False, high=True):
    nouns = {'备用连接器':('запасной разъём','запасного разъёма','запасной разъём'),
             '信号异常':('аномалия сигнала','аномалии сигнала','аномалию сигнала')}
    forms = {s:dict(base=nom,nominative=nom,genitive=gen,accusative=acc)
             for s,(nom,gen,acc) in nouns.items()}
    entries = [GlossaryEntry(s,t[0],'zh','ru',trust=.9,status='REVIEWED',notes=json.dumps(
        dict(concept_id=s,review_status='VERIFIED',type='compound'))) for s,t in nouns.items()]
    if ambiguous:
        entries.append(replace(entries[0],target_term='другой разъём',notes=json.dumps(
            dict(concept_id='other',review_status='VERIFIED',type='compound'))))
    def candidates(source,*args):
        return [TermMatch(0,len(source),e,'user' if user else 'builtin:test')
                for e in entries if e.source_term==source]
    context = SimpleNamespace(allow_bypass=lambda match,request:high)
    return TranslationRequest(text,'zh','ru',domain='automotive',context_router=context,
        knowledge_snapshot=SimpleNamespace(candidates=candidates)),forms


@pytest.mark.parametrize('source,target,kind',[
    ('找到备用连接器了吗？','Удалось ли найти запасной разъём?','YES_NO'),
    ('7. 发现信号异常了吗?','7. Удалось ли найти аномалию сигнала?','FAULT_CHECK'),
])
def test_complete_finding_question_keeps_completed_predicate_and_case(source,target,kind):
    request,forms=known_request(source)
    assert compose(request,forms)==(target,kind)
    assert not violations(source,target)


@pytest.mark.parametrize('source,kind',[
    ('备用设备是否正常？','STATE_CHECK'),
    ('备用设备不正常吗？','STATE_CHECK'),
    ('电阻是多少？','VALUE_CHECK'),
    ('测试电压是否正常？','VALUE_CHECK'),
    ('备用连接器在这里吗？','YES_NO'),
])
def test_semantic_question_kind_is_more_than_punctuation(source,kind):
    assert features(source).kind==kind


@pytest.mark.parametrize('source',['备用连接器？','什么时候维修？','检查是否正常。','找到备用连接器了吗？然后拆下盖。',
                                 '找到连接器。设备正常了吗？'])
def test_unproved_or_nonwhole_question_is_not_a_closed_frame(source):
    assert features(source) is None
    request,forms=known_request(source)
    assert compose(request,forms) is None


@pytest.mark.parametrize('target,reason',[
    ('Есть ли аномалия сигнала?','question:found_relation'),
    ('Аномалия сигнала найдена.','question:lost'),
    ('Удалось ли найти новый разъём?','question:fault_meaning'),
])
def test_finding_cannot_become_existence_declaration_or_unrelated_object(target,reason):
    assert reason in violations('发现信号异常了吗？',target)


def test_normal_question_cannot_lose_its_predicate():
    assert 'question:normal_predicate' in violations('备用设备是否正常？','Есть ли запасное устройство?')
    assert not violations('备用设备是否正常？','Исправно ли запасное устройство?')
    assert features('正常条件下需要更换吗？').predicate==''
    assert features('电压正常，备用设备需要更换吗？') is None


@pytest.mark.parametrize('options',[dict(ambiguous=True),dict(user=True),dict(high=False)])
def test_question_requires_unique_high_whole_concept_and_respects_user(options):
    request,forms=known_request('找到备用连接器了吗？',**options)
    assert compose(request,forms) is None


def test_missing_case_unknown_object_and_other_language_back_off():
    request,forms=known_request('找到备用连接器了吗？')
    del forms['备用连接器']['genitive']
    assert compose(request,forms) is None
    request,forms=known_request('找到未知连接器了吗？')
    assert compose(request,forms) is None
    request,forms=known_request('找到备用连接器了吗？')
    assert compose(replace(request,target_language='en'),forms) is None
    assert compose(replace(request,context_router=None),forms) is None


def test_diagnostic_relation_is_not_a_physical_object_for_substitution_guard():
    from app.knowledge.objects import ObjectGuard
    entry=GlossaryEntry('故障部位','место неисправности','zh','ru',trust=.9,status='REVIEWED',notes=json.dumps(
        dict(concept_id='fault-location',review_status='VERIFIED',type='compound',semantic_role='diagnostic_relation')))
    snapshot=SimpleNamespace(signature='diagnostic-only',entries=[entry])
    forms={'故障部位':dict(base='место неисправности',nominative='место неисправности',
                        genitive='места неисправности',accusative='место неисправности')}
    assert ObjectGuard().index(snapshot,forms)[0]=={}


def test_unsafe_tm_finding_question_is_rejected_by_shared_boundary(tmp_path):
    from app.glossary.engine import GlossaryEngine
    from app.translation_memory.knowledge import TranslationKnowledgeEngine
    router=Mock()
    router.policy.max_text_chars=20000
    router.languages.resolve.return_value=('zh','ru')
    router.translate.return_value=TranslationResult('Есть ли тестовая неисправность?','zh','ru','fake','cpu',0,'',False,'')
    memory=Mock()
    memory.lookup.return_value=SimpleNamespace(reusable=True,target='Есть ли тестовая неисправность?',match_type='exact',translation_unit_id=1)
    engine=TranslationKnowledgeEngine(router,memory,GlossaryEngine(tmp_path/'terms.db'))
    result=engine.translate(TranslationRequest('找到测试故障了吗？','zh','ru',domain='automotive'))
    assert result.translated_text=='找到测试故障了吗？'
    assert result.constraint_status.startswith('semantic_source_preserved:')
    assert result.question_kind=='FAULT_CHECK'
