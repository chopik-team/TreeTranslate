from unittest.mock import Mock
import pytest
from app.engine.types import TranslationRequest,TranslationResult
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from app.knowledge.relations import negative_relation

@pytest.fixture
def engine(tmp_path):
    router=Mock();router.languages.resolve.return_value=('zh','ru');router.policy.max_text_chars=20000
    router.translate.return_value=TranslationResult('fallback','zh','ru','m2m100','cpu',0,'qa',False,'')
    return TranslationKnowledgeEngine(router,Mock(lookup=Mock(return_value=None)),GlossaryEngine(tmp_path/'u.db',builtin_paths=bundled_paths()))

@pytest.mark.parametrize('source,expected',[
    ('拆卸散热器盖(A)。','Снимите крышку радиатора (A).'),
    ('安装冷却风扇总成。','Установите узел вентилятора охлаждения.'),
    ('断开集成热管理模块(ITM)连接器。','Отсоедините разъём интегрированного модуля управления тепловым режимом (ITM).'),
    ('连接集成热管理模块(ITM)连接器。','Подсоедините разъём интегрированного модуля управления тепловым режимом (ITM).'),
    ('补充冷却液。','Долейте охлаждающую жидкость.'),('排出冷却液。','Слейте охлаждающую жидкость.'),
    ('拧紧排放螺塞。','Затяните сливную пробку.'),('松开螺栓。','Ослабьте болт.'),
    ('检查冷却液液位。','Проверьте уровень охлаждающей жидкости.'),
    ('起动发动机。','Запустите двигатель.'),('关闭发动机。','Заглушите двигатель.'),
    ('测量电源电压。','Измерьте напряжение питания.'),('调整液位。','Отрегулируйте уровень жидкости.'),
    ('排出空气。','Удалите воздух из системы.'),('确保没有泄漏。','Убедитесь, что утечек нет.'),
    ('不要混合不同品牌的防冻液/冷却液。','Не смешивайте антифриз/охлаждающую жидкость разных марок.'),
])
def test_actions(engine,source,expected):
    p=engine.profile_document('zh','ru',segments=['冷却液 散热器 发动机 机油 线束 电压 连接器'])
    result=engine.translate(TranslationRequest(source,'zh','ru',context_profile=p,segment_type='PROCEDURE_STEP'))
    assert result.translated_text==expected
    assert result.knowledge_source=='template'

def test_heading_and_step_differ(engine):
    p=engine.profile_document('zh','ru',segments=['冷却液 散热器'])
    result=engine.translate(TranslationRequest('安装冷却风扇总成','zh','ru',context_profile=p,segment_type='HEADING'))
    assert result.translated_text=='Установка узла вентилятора охлаждения'

def test_unsafe_partial_unknown_and_negation(engine):
    p=engine.profile_document('zh','ru',segments=['冷却液 散热器'])
    for text in ['安装未知零件。','安装冷却风扇总成。另外执行。','不要安装冷却风扇总成。']:
        r=engine.translate(TranslationRequest(text,'zh','ru',context_profile=p,segment_type='PROCEDURE_STEP'))
        assert r.knowledge_source!='template'
    assert not negative_relation('不要连接电源。','Подключите питание.')
    assert negative_relation('确保没有泄漏。','Убедитесь, что утечек нет.')

def test_polysemy(engine):
    for texts,target in [(['冷却液 散热器 排气'],'удаление воздуха'),(['发动机 机油 排气'],'выпуск отработавших газов')]:
        p=engine.profile_document('zh','ru',segments=texts)
        r=engine.translate(TranslationRequest('排气','zh','ru',context_profile=p,segment_type='COMPONENT_LABEL'))
        assert r.translated_text.casefold()==target

def test_adjacent_identifiers_and_numbers_remain_protected():
    from app.translation_memory.normalization import compatible
    assert compatible('连接GDS。','Подсоедините GDS.')
    assert not compatible('连接GDS。','Подсоедините устройство.')
    assert compatible('预热发动机20分钟。','Прогревайте двигатель 20 минут.')
    assert not compatible('预热发动机20分钟。','Прогревайте двигатель 10 минут.')

def test_composition_all_or_nothing(engine):
    p=engine.profile_document('zh','ru',segments=['冷却液 散热器'])
    for source in ['拆卸散热器盖。安装冷却风扇总成。','检查冷却液液位。更换未知部件。']:
        r=engine.translate(TranslationRequest(source,'zh','ru',context_profile=p,segment_type='PROCEDURE_STEP'))
        if '未知' in source:assert r.knowledge_source!='template'
        else:assert r.knowledge_source=='template' and 'Снимите крышку радиатора.' in r.translated_text and 'Установите узел' in r.translated_text

def test_holdout_integrity_and_production_boundary():
    from pathlib import Path
    from hashlib import sha256
    import json
    root=Path(__file__).resolve().parents[1]
    held=json.loads((root/'qa/aw087/automotive_semantic_holdout.json').read_text('utf-8'))
    assert held['frozen_before_evaluation'] and len(held['rows'])>=100
    # Historical freeze binds AW087's evaluation, not every future production
    # pack. Preserve the references and compare their recorded evaluation hash.
    result=json.loads((root/'qa/aw087/semantic_holdout_results.json').read_text('utf-8'))
    assert result['holdout_sha256']==sha256((root/'qa/aw087/automotive_semantic_holdout.json').read_bytes()).hexdigest()
    assert result['references_unchanged']
    for path in (root/'app').rglob('*.py'):
        assert 'automotive_semantic_holdout.json' not in path.read_text('utf-8')

def test_industrial_reuse_needs_data_only(tmp_path):
    from pathlib import Path
    import shutil,json
    from app.glossary.database import Database
    from app.glossary.repository import Repository
    root=Path(__file__).resolve().parents[1];path=tmp_path/'industrial.db'
    shutil.copy2(root/'assets/knowledge/aw083-body-repair-zh-ru.db',path)
    repo=Repository(Database(path))
    repo.insert_many([dict(source_term='螺栓',target_term='болт',source_language='zh',target_language='ru',domain='industrial',status='BUILTIN',
        notes=json.dumps(dict(type='term',subdomains=['mechanical'],segment_types=['COMPONENT_LABEL'],concept_id='qa:bolt')))])
    with repo.db.connect(write=True) as con:
        uid=con.execute("SELECT id FROM entries WHERE domain='industrial'").fetchone()[0]
        con.execute('INSERT INTO knowledge_context_index VALUES(?,?,?,?,?,?,?,?)',(uid,'zh','ru','industrial','mechanical','TERM','qa:bolt',100))
    router=Mock();router.languages.resolve.return_value=('zh','ru');router.policy.max_text_chars=20000
    e=TranslationKnowledgeEngine(router,Mock(lookup=Mock(return_value=None)),GlossaryEngine(tmp_path/'u.db',builtin_paths=[path]))
    p=e.profile_document('zh','ru',segments=['车床 铣床 工业轴承'])
    assert p.primary_domain=='industrial'
    result=e.translate(TranslationRequest('拧紧螺栓。','zh','ru',context_profile=p,segment_type='PROCEDURE_STEP'))
    assert result.translated_text=='Затяните болт.' and result.knowledge_source=='template'
