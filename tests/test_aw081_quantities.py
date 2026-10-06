from app.knowledge.units import quantity_caption


def test_caption_reuses_complete_verified_noun_without_changing_units():
    forms = {'容量':dict(base='ёмкость',nominative='ёмкость',gender='f'),
             '电压':dict(base='напряжение',nominative='напряжение',gender='n')}
    lookup = lambda source: forms.get(source,{}).get('base')
    assert quantity_caption('最大容量(mL)',lookup,forms)=='Максимальная ёмкость(mL)'
    assert quantity_caption('额定电压（V）',lookup,forms)=='Номинальное напряжение（V）'
    assert quantity_caption('向电池加注最大容量。',lookup,forms) is None
    assert quantity_caption('总压力',lookup,forms) is None
    assert quantity_caption('最小未知容量',lookup,forms) is None


def test_unknown_gender_or_competing_sense_is_not_inflected():
    forms = {'容量':dict(base='ёмкость',nominative='ёмкость')}
    assert quantity_caption('最大容量',lambda _: 'ёмкость',forms) is None
    forms['容量']['gender'] = 'f'
    assert quantity_caption('最大容量',lambda _: 'мощность',forms) is None


def test_ambiguous_nominal_labels_do_not_replace_verbs_in_short_prose(tmp_path):
    from unittest.mock import Mock
    from app.glossary.engine import GlossaryEngine
    from app.glossary.repository import Repository
    from app.glossary.database import Database
    from app.engine.types import TranslationRequest, TranslationResult
    import json
    db = tmp_path/'official.db'
    Repository(Database(db)).insert_many([dict(source_term='说明',target_term='описание',source_language='zh',target_language='ru',
        domain='automotive',status='BUILTIN',notes=json.dumps(dict(label_only=True)),source_pack='reviewed-test')])
    glossary = GlossaryEngine(tmp_path/'user.db',builtin_paths=[db])
    assert glossary.full_segment(TranslationRequest('说明','zh','ru',domain='automotive')).translated_text=='описание'
    backend = Mock()
    backend.translate.return_value = TranslationResult('Поясните результаты проверки.','zh','ru','m2m100','cpu',0,'',False,'')
    from threading import Event
    glossary.translate(TranslationRequest('请说明测试结果','zh','ru',domain='automotive'),backend,Event())
    assert backend.translate.call_args[0][0].text == '请说明测试结果'


import json
from dataclasses import replace
from types import SimpleNamespace
import pytest
from app.engine.types import TranslationRequest
from app.glossary.models import GlossaryEntry, TermMatch
from app.knowledge.units import reviewed_quantity_label


def caption_request(text, *, high=True, user=False, ambiguous=False, role='quantity', kind='compound', verified=True, label_only=True):
    metadata=dict(concept_id='test-resistance',review_status='VERIFIED' if verified else 'REVIEWED',
                  semantic_role=role,type=kind,label_only=label_only)
    entry=GlossaryEntry('参考电阻','Эталонное сопротивление','zh','ru',trust=.9,status='REVIEWED',notes=json.dumps(metadata))
    entries=[entry]
    if ambiguous:
        entries.append(replace(entry,target_term='Иное сопротивление',notes=json.dumps(dict(metadata,concept_id='other'))))
    def candidates(source,*args):
        return [TermMatch(0,len(source),e,'user' if user else 'builtin:test') for e in entries if source==e.source_term]
    return TranslationRequest(text,'zh','ru',domain='automotive',knowledge_snapshot=SimpleNamespace(candidates=candidates),
        context_router=SimpleNamespace(allow_bypass=lambda match,request:high))


@pytest.mark.parametrize('colon',[':', '：'])
def test_whole_quantity_caption_keeps_literal_colon_without_model(colon):
    req=caption_request('参考电阻'+colon)
    assert reviewed_quantity_label(req)=='Эталонное сопротивление'+colon
    from app.translation_memory.knowledge import TranslationKnowledgeEngine
    engine=object.__new__(TranslationKnowledgeEngine)
    result=engine._structured_exact(req)
    assert result.translated_text=='Эталонное сопротивление'+colon
    assert result.constraint_status=='verified_quantity_label'


@pytest.mark.parametrize('options',[dict(high=False),dict(user=True),dict(ambiguous=True),
    dict(role='diagnostic_relation'),dict(kind='full_segment'),dict(verified=False),dict(label_only=False)])
def test_caption_requires_unique_reviewed_quantity_and_high_confidence(options):
    assert reviewed_quantity_label(caption_request('参考电阻：',**options)) is None


@pytest.mark.parametrize('text',['参考电阻','检查参考电阻：','参考电阻：5 Ω','如果参考电阻：','参考电阻，检查：'])
def test_quantity_caption_does_not_translate_prose_or_numeric_values(text):
    assert reviewed_quantity_label(caption_request(text)) is None


def test_caption_requires_context_and_supported_language():
    req=caption_request('参考电阻：')
    for changed in [replace(req,context_router=None),replace(req,knowledge_snapshot=None),
                    replace(req,target_language='en'),replace(req,domain='general')]:
        assert reviewed_quantity_label(changed) is None
