from dataclasses import replace
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from threading import Event
import json
import socket
import sqlite3
from zipfile import ZipFile,ZIP_DEFLATED
import pytest

from app.glossary.engine import GlossaryEngine
from app.glossary.database import Database
from app.glossary.repository import Repository
from app.glossary.errors import InvalidGlossary,ConstraintFailure
from app.glossary.normalization import normalize
from app.glossary.placeholders import PlaceholderCodec
from app.glossary.packs import build_pack,install_pack,enable_pack,disable_pack,remove_pack,list_packs
from app.glossary.importer import source_rows,import_terms
from app.glossary.exporter import export_user
from app.glossary.maintenance import integrity,duplicates,conflicts,variant_overlaps,stats
from app.glossary.constraints import validate_result
from app.translation_memory.engine import TranslationMemoryEngine
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from app.engine.router.translation_router import TranslationRouter
from app.engine.types import TranslationRequest,TranslationResult

FIXTURE=Path('tests/fixtures/glossary')


@pytest.fixture
def glossary(tmp_path):return GlossaryEngine(tmp_path/'glossary.db')


def add(g,source='connector',target='разъём',**kw):
    return g.remember_term(source,target,'en','ru',**kw)


def test_schema_atomic_and_indexes(glossary):
    assert glossary.lookup('none','en','ru')==()
    assert integrity(glossary.db)==['ok']
    with glossary.db.connect() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==1
        assert c.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        plan=str([tuple(r) for r in c.execute('EXPLAIN QUERY PLAN SELECT * FROM aliases WHERE pair=? AND domain=? AND hash=?',('en>ru','general','hash'))])
        assert 'SEARCH' in plan and 'PRIMARY KEY' in plan


@pytest.mark.parametrize('source,text,expected', [('car','card',False),('car','car.',True),('разъём','разъёмный',False),
 ('разъём','разъём!',True),('冷却液','更换冷却液。',True),('radiator cap','the radiator cap.',True),
 ('engine-coolant','engine-coolant',True),('ITM-1','ITM-2',False),('PS4','PS5',False),('M10','M12',False)])
def test_boundaries(glossary,source,text,expected):
    add(glossary,source,'термин')
    assert bool(glossary.lookup(text,'en','ru'))==expected


def test_case_unicode_variants(glossary):
    add(glossary,'Coolant',case_sensitive=True,variants=['cooling fluid'])
    assert not glossary.lookup('coolant','en','ru')
    assert glossary.lookup('cooling\n fluid','en','ru')
    add(glossary,'straße','улица',case_sensitive=False)
    hit=glossary.lookup('STRASSE','en','ru')[0]
    assert (hit.start,hit.end)==(0,7)
    add(glossary,'café','кафе',case_sensitive=False)
    assert glossary.lookup('cafe\u0301','en','ru')[0].end==5
    add(glossary,'ＡＢ','АБ',case_sensitive=True)
    assert glossary.lookup('AB','en','ru')


def test_longest_overlap_and_priority(glossary):
    for term in ['coolant','engine coolant','engine coolant temperature sensor']:
        add(glossary,term,'термин')
    matches=glossary.lookup('engine coolant temperature sensor','en','ru')
    assert len(matches)==1 and matches[0].entry.source_term=='engine coolant temperature sensor'
    add(glossary,'coolant','особый',priority=100)
    assert glossary.lookup('engine coolant temperature sensor','en','ru')[0].entry.target_term=='особый'


def test_domain_context_direction_trust(glossary):
    add(glossary,'driver','оператор')
    add(glossary,'driver','драйвер',domain='software')
    add(glossary,'driver','водитель',domain='automotive')
    assert glossary.lookup('driver','en','ru','software')[0].entry.target_term=='драйвер'
    assert glossary.lookup('driver','en','ru','automotive')[0].entry.target_term=='водитель'
    assert glossary.lookup('driver','en','ru')[0].entry.target_term=='оператор'
    assert not glossary.lookup('оператор','ru','en')
    add(glossary,'warning','предупреждение',context='heading')
    assert not glossary.lookup('warning','en','ru')
    assert glossary.lookup('warning','en','ru',context='heading')
    glossary.repository.insert_many([dict(source_term='auto',target_term='авто',source_language='en',target_language='ru')])
    assert not glossary.lookup('auto','en','ru')


def test_full_segment_and_keep(glossary):
    add(glossary)
    hit=glossary.full_segment(TranslationRequest(' connector ','en','ru'))
    assert hit.translated_text=='разъём' and hit.constraint_status=='full_segment'
    add(glossary,'ITM','ITM',mode='KEEP')
    assert glossary.full_segment(TranslationRequest('ITM','en','ru')).translated_text=='ITM'
    add(glossary,'M10','M12')
    assert glossary.full_segment(TranslationRequest('M10','en','ru')) is None


@pytest.mark.parametrize('output,valid', [('ZXQ0001QXZ',True),('ZXQ0001QXZ.',True),('文字ZXQ0001QXZ文字',True),
 ('слово ZXQ0001QXZ',True),('',False),('ZXQ0002QXZ',False),('ZXQ0001QXZ ZXQ0001QXZ',False),
 ('ZXQ0001QX',False),('abcZXQ0001QXZ',False),('ZXQ 0001 QXZ',False)])
def test_codec_integrity(glossary,output,valid):
    add(glossary)
    plan=glossary.constraints('connector','en','ru')
    if valid:assert 'разъём' in glossary.codec.restore(output,plan)
    else:
        with pytest.raises(ConstraintFailure):glossary.codec.restore(output,plan)


def test_codec_reorder_collision(glossary):
    add(glossary);add(glossary,'coolant','антифриз')
    plan=glossary.constraints('connector coolant','en','ru')
    assert glossary.codec.restore('ZXQ0002QXZ ZXQ0001QXZ',plan)=='антифриз разъём'
    plan=glossary.constraints('ZXQ0001QXZ connector','en','ru')
    assert plan.mapping[0][0]=='ZXQ0002QXZ'


@pytest.mark.parametrize('pattern', ['ZXQ{:04d}QXZ','TTTERM{:04d}','__TTTERM{:04d}__'])
@pytest.mark.parametrize('source,expected', [
    ('ECV冷却液ON','ECV {token} ON'),
    ('24冷却液_','24 {token} _'),
    ('更换冷却液。','更换{token}。'),
])
def test_codec_generated_ascii_boundaries(glossary,pattern,source,expected):
    glossary.remember_term('冷却液','охлаждающая жидкость','zh','ru')
    codec=PlaceholderCodec(pattern)
    plan=codec.encode(source,glossary.lookup(source,'zh','ru'))
    assert plan.text==expected.format(token=pattern.format(1))
    assert 'охлаждающая жидкость' in codec.restore(plan.text,plan)


@pytest.mark.parametrize('pattern', ['ZXQ{:04d}QXZ','TTTERM{:04d}','__TTTERM{:04d}__'])
def test_codec_adjacent_terms_do_not_relax_restore_integrity(glossary,pattern):
    glossary.remember_term('冷却液','охлаждающая жидкость','zh','ru')
    glossary.remember_term('压力','давление','zh','ru')
    codec=PlaceholderCodec(pattern)
    plan=codec.encode('冷却液压力',glossary.lookup('冷却液压力','zh','ru'))
    assert plan.text==f'{pattern.format(1)}{pattern.format(2)}'
    assert codec.restore(f'{pattern.format(1)} {pattern.format(2)}',plan)=='охлаждающая жидкость давление'
    with pytest.raises(ConstraintFailure,match='placeholder_integrity'):
        codec.restore(plan.text,plan)


@pytest.mark.parametrize('pattern', ['ZXQ{:04d}QXZ','TTTERM{:04d}','__TTTERM{:04d}__'])
@pytest.mark.parametrize('extra', ['ZXQ9999QXZ','TTTERM9999','__TTTERM9999__'])
def test_codec_rejects_unexpected_markers_for_all_policies(glossary,pattern,extra):
    add(glossary)
    codec=PlaceholderCodec(pattern)
    plan=codec.encode('Replace connector.',glossary.lookup('Replace connector.','en','ru'))
    with pytest.raises(ConstraintFailure,match='unexpected_placeholder'):
        codec.restore(f'{plan.mapping[0][0]} {extra}',plan)


@pytest.mark.parametrize('pattern', ['ZXQ{:04d}QXZ','TTTERM{:04d}','__TTTERM{:04d}__'])
def test_codec_preserves_existing_literal_marker(glossary,pattern):
    add(glossary)
    literal=pattern.format(1)
    source=f'{literal} connector'
    codec=PlaceholderCodec(pattern)
    plan=codec.encode(source,glossary.lookup(source,'en','ru'))
    assert plan.mapping[0][0]==pattern.format(2)
    assert codec.restore(plan.text,plan)==f'{literal} разъём'


def test_constraint_fallback_warning(glossary):
    add(glossary)
    req=TranslationRequest('Replace connector.','en','ru')
    base=TranslationResult('Простой перевод','en','ru','fake','cpu',0,'test',False,req.request_id)
    router=Mock();router.translate.side_effect=[replace(base,translated_text='ZXQ0001BROKEN'),base]
    result=glossary.translate(req,router,Event())
    assert result.constraint_status=='fallback_unconstrained' and result.translated_text=='Простой перевод'
    assert router.translate.call_count==2 and glossary.last_warning


def test_enforcement_and_forbidden(glossary):
    add(glossary,'coolant','антифриз',forbidden_target_variants=['кондиционер'])
    req=TranslationRequest('Replace coolant.','en','ru')
    router=Mock();router.translate.return_value=TranslationResult('Замените ZXQ0001QXZ.','en','ru','fake','cpu',0,'test',False,req.request_id)
    result=glossary.translate(req,router,Event())
    assert result.translated_text=='Замените антифриз.' and result.constraint_status=='enforced'
    router.translate.side_effect=[replace(result,translated_text='кондиционер ZXQ0001QXZ'),replace(result,translated_text='кондиционер')]
    assert glossary.translate(req,router,Event()).constraint_status=='forbidden_detected'


@pytest.mark.parametrize('source,target',[('GDS ITM IVT 6.6 45–60% 20','GDS ITM 6.6 45–60% 20'),
 ('6.6','5.5'),('45–60%','40–60%'),('M10','M12'),('20 mm','20 cm'),('6.6 liters','6.6 gallons'),('https://example.com','сайт'),
 ('user@example.com','почта')])
def test_fidelity(source,target):
    with pytest.raises(ConstraintFailure):validate_result(source,target)


def test_compatible_units():
    assert validate_result('Fill 6.6 liters.','Залейте 6.6 литра.')=='Залейте 6.6 литра.'


def test_tm_priority_and_isolation(glossary,tmp_path):
    tm=TranslationMemoryEngine(tmp_path/'tm.db');router=TranslationRouter({});router.translate=Mock()
    tm.remember_translation('Disconnect connector.','Отключите штекер.','en','ru')
    add(glossary)
    engine=TranslationKnowledgeEngine(router,tm,glossary)
    try:
        assert engine.translate(TranslationRequest('Disconnect connector.','en','ru')).translated_text=='Отключите штекер.'
        assert engine.translate(TranslationRequest('connector','en','ru')).translated_text=='разъём'
        router.translate.assert_not_called()
    finally:engine.shutdown()


def test_user_builtin_override_suppress(glossary,tmp_path):
    builtin=GlossaryEngine(tmp_path/'builtin.db');add(builtin,target='соединитель')
    g=GlossaryEngine(glossary.db.path,builtin_paths=[builtin.db.path])
    assert g.lookup('connector','en','ru')[0].entry.target_term=='соединитель'
    g.repository.suppress('connector','en','ru')
    assert not g.lookup('connector','en','ru')
    add(g)
    assert g.lookup('connector','en','ru')[0].entry.target_term=='разъём'
    assert next(builtin.repository.rows()).target_term=='соединитель'
    from app.glossary.maintenance import knowledge_conflicts
    assert knowledge_conflicts(g)['conflicts_total']==1


def test_pack_lifecycle(glossary,tmp_path):
    manifest=json.loads((FIXTURE/'manifest.json').read_text('utf-8'));path=tmp_path/'test.tglossary'
    report=build_pack(source_rows(FIXTURE/'test-automotive.jsonl'),manifest,path)
    assert report['entries']==10
    install_pack(glossary.db,path,trusted=True)
    assert glossary.lookup('connector','en','ru','automotive')[0].entry.target_term=='разъём'
    add(glossary,target='штекер',domain='automotive')
    disable_pack(glossary.db,'test-automotive')
    assert not glossary.lookup('coolant','en','ru','automotive')
    enable_pack(glossary.db,'test-automotive')
    assert glossary.lookup('coolant','en','ru','automotive')
    rows=list(source_rows(FIXTURE/'test-automotive.jsonl'))
    rows.extend(dict(source_term=s,target_term='деталь',source_language='en',target_language='ru',domain='automotive') for s in ('new part','another part'))
    build_pack(rows,dict(manifest,version='2.0.0'),path)
    install_pack(glossary.db,path,trusted=True)
    assert stats(glossary)['builtin_entries']==12
    assert glossary.lookup('connector','en','ru','automotive')[0].entry.target_term=='штекер'
    assert list_packs(glossary.db)[0]['version']=='2.0.0'
    remove_pack(glossary.db,'test-automotive')
    assert not glossary.lookup('coolant','en','ru','automotive')
    assert stats(glossary)['user_entries']==1


def test_invalid_pack_atomic_and_license(glossary,tmp_path):
    manifest=json.loads((FIXTURE/'manifest.json').read_text('utf-8'));path=tmp_path/'test.tglossary'
    with pytest.raises(InvalidGlossary):build_pack([],dict(manifest,license='unknown'),path)
    rows=[dict(source_term=f'part {i}',target_term=f'деталь {i}',source_language='en',target_language='ru',domain='automotive') for i in range(99)]
    with pytest.raises(InvalidGlossary):build_pack([*rows,{'source_term':'bad'}],manifest,path)
    assert not path.exists() and not list_packs(glossary.db)
    build_pack(rows,manifest,path)
    with ZipFile(path) as z:meta=json.loads(z.read('manifest.json'));data=z.read('entries.jsonl')
    meta['entries_sha256']='0'*64
    with ZipFile(path,'w') as z:z.writestr('manifest.json',json.dumps(meta));z.writestr('entries.jsonl',data)
    with pytest.raises(InvalidGlossary):install_pack(glossary.db,path,trusted=True)
    assert not list_packs(glossary.db)


@pytest.mark.parametrize('field,value', [
    ('source_language','auto'),('target_language',None),('source_language','EN'),
    ('domains',[None]),('domains',['bad domain']),('domains',[{}]),
])
def test_pack_manifest_validation_preserves_installed_version(glossary,tmp_path,field,value):
    manifest=json.loads((FIXTURE/'manifest.json').read_text('utf-8'))
    path=tmp_path/'valid.tglossary'
    build_pack(source_rows(FIXTURE/'test-automotive.jsonl'),manifest,path)
    install_pack(glossary.db,path,trusted=True)
    before=list_packs(glossary.db)
    with pytest.raises(InvalidGlossary):
        build_pack([],dict(manifest,**{field:value}),tmp_path/'invalid-build.tglossary')
    with ZipFile(path) as archive:
        metadata=json.loads(archive.read('manifest.json'));data=archive.read('entries.jsonl')
    metadata[field]=value
    invalid=tmp_path/'invalid.tglossary'
    with ZipFile(invalid,'w') as archive:
        archive.writestr('manifest.json',json.dumps(metadata));archive.writestr('entries.jsonl',data)
    with pytest.raises(InvalidGlossary):install_pack(glossary.db,invalid,trusted=True)
    assert list_packs(glossary.db)==before
    assert glossary.lookup('coolant','en','ru','automotive')[0].entry.target_term=='охлаждающая жидкость'
    assert integrity(glossary.db)==['ok']


def test_import_export_csv_tsv_and_trust(glossary,tmp_path):
    for suffix,separator in [('csv',','),('tsv','\t')]:
        path=tmp_path/('terms.'+suffix)
        path.write_text(separator.join(['source','target','source_language','target_language','domain'])+'\n'+separator.join(['connector','разъём','en','ru','general'])+'\n','utf-8')
        import_terms(glossary.repository,path)
        assert not glossary.lookup('connector','en','ru') if suffix=='csv' else True
    import_terms(glossary.repository,path,trusted=True)
    assert glossary.lookup('connector','en','ru')
    output=tmp_path/'export.jsonl';assert export_user(glossary.repository,output)==1
    other=GlossaryEngine(tmp_path/'other.db');import_terms(other.repository,output,trusted=True)
    assert other.lookup('connector','en','ru')


def test_duplicates_conflicts_and_cache(glossary):
    add(glossary);add(glossary)
    assert len(list(glossary.repository.rows()))==1
    add(glossary,target='соединитель')
    assert len(conflicts(glossary.db))==1 and variant_overlaps(glossary.db)
    assert duplicates(glossary.db)==[]
    hit=glossary.lookup('connector','en','ru')[0]
    glossary.repository.disable(hit.entry.id)
    assert glossary.lookup('connector','en','ru')[0].entry.id!=hit.entry.id
    glossary.config['cache_size']=2
    for i in range(10):glossary.lookup(str(i),'en','ru')
    assert len(glossary.cache)<=2


@pytest.mark.parametrize('which',['glossary','tm','both'])
def test_corrupt_independence(glossary,tmp_path,which):
    tm=TranslationMemoryEngine(tmp_path/'tm.db')
    if which in ('tm','both'):tm.db.path.write_bytes(b'broken')
    else:tm.remember_translation('hello','привет','en','ru')
    if which in ('glossary','both'):glossary.db.path.write_bytes(b'broken')
    else:add(glossary)
    router=TranslationRouter({});router.translate=Mock(return_value=TranslationResult('модель','en','ru','fake','cpu',0,'test',False,'id'))
    engine=TranslationKnowledgeEngine(router,tm,glossary)
    try:
        assert engine.translate(TranslationRequest('hello','en','ru')).translated_text==('привет' if which=='glossary' else 'модель')
        if which=='tm':assert engine.translate(TranslationRequest('connector','en','ru')).translated_text=='разъём'
    finally:engine.shutdown()


@pytest.mark.parametrize('repeat',range(5))
def test_concurrency_offline_privacy(glossary,monkeypatch,caplog,repeat):
    def fail(*a,**kw):raise AssertionError('network')
    monkeypatch.setattr(socket,'getaddrinfo',fail);monkeypatch.setattr(socket,'create_connection',fail)
    def work(i):
        g=GlossaryEngine(glossary.db.path);add(g,f'private item {i}',f'термин {i}')
        return bool(g.lookup(f'private item {i}','en','ru'))
    with ThreadPoolExecutor(max_workers=4) as pool:assert all(pool.map(work,range(20)))
    assert 'private item' not in caplog.text and integrity(glossary.db)==['ok']


@pytest.mark.parametrize('failure',['future','migration','locked'])
def test_database_failure_fallback(glossary,failure):
    lock=None
    if failure=='future':
        with sqlite3.connect(glossary.db.path) as c:c.execute('PRAGMA user_version=99')
    elif failure=='migration':
        with sqlite3.connect(glossary.db.path) as c:
            c.execute('CREATE TABLE entries(private_data TEXT)');c.execute("INSERT INTO entries VALUES('preserve')")
    else:
        lock=sqlite3.connect(glossary.db.path);lock.execute('BEGIN EXCLUSIVE')
    try:assert not glossary.lookup('source','en','ru') and glossary.last_warning and glossary.db.path.exists()
    finally:
        if lock:lock.close()
    if failure=='migration':
        with sqlite3.connect(glossary.db.path) as c:
            assert c.execute('SELECT private_data FROM entries').fetchone()[0]=='preserve'
            assert c.execute('PRAGMA user_version').fetchone()[0]==0


def test_installer_invalid_last_entry_transaction(glossary,tmp_path):
    from hashlib import sha256
    manifest=json.loads((FIXTURE/'manifest.json').read_text('utf-8'))
    rows=[dict(source_term=f'part {i}',target_term=f'деталь {i}',source_language='en',target_language='ru',domain='automotive') for i in range(99)]
    rows.append(dict(source_term='invalid',target_term='',source_language='en',target_language='ru',domain='automotive'))
    data=('\n'.join(json.dumps(r) for r in rows)+'\n').encode()
    manifest.update(format='TreeTranslate.tglossary',schema_version=1,entry_count=100,entries_sha256=sha256(data).hexdigest())
    path=tmp_path/'invalid.tglossary'
    with ZipFile(path,'w') as z:z.writestr('manifest.json',json.dumps(manifest));z.writestr('entries.jsonl',data)
    with pytest.raises(InvalidGlossary):install_pack(glossary.db,path,trusted=True)
    assert not list_packs(glossary.db) and stats(glossary)['entries_total']==0


def test_forbidden_only_checks_without_replacement(glossary):
    add(glossary,'coolant','кондиционер',mode='FORBIDDEN')
    req=TranslationRequest('Replace coolant.','en','ru')
    router=Mock();router.translate.return_value=TranslationResult('Замените антифриз.','en','ru','fake','cpu',0,'test',False,'id')
    assert glossary.translate(req,router,Event()).constraint_status=='forbidden_checked'
    router.translate.assert_called_once()
    assert not glossary.last_warning


def test_masked_model_error_and_cancel(glossary):
    from app.engine.errors import InputTooLongError,TranslationCancelledError
    add(glossary)
    req=TranslationRequest('Replace connector.','en','ru');router=Mock()
    result=TranslationResult('Перевод','en','ru','fake','cpu',0,'test',False,'id')
    router.translate.side_effect=[InputTooLongError(),result]
    assert glossary.translate(req,router,Event()).constraint_status=='fallback_unconstrained'
    router.translate.side_effect=TranslationCancelledError()
    with pytest.raises(TranslationCancelledError):glossary.translate(req,router,Event())


def test_backend_only_ignores_both_knowledge_layers(glossary,tmp_path):
    tm=TranslationMemoryEngine(tmp_path/'tm.db');tm.remember_translation('connector','штекер','en','ru');add(glossary)
    router=TranslationRouter({});router.translate=Mock(return_value=TranslationResult('Модель','en','ru','fake','cpu',0,'test',False,'id'))
    engine=TranslationKnowledgeEngine(router,tm,glossary)
    try:
        assert engine.translate(TranslationRequest('connector','en','ru'),backend_only='argos').translated_text=='Модель'
        assert router.translate.call_args.kwargs['backend_only']=='argos'
    finally:engine.shutdown()


def test_suppressed_builtin_sends_original_to_model(glossary,tmp_path):
    b=GlossaryEngine(tmp_path/'builtin.db');add(b)
    g=GlossaryEngine(glossary.db.path,builtin_paths=[b.db.path]);g.repository.suppress('connector','en','ru')
    router=Mock();router.translate.return_value=TranslationResult('Перевод','en','ru','fake','cpu',0,'test',False,'id')
    g.translate(TranslationRequest('Replace connector.','en','ru'),router,Event())
    assert router.translate.call_args.args[0].text=='Replace connector.'


def test_keep_product_names_and_atoms(glossary):
    for text in ['GDS','ITM','IVT','PS4','Xbox','M10','ISO 9001']:
        add(glossary,text,text,mode='KEEP')
        assert glossary.full_segment(TranslationRequest(text,'en','ru')).translated_text==text
    text='GDS ITM IVT 6.6 45–60% 20'
    plan=glossary.constraints(text,'en','ru')
    restored=glossary.codec.restore(plan.text,plan)
    assert validate_result(text,restored)==text
