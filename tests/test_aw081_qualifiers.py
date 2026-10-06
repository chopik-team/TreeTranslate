import json
from dataclasses import replace
from app.knowledge.qualifiers import derived_constraints
from app.glossary.models import GlossaryEntry, TermMatch
from app.glossary.placeholders import PlaceholderCodec


def fixture(text):
    entry = GlossaryEntry('冷却液','охлаждающая жидкость','zh','ru',domain='automotive',trust=.9,status='REVIEWED',
        notes=json.dumps(dict(review_status='VERIFIED',concept_id='coolant')),source_pack='reviewed')
    start = text.index('冷却液')
    matches = [TermMatch(start,start+3,entry,'official')]
    forms = {'冷却液':dict(base='охлаждающая жидкость',nominative='охлаждающая жидкость')}
    return matches, forms


def test_two_independent_properties_remain_inside_one_constraint():
    text = '检查低温高压冷却液。'
    matches, forms = fixture(text)
    result = derived_constraints(text,matches,forms)
    assert len(result)==1
    assert text[result[0].start:result[0].end]=='低温高压冷却液'
    assert result[0].entry.target_term=='охлаждающая жидкость низкой температуры и высокого давления'
    codec = PlaceholderCodec()
    plan = codec.encode(text,result)
    restored = codec.restore('Проверьте '+plan.mapping[0][0]+'.',plan)
    assert 'низкой температуры и высокого давления' in restored
    assert result[0].entry.origin=='authored_rule'


def test_unknown_degree_duplicate_dimension_and_user_preference_back_off():
    for text in ['检查过低压冷却液。','检查高压低压冷却液。']:
        matches, forms = fixture(text)
        assert not derived_constraints(text,matches,forms)
    text = '检查低温冷却液。'
    matches, forms = fixture(text)
    user = replace(matches[0],store='user',entry=replace(matches[0].entry,target_term='пользовательский термин'))
    assert not derived_constraints(text,matches+[user],forms)


def test_unqualified_electrical_pressure_character_does_not_select_pressure():
    text = '低压电路'
    entry = GlossaryEntry('电路','электрическая цепь','zh','ru',domain='automotive',trust=.9,status='REVIEWED',
                         notes=json.dumps(dict(review_status='VERIFIED')))
    assert not derived_constraints(text,[TermMatch(2,4,entry,'official')],{})


def test_legacy_free_text_or_nonobject_notes_cannot_supply_review_metadata():
    from app.glossary.models import entry_metadata
    text = '检查低温冷却液。'
    matches, forms = fixture(text)
    for notes in ['Imported legacy terminology', '[]', 'null', '"VERIFIED"']:
        entry = replace(matches[0].entry,notes=notes)
        assert entry_metadata(entry)=={}
        assert not derived_constraints(text,[replace(matches[0],entry=entry)],forms)
