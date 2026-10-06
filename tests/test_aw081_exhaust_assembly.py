"""A service assembly must retain its components and one removal operation."""
from test_aw081_duty_and_relations import engine, request
from app.glossary.models import entry_metadata
from app.knowledge.safety import source_actions, russian_actions


def test_remove_exhaust_assembly_preserves_operation_and_joint_object(engine):
    source = '拆卸催化转化器&中央消声器。'
    result = engine.lookup_direct(request(source, 'emissions', kind='PROCEDURE_STEP'))
    assert result is not None
    assert result.translated_text == 'Снимите каталитический нейтрализатор и центральный глушитель в сборе.'
    assert source_actions(source) == russian_actions(result.translated_text) == {'REMOVE'}
    engine.router.translate.assert_not_called()
    assert engine.lookup_direct(request(source, 'electrical', kind='PROCEDURE_STEP')) is None
    from app.documents.job import DocumentJob, DocumentConfig
    from app.documents.control import JobControl
    req = engine.contextualize(request(source, 'emissions', kind='PROCEDURE_STEP'))
    job = DocumentJob([], DocumentConfig(source='zh', target='ru'), JobControl(),
                      engine.translate, engine.languages.resolve)
    job._domain, job._context_profile, job._snapshot = req.domain, req.context_profile, req.knowledge_snapshot
    job._segment_type = 'PROCEDURE_STEP'
    assert job._pdf_translation('1. ' + source, 'zh', 'ru') == '1. ' + result.translated_text
    engine.router.translate.assert_not_called()


def test_component_concepts_are_independent_of_the_joint_service_assembly(engine):
    req = engine.contextualize(request('分离催化转化器和中央消声器。', 'emissions', kind='PROCEDURE_STEP'))
    matches = req.knowledge_snapshot.candidates(req.text, req.domain, req.context, set())
    components = {m.entry.source_term: entry_metadata(m.entry)['concept_id'] for m in matches
                  if m.entry.source_term in {'催化转化器', '中央消声器'}}
    assert set(components) == {'催化转化器', '中央消声器'}
    assert len(set(components.values())) == 2
    assert not any(m.entry.source_term == '催化转化器&中央消声器' for m in matches)
    known = engine.lookup_direct(request('催化转化器&中央消声器', 'emissions', kind='COMPONENT_LABEL'))
    assert known and known.translated_text.endswith('центральный глушитель в сборе')
    changed = engine.lookup_direct(request('拆卸催化转化器&未知消声器。', 'emissions', kind='PROCEDURE_STEP'))
    assert changed is None
