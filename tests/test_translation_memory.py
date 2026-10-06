from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import Mock
import json
import socket
import sqlite3

import pytest

from app.translation_memory.engine import TranslationMemoryEngine
from app.translation_memory.models import Status
from app.translation_memory.errors import InvalidMemoryData, MemoryUnavailable
from app.translation_memory.database import Database
from app.translation_memory.repository import Repository
from app.translation_memory.normalization import normalize
from app.translation_memory.importer import import_memory, import_tmx
from app.translation_memory.exporter import export_memory, export_tmx, export_dataset
from app.translation_memory.maintenance import backup, restore, integrity, duplicates, optimize
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from app.engine.router.translation_router import TranslationRouter
from app.engine.types import TranslationRequest, TranslationResult
from app.engine.errors import TranslationCancelledError


@pytest.fixture
def tm(tmp_path):
    return TranslationMemoryEngine(tmp_path/'memory.db')


def remember(tm, source='Disconnect the ITM connector.', target='Отсоедините разъём ITM.', **kw):
    return tm.remember_translation(source, target, 'en', 'ru', **kw)


def test_creation_migration_and_indexes(tm):
    assert tm.lookup('missing', 'en', 'ru') is None
    assert integrity(tm.db) == ['ok']
    with tm.db.connect() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0] == 1
        assert c.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert c.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        for col, index in [('source_hash','tm_exact'),('normalized_hash','tm_normalized')]:
            plan = str([tuple(r) for r in c.execute(f'EXPLAIN QUERY PLAN SELECT * FROM units WHERE source_language=? AND target_language=? AND {col}=?', ('en','ru','x'))])
            assert index in plan and 'SCAN units' not in plan
    other = TranslationMemoryEngine(tm.db.path)
    assert other.stats()['total_units'] == 0


@pytest.mark.parametrize('source,variant,target,language', [
    ('Save the file.', '  Save\n the  file. ', 'Сохраните файл.', 'en'),
    ('Click “save”.', 'Click "save".', 'Нажмите «сохранить».', 'en'),
    ('保存 文件。', '保存\n文件。', 'Сохраните файл.', 'zh'),
    ('Сохраните файл.', 'Сохраните\n файл.', 'Save the file.', 'ru'),
    ('Save Ａ file.', 'Save A file.', 'Сохраните файл.', 'en'),
])
def test_normalization(tm, source, variant, target, language):
    target_language = 'en' if language == 'ru' else 'ru'
    tm.remember_translation(source, target, language, target_language)
    match = tm.lookup(variant, language, target_language)
    assert match and match.reusable and match.match_type == 'normalized'


@pytest.mark.parametrize('original,changed', [('ITM-1','ITM-2'),('6.6 liters','5.5 liters'),
                                           ('45–60%','40–60%'),('Save.','Save?'),('file','File')])
def test_distinctions(tm, original, changed):
    remember(tm, original, original)
    hit = tm.lookup(changed,'en','ru')
    assert hit is None or not hit.reusable
    assert normalize(original) != normalize(changed)


@pytest.mark.parametrize('target', ['Отсоедините разъём.', 'GDS ITM 6.6 40–60%', 'GDS 6.6 45–60%'])
def test_fidelity_applies_to_confirmations(tm,target):
    remember(tm,'GDS ITM IVT 6.6 45–60%',target)
    assert not tm.lookup('GDS ITM IVT 6.6 45–60%','en','ru').reusable


def test_complete_identifier_not_just_numbers(tm):
    remember(tm, 'Connect itm-1.', 'Подключите abc-1.')
    assert not tm.lookup('Connect itm-1.','en','ru').reusable


def test_exact_no_silent_learning_and_router_bypass(tm):
    router = TranslationRouter({})
    router.translate = Mock(return_value=TranslationResult('Отсоедините разъём ITM.','en','ru','fake','cpu',0,'test',False,'id'))
    engine = TranslationKnowledgeEngine(router,tm)
    request = TranslationRequest('Disconnect the ITM connector.','en','ru')
    try:
        assert engine.translate(request).backend == 'fake'
        assert tm.stats()['total_units'] == 0
        uid = remember(tm)
        result = engine.translate(request)
        assert result.backend == 'translation_memory'
        assert router.translate.call_count == 1
        assert result.translated_text == 'Отсоедините разъём ITM.'
        assert next(tm.repository.rows())['use_count'] == 1
        assert uid == tm.lookup(request.text,'en','ru').translation_unit_id
    finally:
        engine.shutdown()


def test_trust_duplicates_domain_and_alternatives(tm):
    first = remember(tm, 'driver', 'драйвер', domain='software')
    assert remember(tm,'driver','драйвер',domain='software') == first
    remember(tm,'driver','водитель',domain='automotive')
    remember(tm,'driver','оператор')
    assert tm.lookup('driver','en','ru','software').target == 'драйвер'
    assert tm.lookup('driver','en','ru','automotive').target == 'водитель'
    assert tm.lookup('driver','en','ru').target == 'оператор'
    assert tm.lookup('driver','ru','en') is None
    assert tm.stats()['total_units'] == 3
    assert duplicates(tm.db) == []


def test_context_and_status_change_invalidates_cache(tm):
    uid = remember(tm,context='warning')
    assert tm.lookup('Disconnect the ITM connector.','en','ru') is None
    assert tm.lookup('Disconnect the ITM connector.','en','ru',context='warning').reusable
    tm.repository.status(uid,Status.REJECTED)
    assert tm.lookup('Disconnect the ITM connector.','en','ru',context='warning') is None
    tm.repository.status(uid,Status.REVIEWED)
    assert tm.lookup('Disconnect the ITM connector.','en','ru',context='warning').reusable


def test_unconfirmed_not_used(tm):
    remember(tm,confirmed=False)
    assert tm.lookup('Disconnect the ITM connector.','en','ru') is None


def test_safe_explicit_placeholder(tm):
    tm.remember_template('Fill {NUMBER_1} liters of coolant.', 'Залейте {NUMBER_1} л охлаждающей жидкости.', 'en','ru')
    match = tm.lookup('Fill 6.6 liters of coolant.','en','ru')
    assert match.match_type == 'placeholder' and match.reusable
    assert match.target == 'Залейте 6.6 л охлаждающей жидкости.'
    assert tm.lookup('Fill 6.6 to 7.0 liters of coolant.','en','ru') is None
    with pytest.raises(InvalidMemoryData):
        tm.remember_template('Fill {NUMBER_1} then {NUMBER_1}.','Залейте {NUMBER_1}.','en','ru')


def test_literals_never_implicitly_become_templates(tm):
    remember(tm,'Fill 5.5 liters of coolant.','Залейте 5.5 л охлаждающей жидкости.')
    hit = tm.lookup('Fill 6.6 liters of coolant.','en','ru')
    assert not hit or not hit.reusable


def test_fuzzy_candidates_and_explicit_policy(tm):
    remember(tm,'Save the configuration file.','Сохраните файл конфигурации.')
    hit = tm.lookup('Save configuration file.','en','ru')
    assert hit and hit.match_type == 'fuzzy' and 0 < hit.score < 1 and not hit.reusable
    other = TranslationMemoryEngine(tm.db.path,config={'fuzzy_reuse':True,'fuzzy_reuse_threshold':.8})
    assert other.lookup('Save configuration file.','en','ru').reusable


def test_chinese_fuzzy(tm):
    tm.remember_translation('请在启动之前保存文件。','Сохраните файл перед запуском.','zh','ru')
    hit = tm.lookup('请在启动前保存文件。','zh','ru')
    assert hit and hit.match_type == 'fuzzy' and not hit.reusable


def test_cache_batch_and_external_writes(tm):
    tm.config['cache_size'] = 3
    assert tm.lookup_many(['one','two','three','four'],'en','ru') == [None]*4
    assert len(tm.cache) == 3
    other = TranslationMemoryEngine(tm.db.path)
    remember(other,'one','один')
    assert tm.lookup('one','en','ru').target == 'один'
    batch = tm.lookup_many(['one']*500,'en','ru')
    assert all(m.target == 'один' for m in batch)
    assert len(tm.cache) <= 3


def test_builtin_readonly_and_user_priority(tm,tmp_path):
    builtin = TranslationMemoryEngine(tmp_path/'builtin.db')
    remember(builtin,'driver','оператор')
    memory = TranslationMemoryEngine(tm.db.path,builtin_path=builtin.db.path)
    assert memory.lookup('driver','en','ru').store == 'builtin'
    remember(memory,'driver','водитель')
    assert memory.lookup('driver','en','ru').target == 'водитель'
    with pytest.raises(MemoryUnavailable):
        Repository(memory.builtin).status(1,Status.REJECTED)


def test_import_export_trust_and_dataset(tm,tmp_path):
    remember(tm,source_document='C:/private/document.pdf')
    remember(tm,'Other','Другое',confirmed=False)
    path = tmp_path/'memory.tmemory'
    assert export_memory(tm.repository,path) == 2
    assert 'private' not in path.read_text('utf-8')
    dest = TranslationMemoryEngine(tmp_path/'dest.db')
    assert import_memory(dest.repository,path) == 2
    assert dest.lookup('Disconnect the ITM connector.','en','ru') is None
    import_memory(dest.repository,path,trusted=True)
    assert dest.lookup('Disconnect the ITM connector.','en','ru').reusable
    assert dest.stats()['confirmed_units'] == 0
    data = tmp_path/'dataset.jsonl'
    assert export_dataset(tm.repository,data) == 1
    assert len(data.read_text('utf-8').splitlines()) == 1


def test_import_atomic_rollback(tm,tmp_path):
    remember(tm)
    path = tmp_path/'bad.tmemory'
    export_memory(tm.repository,path)
    with path.open('a') as f:
        f.write('{"malformed":true}\n')
    dest = TranslationMemoryEngine(tmp_path/'dest.db')
    with pytest.raises(InvalidMemoryData):
        import_memory(dest.repository,path,trusted=True)
    assert dest.stats()['total_units'] == 0


def test_tmx_roundtrip_and_entities(tm,tmp_path):
    remember(tm)
    path = tmp_path/'memory.tmx'
    assert export_tmx(tm.repository,path) == 1
    dest = TranslationMemoryEngine(tmp_path/'dest.db')
    assert import_tmx(dest.repository,path,trusted=True) == 1
    assert dest.lookup('Disconnect the ITM connector.','en','ru').reusable
    path.write_text('<!DOCTYPE tmx [<!ENTITY x SYSTEM "file:///private">]><tmx/>','utf-8')
    with pytest.raises(InvalidMemoryData):
        import_tmx(dest.repository,path)


def test_backup_restore_and_maintenance(tm,tmp_path):
    remember(tm)
    path = tmp_path/'backup.db'
    backup(tm.db,path)
    remember(tm,'Other','Другое')
    tm.lookup('Other','en','ru')
    previous = restore(tm.db,path)
    assert previous.exists()
    assert tm.stats()['total_units'] == 1
    assert tm.lookup('Other','en','ru') is None
    assert integrity(tm.db) == ['ok']
    optimize(tm.db,vacuum=True)
    assert integrity(tm.db) == ['ok']


@pytest.mark.parametrize('condition',['corrupt','future','locked'])
def test_unavailable_falls_back_without_deleting(tm,condition):
    locker = None
    if condition == 'corrupt':
        tm.db.path.write_bytes(b'private broken database')
    elif condition == 'future':
        with sqlite3.connect(tm.db.path) as c:
            c.execute('PRAGMA user_version=999')
    else:
        locker = sqlite3.connect(tm.db.path)
        locker.execute('BEGIN EXCLUSIVE')
    messages = []
    tm.warning = messages.append
    try:
        assert tm.lookup('private source','en','ru') is None
        assert tm.disabled and messages and tm.db.path.exists()
        assert 'private source' not in messages[0]
        if condition == 'corrupt':
            assert tm.db.path.read_bytes() == b'private broken database'
    finally:
        if locker:
            locker.close()


def test_concurrency(tm):
    def work(i):
        other = TranslationMemoryEngine(tm.db.path)
        remember(other,f'Item {i}.',f'Элемент {i}.')
        return other.lookup(f'Item {i}.','en','ru').reusable
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(work,range(40)))
    assert tm.stats()['total_units'] == 40
    assert integrity(tm.db) == ['ok']


def test_offline_and_log_privacy(tm,monkeypatch,caplog):
    def fail(*a,**kw):
        raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket,'create_connection',fail)
    monkeypatch.setattr(socket,'getaddrinfo',fail)
    remember(tm,'Secret private text.','Секретный текст.')
    assert tm.lookup('Secret private text.','en','ru').reusable
    assert 'Secret private text' not in caplog.text


def test_cancelled_hit_never_returns(tm):
    remember(tm)
    router = TranslationRouter({})
    event = Event();event.set()
    try:
        with pytest.raises(TranslationCancelledError):
            TranslationKnowledgeEngine(router,tm).translate(TranslationRequest('Disconnect the ITM connector.','en','ru'),event)
    finally:
        router.shutdown()


@pytest.mark.parametrize('source,target', [('Value -5.', 'Значение 5.'),
    ('Value 45–60%.','Значение 45 60%.'),('Value 45%.','Значение 45.'),
    ('Open www.example.com','Откройте сайт.')])
def test_signs_ranges_percentages_and_urls(tm,source,target):
    remember(tm,source,target)
    assert not tm.lookup(source,'en','ru').reusable


def test_migration_failure_preserves_unknown_database(tm):
    with sqlite3.connect(tm.db.path) as con:
        con.execute('CREATE TABLE units (private_data TEXT)')
        con.execute("INSERT INTO units VALUES ('preserve')")
    assert tm.lookup('hello','en','ru') is None
    with sqlite3.connect(tm.db.path) as con:
        assert con.execute('SELECT private_data FROM units').fetchone()[0] == 'preserve'
        assert con.execute('PRAGMA user_version').fetchone()[0] == 0


def test_invalid_import_fields_and_future_package(tm,tmp_path):
    with pytest.raises(InvalidMemoryData):
        tm.repository.insert_many([{'unexpected sql)': 'value'}])
    path = tmp_path/'future.tmemory'
    path.write_text(json.dumps({'format':'TreeTranslate.tmemory','version':99,'schema_version':99})+'\n','utf-8')
    with pytest.raises(InvalidMemoryData):
        import_memory(tm.repository,path)


def test_corrupt_memory_router_still_translates(tm):
    tm.db.path.write_bytes(b'broken')
    router = TranslationRouter({})
    router.translate = Mock(return_value=TranslationResult('Привет','en','ru','fake','cpu',0,'test',False,'id'))
    try:
        assert TranslationKnowledgeEngine(router,tm).translate(TranslationRequest('Hello','en','ru')).translated_text == 'Привет'
        router.translate.assert_called_once()
    finally:
        router.shutdown()


def test_rejected_import_not_revived(tm,tmp_path):
    uid = remember(tm)
    path = tmp_path/'memory.tmemory'
    export_memory(tm.repository,path)
    tm.repository.status(uid,Status.REJECTED)
    import_memory(tm.repository,path,trusted=True)
    assert tm.lookup('Disconnect the ITM connector.','en','ru') is None


def test_bad_backup_cannot_replace_memory(tm,tmp_path):
    remember(tm)
    path = tmp_path/'wrong.db'
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA user_version=99')
    with pytest.raises(InvalidMemoryData):
        restore(tm.db,path)
    assert tm.stats()['total_units'] == 1


def test_basic_tmx_rejects_inline_codes_atomically(tm,tmp_path):
    path = tmp_path/'inline.tmx'
    path.write_text('''<tmx version="1.4"><header srclang="en"/><body><tu>
      <tuv xml:lang="en"><seg>Click <bpt>code</bpt>here</seg></tuv>
      <tuv xml:lang="ru"><seg>Нажмите</seg></tuv></tu></body></tmx>''','utf-8')
    with pytest.raises(InvalidMemoryData):
        import_tmx(tm.repository,path,trusted=True)
    assert tm.stats()['total_units'] == 0
