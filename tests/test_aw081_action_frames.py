"""Proven command roles and HIGH whole objects, independent of diagnostic text."""
from collections import Counter
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.engine.types import TranslationRequest, TranslationResult
from app.glossary.models import GlossaryEntry, TermMatch
from app.knowledge.objects import ObjectGuard
from app.knowledge.safety import action_records, russian_actions
from app.translation_memory.knowledge import TranslationKnowledgeEngine


def fixture(text, *, high=True, user=False, verified=True, role=None, ambiguous=False):
    meta=dict(review_status='VERIFIED' if verified else 'REVIEWED',concept_id='reserve-connector',type='compound')
    if role:
        meta['semantic_role']=role
    entry=GlossaryEntry('备用连接器','запасной разъём','zh','ru',trust=.9,status='REVIEWED',notes=json.dumps(meta))
    entries=[entry]
    if ambiguous:
        entries.append(replace(entry,target_term='иной разъём',notes=json.dumps(dict(meta,concept_id='other'))))
    def candidates(source,*args):
        return [TermMatch(source.index(e.source_term),source.index(e.source_term)+len(e.source_term),e,
                          'user' if user else 'builtin:test') for e in entries if e.source_term in source]
    rules=[dict(status='VERIFIED',shared_forms=True,source=surface+'{X}。',forms={'X':'accusative'},
                domain='automotive',subdomains=['electrical'],types=['PROCEDURE_STEP'],component_marker=True,
                allowed_slots=['备用连接器']) for surface in ('拆下','安装','检查','撬下')]
    context=SimpleNamespace(slot_forms={'备用连接器':dict(base='запасной разъём',nominative='запасной разъём',
        genitive='запасного разъёма',accusative='запасной разъём')},templates=rules,
        allow_bypass=lambda match,request:high,ranked=lambda matches,request:matches,metrics=Counter())
    snapshot=SimpleNamespace(candidates=candidates,signature='independent',entries=entries)
    profile=SimpleNamespace(primary_domain='automotive',subdomains=[('automotive.electrical',1)])
    request=TranslationRequest(text,'zh','ru',domain='automotive',segment_type='PROCEDURE_STEP',
        context_router=context,context_profile=profile,knowledge_snapshot=snapshot)
    engine=object.__new__(TranslationKnowledgeEngine)
    engine.context_router=context;engine.object_guard=ObjectGuard();engine.router=Mock();engine.glossary=None
    return engine,request


@pytest.mark.parametrize('source,semantic,target',[
    ('7. 拆下备用连接器(A)。','REMOVE','7. Снимите запасной разъём (A).'),
    ('安装备用连接器。','INSTALL','Установите запасной разъём.'),
    ('检查备用连接器。','CHECK','Проверьте запасной разъём.'),
    ('撬下备用连接器(B)。','PRY_REMOVE','Подденьте и снимите запасной разъём (B).'),
])
def test_reviewed_command_has_stable_source_id_complete_case_and_literal_marker(source,semantic,target):
    engine,request=fixture(source)
    assert engine._safe_action_object(request,with_semantics=True)==(target,semantic)


@pytest.mark.parametrize('target',['Запасной разъём (A).','Установите запасной разъём (A).','Разрежьте запасной разъём (A).'])
def test_missing_or_substituted_known_action_repairs_before_another_model_call(target):
    engine,request=fixture('拆下备用连接器(A)。')
    result=engine._ensure_safe(request,TranslationResult(target,'zh','ru','model','cpu',0,'',False,''))
    assert result.translated_text=='Снимите запасной разъём (A).'
    assert result.constraint_status=='semantic_action_object_repair:REMOVE'
    engine.router.translate.assert_not_called()


@pytest.mark.parametrize('options',[dict(high=False),dict(user=True),dict(verified=False),
    dict(ambiguous=True),dict(role='quantity'),dict(role='diagnostic_relation')])
def test_command_rendering_cannot_force_unproved_objects(options):
    engine,request=fixture('拆下备用连接器。',**options)
    assert engine._safe_action_object(request) is None


@pytest.mark.parametrize('source',['安装备用连接器时。','如果泄漏，拆下备用连接器。',
    '拆下备用连接器并剪断未知导线。','不要拆下备用连接器。'])
def test_unknown_tails_conditions_or_temporal_roles_are_not_a_simple_command(source):
    engine,request=fixture(source)
    assert engine._safe_action_object(request) is None


@pytest.mark.parametrize('kind',['HEADING','COMPONENT_LABEL','DIAGRAM_LABEL','TABLE_HEADER'])
def test_nominal_layout_role_is_not_rewritten_as_an_imperative(kind):
    engine,request=fixture('安装备用连接器。')
    assert engine._safe_action_object(replace(request,segment_type=kind)) is None


def test_complete_forms_and_existing_template_slot_scope_are_required():
    engine,request=fixture('拆下备用连接器。')
    del engine.context_router.slot_forms['备用连接器']['genitive']
    assert engine._safe_action_object(request) is None
    engine,request=fixture('拆下备用连接器。')
    for rule in engine.context_router.templates:
        rule['slot_allowed']={'X':['另一个部件']}
    assert engine._safe_action_object(request) is None
    engine,request=fixture('拆下备用连接器。')
    request=replace(request,context_profile=SimpleNamespace(primary_domain='automotive',subdomains=[('automotive.cooling',1)]))
    assert engine._safe_action_object(request) is None


@pytest.mark.parametrize('suffix',['','。','(B)。'])
def test_longer_known_component_with_an_action_prefix_keeps_its_nominal_meaning(suffix):
    engine,request=fixture('安装备用连接器'+suffix)
    entry=GlossaryEntry('安装备用连接器','монтажный запасной разъём','zh','ru',trust=.9,status='REVIEWED',
        notes=json.dumps(dict(review_status='VERIFIED',concept_id='mounting-connector',type='compound')))
    original=request.knowledge_snapshot.candidates
    def candidates(source,*args):
        extra=[TermMatch(0,len(entry.source_term),entry,'builtin:test')] if source.startswith(entry.source_term) else []
        return original(source,*args)+extra
    request.knowledge_snapshot.candidates=candidates
    assert engine._safe_action_object(request) is None


def test_frame_cannot_cross_language_or_missing_context():
    engine,request=fixture('拆下备用连接器。')
    for changed in [replace(request,target_language='en'),replace(request,source_language='en'),
                    replace(request,context_profile=None)]:
        assert engine._safe_action_object(changed) is None


@pytest.mark.parametrize('action',action_records(),ids=lambda action:action['semantic_id'])
def test_existing_verified_action_rendering_is_recognized(action):
    assert action['semantic_id'] in russian_actions(action['imperative']+' тестового механизма.')


def test_power_and_air_frames_own_their_verb_instead_of_a_shorter_removal():
    assert russian_actions('Снимите питание разъёма.')=={'REMOVE_POWER'}
    assert russian_actions('Удалите воздух из системы.')=={'REMOVE_AIR'}
    assert russian_actions('Проверьте разъём.')=={'CHECK','VERIFY'}  # Authored identical verb, not distinct surface proof.
