from dataclasses import asdict,replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest

from app.glossary.cache_plan import GlossaryCachePlan,GIB,MIB
from app.glossary.hot_cache import ByteLRU,ABSENT
from app.glossary.database import Database
from app.glossary.engine import GlossaryEngine
from app.glossary.repository import Repository
from app.glossary.normalization import mapped,normalize,configure_cache,cache_info
from app.glossary.models import GlossaryEntry,TermMatch
from app.engine.types import TranslationRequest


@pytest.mark.parametrize('ram',[8,16,32,64])
def test_resource_plan_headroom_and_lookup_invariance(tmp_path,ram):
    plan=GlossaryCachePlan.build(ram*GIB,int(ram*.75*GIB),256*MIB,100*MIB,256*MIB)
    assert 0<=plan.lexical_bytes<=256*MIB
    assert plan.lexical_bytes+plan.normalization_bytes+plan.document_prefetch_bytes<=int(ram*.75*GIB)-plan.reserve_bytes
    assert plan.prefetch_batch_items<=256
    g=GlossaryEngine(tmp_path/'terms.db');g.lexical.resize(plan.lexical_bytes)
    g.remember_term('冷却液','охлаждающая жидкость','zh','ru')
    a=g.lookup('更换冷却液','zh','ru');b=g.lookup('更换冷却液','zh','ru')
    assert a==b and a[0].entry.target_term=='охлаждающая жидкость'
    g.close()


@pytest.mark.parametrize('available,process',[(-1,0),(0,0),(GIB,20*GIB)])
def test_planner_shrinks_under_pressure(available,process):
    p=GlossaryCachePlan.build(8*GIB,available,process,100*MIB,256*MIB)
    assert p.lexical_bytes==p.normalization_bytes==p.document_prefetch_bytes==p.prefetch_batch_items==0


def test_normalization_empty_and_offset_copy():
    configure_cache(2*MIB)
    first=mapped('Ａ café\u0301  B',fold=True);first[1].clear()
    assert mapped('Ａ café\u0301  B',fold=True)[1]
    assert normalize(' Ａ   B ',fold=True)=='a b'
    normalize('');before=cache_info()['computations'];assert normalize('')==''
    assert cache_info()['computations']==before


def test_normalization_byte_accounting_preserves_surrogates():
    from app.glossary.normalization import _mapped_uncached
    for text in ['\ud800','Ａ\udfff B','\ud800\udfff']:
        assert normalize(text,fold=True)==_mapped_uncached(text,fold=True)[0].strip()


def test_disabled_pack_closes_persistent_handle_and_reenable_is_fresh(tmp_path):
    pack=Database(tmp_path/'pack.db');Repository(pack).remember_term('term','термин','en','ru')
    g=GlossaryEngine(tmp_path/'user.db')
    with g.db.connect(write=True) as con:
        con.execute('INSERT INTO packs VALUES(?,?,?,?,?)',('pack','1',str(pack.path),1,'{}'))
    assert g.lookup('term','en','ru')[0].store=='pack'
    retained=g._pack_databases[str(pack.path)]
    with g.db.connect(write=True) as con:con.execute('UPDATE packs SET enabled=0')
    assert g.lookup('term','en','ru')==()
    assert not g._pack_databases and retained._local.connection is None
    with g.db.connect(write=True) as con:con.execute('UPDATE packs SET enabled=1')
    assert g.lookup('term','en','ru')[0].store=='pack'
    assert g._pack_databases[str(pack.path)] is not retained
    g.close()


def test_byte_lru_negative_capacity_and_shrink():
    c=ByteLRU(100,2);c.put('a',(),40);c.put('b',('b',),40)
    assert c.get('a')==()
    c.put('c',('c',),40);assert c.get('b') is ABSENT
    assert c.summary()['negative_hits']==1
    c.resize(0);assert not c.values and c.bytes==0


def test_thread_local_connections_transactions_and_external_revision(tmp_path):
    db=Database(tmp_path/'terms.db',persistent_reads=True);repo=Repository(db)
    repo.remember_term('one','один','en','ru')
    first=db.revision_state()
    with db.connect() as a:
        with db.connect() as nested:assert nested is not a
    with db.connect() as b:assert b is a
    with sqlite3.connect(db.path) as other:other.execute("UPDATE entries SET target_term='новый' WHERE source_term='one'")
    second=db.revision_state();assert second!=first and second[1]>first[1]
    with db.connect() as own:own.execute("UPDATE entries SET target_term='свой' WHERE source_term='one'")
    third=db.revision_state();assert third[1]>second[1]
    with ThreadPoolExecutor(max_workers=1) as pool:
        def worker():
            with db.connect() as con:different=con is not a
            db.close();return different
        assert pool.submit(worker).result()
    db.close();assert db.revision_state()[0]!=third[0]
    db.close()


def test_failed_transaction_is_rolled_back_before_reuse(tmp_path):
    db=Database(tmp_path/'terms.db',persistent_reads=True);repo=Repository(db)
    repo.remember_term('one','один','en','ru')
    with pytest.raises(RuntimeError):
        with db.connect() as con:
            con.execute("UPDATE entries SET target_term='wrong'");raise RuntimeError('cancel')
    with db.connect() as con:assert con.execute('SELECT target_term FROM entries').fetchone()[0]=='один'
    db.close()


def test_negative_cache_external_add_and_source_switch(tmp_path):
    g=GlossaryEngine(tmp_path/'terms.db');assert g.lookup('missing','en','ru')==()
    assert g.lookup('missing','en','ru')==()
    Repository(Database(g.db.path)).remember_term('missing','новый','en','ru')
    assert g.lookup('missing','en','ru')[0].entry.target_term=='новый'
    replacement=Database(tmp_path/'other.db');Repository(replacement).remember_term('missing','другой','en','ru')
    g.db.path=replacement.path
    assert g.lookup('missing','en','ru')[0].entry.target_term=='другой'
    g.close()


def test_context_domain_pair_placeholder_and_user_override(tmp_path):
    builtin=Database(tmp_path/'builtin.db');Repository(builtin).insert_many([
        dict(source_term='coolant',target_term='встроенный',source_language='en',target_language='ru',status='BUILTIN'),
        dict(source_term='driver',target_term='водитель',source_language='en',target_language='ru',domain='automotive',status='BUILTIN'),
        dict(source_term='driver',target_term='драйвер',source_language='en',target_language='ru',domain='software',status='BUILTIN'),
        dict(source_term='label',target_term='заголовок',source_language='en',target_language='ru',context='heading',status='BUILTIN')])
    g=GlossaryEngine(tmp_path/'user.db',builtin_paths=[builtin.path])
    assert g.lookup('label','en','ru')==()
    assert g.lookup('label','en','ru',context='heading')[0].entry.target_term=='заголовок'
    assert g.lookup('driver','en','ru','automotive')[0].entry.target_term=='водитель'
    assert g.lookup('driver','en','ru','software')[0].entry.target_term=='драйвер'
    assert g.lookup('driver','ru','en')==()
    g.remember_term('coolant','пользовательский','en','ru')
    assert g.lookup('coolant','en','ru')[0].store=='user'
    a=g.constraints('coolant','en','ru');b=g.constraints('ZXQ0001QXZ coolant','en','ru')
    assert a.mapping[0][0]=='ZXQ0001QXZ' and b.mapping[0][0]=='ZXQ0002QXZ'
    g.close()


def test_snapshot_identity_separates_negative_and_positive(tmp_path):
    g=GlossaryEngine(tmp_path/'user.db')
    entry=GlossaryEntry('冷却液','охлаждающая жидкость','zh','ru',status='BUILTIN',trust=.8)
    no=SimpleNamespace(signature='revision-A',stores=(),candidates=lambda *a:())
    yes=SimpleNamespace(signature='revision-B',stores=(),candidates=lambda *a:(TermMatch(0,3,entry,'builtin:0'),))
    assert g.lookup('冷却液','zh','ru',snapshot=no)==()
    assert g.lookup('冷却液','zh','ru',snapshot=yes)[0].entry==entry
    g.close()


def test_pressure_clears_bounded_caches_without_changing_matches(tmp_path,monkeypatch):
    import psutil
    g=GlossaryEngine(tmp_path/'user.db');g.remember_term('term','термин','en','ru')
    reference=g.lookup('term','en','ru');g._pressure_checks=127
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=0))
    assert g.lookup('term','en','ru')==reference
    assert g.lexical.bytes==g.lexical.budget==0
    g.close()


def test_prefetch_keeps_rows_unselected_and_invalidates_after_write(tmp_path):
    g=GlossaryEngine(tmp_path/'terms.db')
    g.remember_term('coolant','жидкость','en','ru')
    g.cache_plan=replace(g.cache_plan,document_prefetch_bytes=MIB,prefetch_batch_items=16)
    g.lexical.resize(MIB)
    expected=g.lookup('coolant','en','ru');g.cache.clear()
    before=sqlite3.connect(g.db.path).execute('SELECT revision FROM metadata').fetchone()[0]
    g.prefetch(['coolant','missing','coolant'],'en','ru')
    assert not g.cache and g.lexical.stats['prefetch_unique_sources']==2
    assert g.lookup('coolant','en','ru')==expected
    with sqlite3.connect(g.db.path) as con:
        assert con.execute('SELECT revision FROM metadata').fetchone()[0]==before
    g.remember_term('missing','новый','en','ru')
    assert g.lookup('missing','en','ru')[0].entry.target_term=='новый'
    g.close()


def test_changed_derived_forms_do_not_reuse_final_selection(tmp_path):
    from collections import Counter
    import json
    builtin=Database(tmp_path/'builtin.db')
    Repository(builtin).insert_many([dict(source_term='冷却液',target_term='охлаждающая жидкость',
        source_language='zh',target_language='ru',status='BUILTIN',
        notes=json.dumps({'review_status':'VERIFIED','concept_id':'coolant'}))])
    g=GlossaryEngine(tmp_path/'user.db',builtin_paths=[builtin.path])
    forms={'冷却液':{'base':'охлаждающая жидкость','nominative':'охлаждающая жидкость'}}
    router=SimpleNamespace(slot_forms=forms,metrics=Counter())
    request=TranslationRequest('高压冷却液','zh','ru',context_router=router)
    a=g.lookup(request.text,'zh','ru',request=request)
    forms['冷却液']['nominative']='жидкость охлаждения'
    b=g.lookup(request.text,'zh','ru',request=request)
    assert a!=b
    g.close()
