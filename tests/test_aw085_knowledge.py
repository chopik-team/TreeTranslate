"""Knowledge contracts and safety boundaries; no research weights required."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
import pytest
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.engine.types import TranslationRequest,TranslationResult
from app.translation_memory.knowledge import TranslationKnowledgeEngine

@pytest.fixture
def knowledge(tmp_path):
    glossary=GlossaryEngine(tmp_path/'user.db',builtin_paths=bundled_paths())
    router=Mock();router.languages.resolve.return_value=('zh','ru');router.policy.max_text_chars=20000
    router.translate.return_value=TranslationResult('Перевод модели','zh','ru','m2m100','cpu',1,'qa',False,'')
    memory=Mock();memory.lookup.return_value=None
    return TranslationKnowledgeEngine(router,memory,glossary)

def req(text,domain='automotive'):return TranslationRequest(text,'zh','ru',domain=domain)

@pytest.mark.parametrize('source,target',[
    ('前门上铰链安装孔','Отверстие крепления верхней петли передней двери'),
    ('后门下铰链安装孔','Отверстие крепления нижней петли задней двери'),
    ('测量前检查探头','Перед измерением проверьте измерительный наконечник'),
    ('使用卷尺时','При использовании рулетки'),
    ('前門上鉸鏈安裝孔','Отверстие крепления верхней петли передней двери'),
    ('自由間隙','Люфт')])
def test_longest_compound_phrase_and_explicit_alias(knowledge,source,target):
    assert knowledge.lookup_direct(req(source)).translated_text==target
    knowledge.router.translate.assert_not_called()

@pytest.mark.parametrize('suffix',[' （Ø13）','(7x12)',' （D:Ø9 D\':Ø7）'])
def test_literal_measurement_suffix(knowledge,suffix):
    assert knowledge.lookup_direct(req('前门上铰链安装孔'+suffix)).translated_text.endswith(suffix)

def test_user_priority_and_memory_semantics(knowledge):
    request=req('使用卷尺时')
    knowledge.glossary.remember_term(request.text,'Когда используется рулетка','zh','ru','automotive')
    assert knowledge.lookup_direct(request).translated_text=='Когда используется рулетка'
    knowledge.memory.lookup.return_value=Mock(reusable=True,target='Проверенный TM',match_type='exact',translation_unit_id=1)
    assert knowledge.translate(request).translated_text=='Проверенный TM'

@pytest.mark.parametrize('source',[
    '3. 使用卷尺时,一定要确保卷尺没有拉长、 扭曲或弯曲。',
    '5. 投影尺寸是测量点投影到参考平面时的测量尺寸,用来作为车身变动的基准尺寸。',
    '6. 如果轨距仪的探头长度可以调整,可通过增加一个长度等同于两个表面之间高度差的测量段,将探头加长进行测量。',
    '检查探头和量规,确保无自 由间隙。'])
def test_known_instructions_without_neural_guess(knowledge,source):
    result=knowledge.translate(req(source))
    assert result.backend=='glossary'
    assert not any('\u4e00'<=c<='\u9fff' for c in result.translated_text)
    knowledge.router.translate.assert_not_called()

def test_fullwidth_punctuation_alias(knowledge):
    result=knowledge.translate(req('使用卷尺时，一定要确保卷尺没有拉长、扭曲或弯曲.'))
    assert 'не перекручена' in result.translated_text
    knowledge.router.translate.assert_not_called()

def test_sentence_slots_have_safe_phrase_form_and_bounded_correction(knowledge):
    matches=knowledge.glossary.lookup('使用卷尺时,请检查新型测量仪器。','zh','ru','automotive')
    safe=knowledge.glossary.sentence_safe_matches('使用卷尺时,请检查新型测量仪器。',matches)
    assert any(m.entry.target_term=='при использовании рулетки' for m in safe)
    assert not any(m.entry.source_term=='测量' for m in safe)
    noun=knowledge.glossary.lookup('卷尺','zh','ru','automotive')
    assert knowledge.glossary.grammatical_phrases('При использовании рулетка',noun)=='При использовании рулетки'

def test_unknown_label_and_domain_are_not_exact_substring(knowledge):
    assert knowledge.lookup_direct(req('不是前门上铰链安装孔')) is None
    assert knowledge.lookup_direct(req('前门上铰链安装孔','gaming')) is None
    knowledge.translate(req('新型复合材料支承机构'))
    knowledge.router.translate.assert_called_once()

def test_numbered_sentence_preserves_marker(knowledge):
    result=knowledge.lookup_direct(req('17. 检查探头和量规,确保无自由间隙。'))
    assert result.translated_text.startswith('17. ')
    assert 'люфта' in result.translated_text

@pytest.mark.parametrize('source,target',[
    ('车身尺寸','Размеры кузова'),('一般事项','Общие сведения'),('内部','Внутренняя часть кузова'),
    ('前车身','Передняя часть кузова'),('后车身','Задняя часть кузова'),('车身侧面','Боковая часть кузова'),
    ('车身底部','Нижняя часть кузова'),('车身面板间隙','Зазоры кузовных панелей'),('车身维修','Ремонт кузова')])
def test_filename_folder_knowledge(knowledge,source,target):
    assert knowledge.lookup_direct(req(source)).translated_text==target

def test_pack_checksum_and_review_metadata():
    manifest=json.loads(Path('assets/knowledge/manifest.json').read_text('utf-8'))
    pack=next(p for p in manifest['packs'] if p['pack_id']=='aw083-body-repair')
    assert hashlib.sha256((Path('assets/knowledge')/pack['file']).read_bytes()).hexdigest()==pack['sha256']
    reviewed=json.loads(Path('qa/aw085/reviewed_entries.json').read_text('utf-8'))
    assert all(r['review_status']=='VERIFIED' and r['provenance'] and r['language_pair']=='zh>ru' for r in reviewed)

def test_residue_distinguishes_missing_translation_placement_and_noise():
    from tools.aw085_metrics import residue_class
    untranslated=dict(text='孔',translated='孔',visible_text='',overflow_text='')
    assert residue_class(untranslated).startswith('A_')
    assert residue_class(dict(untranslated,translated='Отверстие')).startswith('B_')
    assert residue_class(untranslated,'noise').startswith('C_')
    assert residue_class(dict(untranslated,visible_text='Отверстие')) is None

def test_structured_tag_preserves_geometry(knowledge):
    result=knowledge.lookup_direct(req('A&B [完整装饰]'))
    assert result.translated_text=='A&B [Полная отделка]'

def test_measurement_verb_does_not_swallow_hole_diameter(knowledge):
    matches=knowledge.glossary.lookup('先测量孔径，再测量孔中心距。','zh','ru','automotive')
    assert any(m.entry.source_term=='孔径' for m in matches)
    assert not any(m.entry.source_term=='测量孔' for m in matches)

def test_nested_list_markers_do_not_match_instruction_substring(knowledge):
    assert knowledge.lookup_direct(req('1. 2. 使用卷尺时')) is None
