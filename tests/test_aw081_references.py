import json
from unittest.mock import Mock
from app.knowledge.references import render, is_reference
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from app.engine.types import TranslationRequest
from app.glossary.models import GlossaryEntry, TermMatch
import pytest


def test_closed_reference_quotes_known_labels_and_keeps_unknown_untranslated():
    lookup = {'测试系统':'тестовая система','测试盖':'сервисная крышка'}.get
    assert render('（参考测试系统-“测试盖”）',lookup) == 'См. раздел «тестовая система», подраздел «сервисная крышка».'
    assert render('（请参阅测试系统-"未知盖")',lookup) is None
    assert render('（参考测试系统-“测试盖',lookup) is None
    assert not is_reference('检查盖。然后参考测试手册。')


def test_unknown_reference_warns_without_creating_memory():
    glossary = Mock()
    glossary.lookup.return_value = ()
    memory = Mock()
    engine = TranslationKnowledgeEngine(Mock(),memory,glossary)
    request = TranslationRequest('（参考测试系统-“未知标题”）','zh','ru')
    result = engine._structured_exact(request)
    assert result.translated_text == request.text
    assert result.constraint_status.startswith('semantic_source_preserved:')
    assert glossary.warning.called
    assert not memory.remember.called


def test_equal_title_targets_back_off_instead_of_selecting_first():
    glossary = Mock()
    def lookup(text,*args,**kwargs):
        targets = ['сервисная крышка','крышка насоса'] if text=='测试盖' else ['тестовая система']
        return tuple(TermMatch(0,len(text),GlossaryEntry(text,target,'zh','ru',trust=.9,status='REVIEWED',
                     notes=json.dumps(dict(review_status='VERIFIED'))),'official') for target in targets)
    glossary.lookup.side_effect = lookup
    engine = TranslationKnowledgeEngine(Mock(),Mock(),glossary)
    request = TranslationRequest('（参考测试系统-“测试盖”）','zh','ru')
    result = engine._structured_exact(request)
    assert 'название подраздела в источнике: «测试盖»' in result.translated_text
    assert result.constraint_status == 'verified_cross_reference:source_title_preserved'


def test_annotation_preserves_exact_title_and_keeps_general_validator_strict():
    from app.knowledge.references import validate_source_title
    from app.documents.pdf_fidelity import faithful_result, FidelityMismatch
    source = '（参考测试系统-“未知盖A 25mm”）'
    target = 'См. раздел «тестовая система», название подраздела в источнике: «未知盖A 25mm».'
    assert validate_source_title(source,target)==target
    with pytest.raises(FidelityMismatch):
        faithful_result(source,target)
    from app.glossary.errors import ConstraintFailure
    for invalid in [target.replace('25mm','26mm'),target.replace('未知盖','已知盖'),
                    target.replace('тестовая система','测试系统'),target+' 新文字']:
        with pytest.raises(ConstraintFailure):
            validate_source_title(source,invalid)


def test_document_job_accepts_only_explicit_reference_annotation():
    from app.documents.job import DocumentJob, DocumentConfig
    from app.documents.control import JobControl
    from app.engine.types import TranslationResult
    source = '（参考测试系统-“未知盖A 25mm”）'
    target = 'См. раздел «тестовая система», название подраздела в источнике: «未知盖A 25mm».'
    class Boundary:
        def translate(self,*args):
            raise AssertionError('No model inference for a structured reference')
        def lookup_direct(self,*args):
            return TranslationResult(target,'zh','ru','knowledge_template','none',0,'',False,'',
                                     constraint_status='verified_cross_reference:source_title_preserved')
    boundary, warnings = Boundary(), []
    job = DocumentJob([],DocumentConfig(source='zh',target='ru'),JobControl(),boundary.translate,
                      lambda *a:('zh','ru'),warning=warnings.append)
    assert job._pdf_translation(source,'zh','ru')==target
    assert warnings


def test_tagged_system_uses_whole_reviewed_genitive_not_free_morphology():
    from app.knowledge.references import tagged_label
    lookup = {'测试传感器':'тестовый датчик'}.get
    forms = {'测试传感器':dict(base='тестовый датчик',genitive='тестового датчика')}
    assert tagged_label('测试传感器（ABC）系统',lookup,forms)=='система тестового датчика （ABC）'
    assert tagged_label('测试传感器(ABC)',lookup,forms)=='тестовый датчик (ABC)'
    assert tagged_label('未知传感器(ABC)系统',lookup,forms) is None
    assert tagged_label('测试传感器(ABC)系统',lookup,{}) is None


def test_repeated_opening_quote_is_formatting_not_an_invented_title():
    lookup = {'测试系统':'тестовая система','测试盖':'сервисная крышка'}.get
    assert render('（请参考测试系统-“测试盖“）',lookup)=='См. раздел «тестовая система», подраздел «сервисная крышка».'
