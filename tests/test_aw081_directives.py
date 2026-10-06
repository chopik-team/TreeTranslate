"""Independent clauses and rejection boundaries, not diagnostic sentences."""
import json
from types import SimpleNamespace
import pytest
from app.engine.types import TranslationRequest
from app.glossary.models import GlossaryEntry, TermMatch
from app.knowledge.directives import compose
from app.knowledge.safety import violations


def request(text, *, ambiguous=False):
    nouns = {'扭矩扳手': 'динамометрический ключ', '水泵': 'водяной насос',
             '螺栓': 'болт', '连接器': 'разъём'}
    forms = {source: dict(base=target, accusative=target) for source,target in nouns.items()}
    entries = [GlossaryEntry(s,t,'zh','ru',trust=.9,status='REVIEWED',
        notes=json.dumps(dict(review_status='VERIFIED', concept_id=s))) for s,t in nouns.items()]
    if ambiguous:
        entries.append(GlossaryEntry('水泵','другой насос','zh','ru',trust=.9,status='REVIEWED',
            notes=json.dumps(dict(review_status='VERIFIED',concept_id='other'))))
    def candidates(text,*args):
        return [TermMatch(0,len(text),e) for e in entries if e.source_term==text]
    snapshot = SimpleNamespace(candidates=candidates)
    return TranslationRequest(text,'zh','ru',domain='automotive',knowledge_snapshot=snapshot), forms


def test_complete_independent_sequence_keeps_tools_directions_markers():
    req, forms = request('使用扭矩扳手，逆时针转动螺栓（C）以松开。然后断开连接器(D)。')
    result = compose(req,forms)
    assert result and result[0] == ('Используйте динамометрический ключ. '
        'Поверните болт （C） против часовой стрелки, чтобы ослабить. Затем отсоедините разъём (D).')
    assert not violations(req.text,result[0])


@pytest.mark.parametrize('text', [
    '拆下水泵。然后检查未知零件。',
    '如果水泵泄漏，拆下水泵。',
    '不要拆下水泵。然后检查螺栓。',
    '顺时针拆下水泵。',
    '转动螺栓来损坏。',
    '使用水泵。',
    '拆下水泵。然后拧紧螺栓至25Nm。',
])
def test_unknown_or_unhandled_clause_cannot_partially_translate(text):
    req, forms = request(text)
    assert compose(req,forms) is None


def test_equal_object_senses_back_off():
    req, forms = request('拆下水泵。然后拧紧螺栓。',ambiguous=True)
    assert compose(req,forms) is None


def assembly_request(text, *, ambiguous=False, whole=False, quantity=False, user=False):
    forms = {'燃油泵':dict(base='топливный насос',nominative='топливный насос',
                          genitive='топливного насоса',accusative='топливный насос',assembly_allowed=True)}
    metadata = dict(review_status='VERIFIED',concept_id='fuel-pump',type='compound')
    if quantity:
        metadata['semantic_role']='quantity'
    entries=[GlossaryEntry('燃油泵','топливный насос','zh','ru',trust=.9,status='REVIEWED',notes=json.dumps(metadata))]
    if ambiguous:
        entries.append(GlossaryEntry('燃油泵','иной насос','zh','ru',trust=.9,status='REVIEWED',
            notes=json.dumps(dict(metadata,concept_id='other-pump'))))
    if whole:
        entries.append(GlossaryEntry('燃油泵总成','модуль подачи топлива','zh','ru',trust=.9,status='REVIEWED',
            notes=json.dumps(dict(metadata,concept_id='fuel-module'))))
    def candidates(source,*args):
        return [TermMatch(0,len(source),entry,'user' if user else 'builtin:test')
                for entry in entries if entry.source_term==source]
    context_router=SimpleNamespace(ranked=lambda matches,request:matches,
                                   allow_bypass=lambda match,request:True)
    return TranslationRequest(text,'zh','ru',domain='automotive',context_router=context_router,
                              knowledge_snapshot=SimpleNamespace(candidates=candidates)),forms


def test_complete_assembly_keeps_action_case_and_marker():
    req,forms=assembly_request('安装燃油泵总成（K）。')
    assert compose(req,forms)[0]=='Установите топливный насос в сборе （K）.'
    req,forms=assembly_request('拆下燃油泵总成。')
    assert compose(req,forms)[0]=='Снимите топливный насос в сборе.'


@pytest.mark.parametrize('options',[dict(ambiguous=True),dict(whole=True),dict(quantity=True),dict(user=True)])
def test_assembly_cannot_override_whole_concept_ambiguity_quantity_or_user(options):
    req,forms=assembly_request('拆下燃油泵总成。',**options)
    assert compose(req,forms) is None


@pytest.mark.parametrize('text',['拆下燃油泵总成总成。','拆下未知泵总成。','如果泄漏，拆下燃油泵总成。',
                               '不要拆下燃油泵总成。','拆下燃油泵总成并剪断电线。'])
def test_assembly_unknown_tail_and_condition_back_off(text):
    req,forms=assembly_request(text)
    assert compose(req,forms) is None


def test_assembly_requires_all_reviewed_complete_case_forms():
    req,forms=assembly_request('拆下燃油泵总成。')
    del forms['燃油泵']['genitive']
    assert compose(req,forms) is None


@pytest.mark.parametrize('eligibility',[None,False,'true',1])
def test_assembly_requires_explicit_reviewed_physical_eligibility(eligibility):
    req,forms=assembly_request('安装燃油泵总成。')
    forms['燃油泵']['assembly_allowed']=eligibility
    assert compose(req,forms) is None


def test_abstract_property_with_complete_forms_cannot_become_an_assembly():
    from dataclasses import replace
    req,forms=assembly_request('安装工作比总成。')
    forms['工作比']=dict(base='коэффициент заполнения',nominative='коэффициент заполнения',
                         genitive='коэффициента заполнения',accusative='коэффициент заполнения')
    entry=GlossaryEntry('工作比','коэффициент заполнения','zh','ru',trust=.9,status='REVIEWED',
        notes=json.dumps(dict(review_status='VERIFIED',concept_id='duty-factor',type='compound')))
    def candidates(source,*args):
        return [TermMatch(0,len(source),entry,'builtin:test')] if source=='工作比' else []
    req=replace(req,knowledge_snapshot=SimpleNamespace(candidates=candidates))
    assert compose(req,forms) is None


def test_assembly_medium_confidence_or_missing_context_cannot_render():
    from dataclasses import replace
    req,forms=assembly_request('拆下燃油泵总成。')
    req.context_router.allow_bypass=lambda match,request:False
    assert compose(req,forms) is None
    assert compose(replace(req,context_router=None),forms) is None


def test_rotation_direction_loss_and_inversion_are_rejected():
    assert 'direction:counterclockwise' in violations('逆时针转动螺栓。','Поверните болт по часовой стрелке.')
    assert 'direction:clockwise' in violations('顺时针转动螺栓。','Поверните болт.')
    assert not violations('逆时针转动螺栓。','Поверните болт против часовой стрелки.')
def test_power_owner_uses_complete_genitive_and_cannot_become_component_removal():
    req, forms = request('关闭连接器（Q）电源。')
    forms['连接器']['genitive']='разъёма'
    result = compose(req,forms)
    assert result[0]=='Отключите питание разъёма （Q）.'
    assert not violations(req.text,result[0])
    assert 'action:REMOVE_POWER:APPLY_POWER' in violations(req.text,'Подайте питание разъёма （Q）.')
    for source in ['关闭未知机构电源。','不要关闭连接器电源。','关闭连接器电源，然后检查未知机构。']:
        req, _ = request(source)
        assert compose(req,forms) is None
    req, forms = request('切断连接器电源。')
    assert compose(req,forms) is None  # No genitive form; never infer an ending.
