import json
from types import SimpleNamespace
from app.engine.types import TranslationRequest
from app.glossary.models import GlossaryEntry, TermMatch
from app.knowledge.objects import ObjectGuard


def setup():
    components = [('水泵','water','водяной насос','водяного насоса'),
                  ('燃油泵','fuel','топливный насос','топливного насоса'),
                  ('水泵连接器','connector','разъём водяного насоса','разъёма водяного насоса')]
    entries = tuple(GlossaryEntry(source,target,'zh','ru',trust=.9,status='REVIEWED',
        notes=json.dumps(dict(type='COMPOUND',concept_id=concept))) for source,concept,target,_ in components)
    forms = {source:dict(nominative=target,accusative=target,genitive=gen) for source,_,target,gen in components}
    def candidates(text,*args):
        return [TermMatch(text.index(e.source_term),text.index(e.source_term)+len(e.source_term),e)
                for e in entries if e.source_term in text]
    snapshot = SimpleNamespace(signature='independent-fixture',entries=entries,candidates=candidates)
    return ObjectGuard(), forms, snapshot


def test_known_component_substitution_is_rejected():
    guard,forms,snapshot = setup()
    request = TranslationRequest('检查水泵。','zh','ru',knowledge_snapshot=snapshot)
    assert guard.violations(request,'Проверьте топливный насос.',forms) == ('object:water:fuel',)
    assert not guard.violations(request,'Проверьте водяной насос.',forms)
    assert not guard.violations(request,'Проверьте неизвестный агрегат.',forms)


def test_two_source_objects_and_nested_parent_are_not_substitution():
    guard,forms,snapshot = setup()
    request = TranslationRequest('检查水泵和燃油泵。','zh','ru',knowledge_snapshot=snapshot)
    assert not guard.violations(request,'Проверьте водяной насос и топливный насос.',forms)
    request = TranslationRequest('检查水泵连接器。','zh','ru',knowledge_snapshot=snapshot)
    assert not guard.violations(request,'Проверьте контакты на разъёме водяного насоса.',forms)


def test_guard_index_is_bounded_and_reused():
    guard,forms,snapshot = setup()
    assert guard.index(snapshot,forms) is guard.index(snapshot,forms)
    for i in range(20):
        other = SimpleNamespace(signature=str(i), entries=snapshot.entries)
        guard.index(other,forms)
    assert len(guard.cache) == 12


def test_reviewed_same_target_and_translated_nested_parent_are_not_substitution():
    guard,forms,snapshot = setup()
    duplicate = GlossaryEntry('泵水','водяной насос','zh','ru',trust=.9,status='REVIEWED',
        notes=json.dumps(dict(type='TERM',concept_id='same-rendering')))
    forms['泵水'] = forms['水泵']
    snapshot.entries += (duplicate,)
    request = TranslationRequest('检查水泵和燃油泵。','zh','ru',knowledge_snapshot=snapshot)
    assert not guard.violations(request,'Проверьте водяной насос и топливный насос.',forms)


def test_retained_whole_compound_without_case_forms_protects_nested_nouns():
    guard,forms,snapshot = setup()
    entry = GlossaryEntry('水泵连接器孔','отверстие разъёма водяного насоса','zh','ru',trust=.9,status='REVIEWED',
        notes=json.dumps(dict(type='COMPOUND',review_status='VERIFIED',concept_id='hole')))
    original_candidates = snapshot.candidates
    def candidates(text,*args):
        result = original_candidates(text,*args)
        if entry.source_term in text:
            result.append(TermMatch(text.index(entry.source_term),text.index(entry.source_term)+len(entry.source_term),entry))
        return result
    snapshot.candidates = candidates
    req = TranslationRequest('检查水泵连接器孔。','zh','ru',knowledge_snapshot=snapshot)
    assert not guard.violations(req,'Проверьте отверстие разъёма водяного насоса.',forms)


def test_retained_generic_parent_does_not_hide_specific_object_substitution():
    guard,forms,snapshot = setup()
    entry = GlossaryEntry('泵','насос','zh','ru',trust=.9,status='REVIEWED',
        notes=json.dumps(dict(type='TERM',review_status='VERIFIED',concept_id='generic-pump')))
    original_candidates = snapshot.candidates
    def candidates(text,*args):
        return original_candidates(text,*args)+[TermMatch(text.index('泵'),text.index('泵')+1,entry)]
    snapshot.candidates = candidates
    req = TranslationRequest('检查水泵。','zh','ru',knowledge_snapshot=snapshot)
    assert guard.violations(req,'Проверьте топливный насос.',forms) == ('object:water:fuel',)


def test_retained_source_object_is_not_extra_when_other_case_is_unindexed():
    guard,forms,snapshot = setup()
    req = TranslationRequest('检查水泵和燃油泵。','zh','ru',knowledge_snapshot=snapshot)
    # Instrumental is deliberately not inferred from the three reviewed forms.
    assert not guard.violations(req,'Проверьте водяным насосом топливный насос.',forms)
