from copy import deepcopy
import gzip
import json
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile
import pytest

from tools.knowledge_harvester.config import load
from tools.knowledge_harvester.storage import Store
from tools.knowledge_harvester.ingest import ingest
from tools.knowledge_harvester.linking import link
from tools.knowledge_harvester.models import HarvestError
from tools.knowledge_harvester.network import download
from tools.knowledge_harvester.provenance import canonical_json, digest_json, file_hash
from tools.knowledge_harvester.build.packs import build_packs
from tools.knowledge_harvester.build.reports import report, export_queue
from tools.knowledge_harvester.review import import_reviews
from tools.knowledge_harvester.sources import agrovoc, cedict, wiktionary
from app.glossary.engine import GlossaryEngine
from app.glossary.packs import install_pack, disable_pack, enable_pack, remove_pack


def entity(uid='Q900000001', zh='测试冷却液', ru='тестовая жидкость', en='test coolant', parents=('Q900000000',)):
    return {'id':uid,'lastrevid':123,'labels':{k:{'value':v} for k,v in [('zh',zh),('ru',ru),('en',en)] if v},
            'aliases':{'ru':[{'value':'тестовый вариант'}]},
            'claims':{'P279':[{'mainsnak':{'datavalue':{'value':{'id':p}}}} for p in parents]}}


def metadata(source_id='test', status='APPROVED_FOR_REDISTRIBUTION', license_id='CC0-1.0'):
    return dict(source_id=source_id,source_url='https://example.org/synthetic-fixture',acquired_at='2026-09-24T00:00:00Z',revision='fixture-v1',
                license=license_id,redistribution_status=status,license_url='https://creativecommons.org/publicdomain/zero/1.0/',
                license_checked_at='2026-09-24',attribution='TreeTranslate synthetic tests only; not production terms',
                independence_group=source_id,languages=['zh','ru','en'])


@pytest.fixture
def pipeline(tmp_path):
    store=Store(tmp_path/'harvest.db');store.source_add(metadata())
    config=load();config['domains']={'automotive':{'roots':['wikidata:Q900000000'],'keywords':['coolant']},
                                   'metallurgy':{'roots':['wikidata:Q900000010'],'keywords':['steel']}}
    return store,config


def feed(pipeline,tmp_path,rows,source='test',name='input.jsonl',**kwargs):
    store,config=pipeline;path=tmp_path/name
    path.write_text(''.join(canonical_json(r)+'\n' for r in rows),'utf-8')
    return ingest(store,path,source,'wikidata',config,**kwargs)


def candidates(store):
    with store.connect() as con:return [json.loads(r[0]) for r in con.execute('SELECT payload FROM candidates ORDER BY id')]


def test_pivot_v2_alias_and_gloss_evidence_without_alias_pollution(pipeline,tmp_path):
    store,config=pipeline;config['pivot_version']=2
    source=entity('Q900000001',zh='测试甲',ru='',en='unused name')
    source['aliases']={'en':[{'value':'test connector'}],'zh-hant':[{'value':'測試甲'}]}
    target=entity('Q900000002',zh='测试乙',ru='тестовая связь',en='test connector')
    feed(pipeline,tmp_path,[source,target]);link(store,config)
    pivots=[c for c in candidates(store) if c['link_type'].startswith('ENGLISH_PIVOT')]
    assert len(pivots)==1 and pivots[0]['status']=='REVIEW'
    assert pivots[0]['zh_variants']==['測試甲']
    assert '测试乙' not in pivots[0]['zh_variants']
    assert pivots[0]['link_evidence']['english_matches'][0]['source']['kind']=='alias'
    direct=next(c for c in candidates(store) if c['zh']=='测试乙' and c['link_type']=='DIRECT_CONCEPT')
    assert direct['status']=='VERIFIED'


@pytest.mark.parametrize('meaning',['driver','seal','bearing','mold','cell','bus','port','terminal','current'])
def test_pivot_v2_never_chooses_first_ambiguous_meaning(pipeline,tmp_path,meaning):
    store,config=pipeline;config['pivot_version']=2
    feed(pipeline,tmp_path,[entity('Q900000001',zh='测试甲',ru='',en=meaning),
        entity('Q900000002',zh='测试乙',ru='первое значение',en=meaning),
        entity('Q900000003',zh='测试丙',ru='второе значение',en=meaning)])
    link(store,config)
    pivots=[c for c in candidates(store) if c['link_type'].startswith('ENGLISH_PIVOT')]
    assert len(pivots)==2
    assert all(c['status']=='REVIEW' and c['link_type']=='ENGLISH_PIVOT_AMBIGUOUS' for c in pivots)
    assert all(len(c['link_evidence']['competing_concepts'])==2 for c in pivots)


def test_pivot_gloss_qualifiers_and_domain_word_boundaries():
    from tools.knowledge_harvester.linking.pivot import lexemes
    from tools.knowledge_harvester.domains import keyword_matches
    r=dict(labels={},aliases={},definitions=['(automotive) idling; idle speed','radiator (for cooling an engine)','CL:把[ba3]'])
    found=list(lexemes(r))
    assert [v['term'] for v in found]==['idling','idle speed','radiator']
    assert found[0]['qualifiers']==['automotive']
    assert found[-1]['qualifiers']==['for cooling an engine']
    assert not keyword_matches('car','carbohydrate')
    assert keyword_matches('car','a car engine')
    assert keyword_matches('ship','selected ships')
    assert keyword_matches('company','several companies')
    assert not keyword_matches('ship','friendship')


def test_refinement_preserves_all_frozen_trust_settings_and_unicode():
    previous=load('tools/knowledge_harvester/expansion_policy.json')
    current=load('tools/knowledge_harvester/refinement_policy.json')
    assert current.pop('pivot_version')==2
    assert current==previous
    assert '列表' in current['review_label_markers']


@pytest.mark.parametrize('label',['ships','lightships','lifeboats','baitboats'])
def test_scope_gate_keeps_nautical_compounds_in_review(label):
    from tools.knowledge_harvester.quality import assess
    from tools.knowledge_harvester.models import LinkType
    config=load('tools/knowledge_harvester/refinement_policy.json')
    record=dict(source='test',labels={'zh':'测试船','ru':'судно','en':label},descriptions={},metadata={})
    score,status,reasons=assess('测试船','судно',LinkType.DIRECT,[{'kind':'taxonomy'}],[record],{'test':metadata()},config,[],False,'automotive')
    assert status=='REVIEW' and 'domain_scope_requires_review' in reasons


def test_refinement_conflict_categories_and_queue_priority():
    from tools.knowledge_harvester.refinement_report import conflict_category,priority
    a=dict(id='a',zh='测试甲',ru='Пайка',domain='metallurgy',zh_variants=[],score=90)
    assert conflict_category(a,dict(a,ru='пайка'))=='case_normalization_collision'
    assert conflict_category(a,dict(a,ru='другое'))=='semantic_ambiguity_requires_review'
    assert conflict_category(a,dict(a,zh='测试乙',ru='другое'))=='alias_collision'
    assert conflict_category(a,dict(a,domain='automotive'))=='domain_separation'
    assert conflict_category(a,dict(a,id='b'))=='duplicate_provenance'
    # Requested corpus terms lead even when they have no domain or low score.
    important=dict(a,zh='冷却液',domain='unclassified',score=0)
    assert priority(important,{})<priority(a,{'测试甲':100})


def test_pivot_v2_matching_chinese_is_support_not_verification(pipeline,tmp_path):
    store,config=pipeline;config['pivot_version']=2
    # Same Chinese key and one English sense remain review without a shared ID.
    feed(pipeline,tmp_path,[entity('Q900000001',zh='测试甲',ru='',en='sense'),
                            entity('Q900000002',zh='测试甲',ru='значение',en='sense')])
    link(store,config)
    pivot=next(c for c in candidates(store) if c['link_type'].startswith('ENGLISH_PIVOT'))
    assert pivot['status']=='REVIEW'
    assert pivot['link_evidence']['quality_tier']=='REVIEW_HIGH'
    assert pivot['link_evidence']['shared_zh']==['测试甲']


@pytest.mark.parametrize('target_zh,expected',[('测试乙','VERIFIED'),('测试甲','REVIEW')])
def test_retrieval_hypothesis_vs_source_attested_chinese_conflict(pipeline,tmp_path,target_zh,expected):
    store,config=pipeline;config['pivot_version']=2
    feed(pipeline,tmp_path,[entity('Q900000001',zh='测试甲',ru='прямое значение',en='specific sense'),
        entity('Q900000002',zh=target_zh,ru='другая гипотеза',en='ambiguous sense'),
        entity('Q900000003',zh='测试甲',ru='',en='ambiguous sense')])
    link(store,config)
    direct=next(c for c in candidates(store) if c['concept']=='wikidata:Q900000001')
    assert direct['status']==expected
    pivot=next(c for c in candidates(store) if c['link_type'].startswith('ENGLISH_PIVOT'))
    assert pivot['status']=='REVIEW'
    with store.connect() as con:
        weak=con.execute("SELECT count(*) FROM conflicts WHERE reason='retrieval_only_challenge'").fetchone()[0]
    assert bool(weak)==(target_zh=='测试乙')


def test_targeted_mapping_requires_network_and_explicit_mapping(pipeline,tmp_path,monkeypatch):
    from tools.knowledge_harvester.complete_mappings import complete
    store,config=pipeline
    with pytest.raises(HarvestError,match='allow-network'):complete(store,tmp_path/'network')
    source=metadata('agro');source['license']='CC-BY-4.0';store.source_add(source)
    raw={'@id':'https://example.org/concept','http://www.w3.org/2004/02/skos/core#exactMatch':[{'@id':'http://www.wikidata.org/entity/Q123'}]}
    path=tmp_path/'agro.jsonl';path.write_text(canonical_json(raw)+'\n','utf-8');ingest(store,path,'agro','agrovoc',config)
    calls=[]
    def cached(url,path,key,allow):
        assert 'Q123' in url and 'search' not in url and 'info' in url and allow
        calls.append(url);data={'entities':{'Q123':entity('Q123')}};path.write_text(canonical_json(data),'utf-8');return path,data
    monkeypatch.setattr('tools.knowledge_harvester.complete_mappings.cached_json',cached)
    result=complete(store,tmp_path/'mapped',allow_network=True)
    assert result['requested']==result['received']==1 and len(calls)==1
    source=json.loads((tmp_path/'mapped/source.json').read_text('utf-8'))
    assert source['independence_group']=='wikidata' and source['acquisition']['plan']['evidence']['Q123']
    def without_revision(url,path,key,allow):
        value=entity('Q123');value.pop('lastrevid')
        data={'entities':{'Q123':value}};path.write_text(canonical_json(data),'utf-8');return path,data
    monkeypatch.setattr('tools.knowledge_harvester.complete_mappings.cached_json',without_revision)
    with pytest.raises(HarvestError,match='revision'):complete(store,tmp_path/'bad-revision',allow_network=True)
    assert not (tmp_path/'bad-revision/entities.jsonl').exists()


def test_unapproved_mapping_cannot_supply_taxonomy_proof(pipeline,tmp_path):
    store,config=pipeline;config['pivot_version']=2
    store.source_add(metadata('unknown',status='UNKNOWN'))
    skos='http://www.w3.org/2004/02/skos/core#'
    parent={'@id':'https://example.org/parent',skos+'exactMatch':[{'@id':'http://www.wikidata.org/entity/Q900000000'}]}
    child={'@id':'https://example.org/child',skos+'broader':[{'@id':parent['@id']}],
           skos+'prefLabel':[{'@language':k,'@value':v} for k,v in [('zh','测试'),('ru','термин'),('en','test term')]]}
    for name,source,row in [('parent','unknown',parent),('child','test',child)]:
        path=tmp_path/(name+'.jsonl');path.write_text(canonical_json(row)+'\n','utf-8')
        ingest(store,path,source,'agrovoc',config)
    link(store,config)
    result=next(c for c in candidates(store) if c['zh']=='测试')
    assert result['status']=='REVIEW' and result['domain']=='unclassified'


def test_reverse_pairs_reject_cyrillic_case_collisions(pipeline,tmp_path):
    store,config=pipeline
    feed(pipeline,tmp_path,[entity('Q900000001',zh='测试甲',ru='Пайка'),
                            entity('Q900000002',zh='测试乙',ru='пайка'),
                            entity('Q900000003',zh='测试丙',ru='безопасный термин')])
    link(store,config)
    assert report(store)['statuses']=={'VERIFIED':3}
    built=build_packs(store,config,tmp_path/'packs',reverse=True)
    reverse=next(p for p in built if '-ru-zh-' in p['pack_id'])
    assert reverse['counts']['reverse_conflicts_rejected']==2
    with ZipFile(tmp_path/'packs'/(reverse['pack_id']+'.tglossary')) as archive:
        entries=[json.loads(line) for line in archive.read('entries.jsonl').decode().splitlines()]
    assert [(e['source_term'],e['target_term']) for e in entries]==[('безопасный термин','测试丙')]


def test_direct_pipeline_packs_lifecycle_and_reproducibility(pipeline,tmp_path):
    store,config=pipeline;feed(pipeline,tmp_path,[entity()]);link(store,config)
    assert report(store)['statuses']=={'VERIFIED':1}
    first=build_packs(store,config,tmp_path/'packs1',reverse=True)
    second=build_packs(store,config,tmp_path/'packs2',reverse=True)
    assert [r['sha256'] for r in first]==[r['sha256'] for r in second]
    assert len(first)==2
    pack=next((tmp_path/'packs1').glob('*-zh-ru-*.tglossary'))
    with ZipFile(pack) as archive:
        assert {'NOTICE','LICENSE','README','manifest.json','entries.jsonl'}==set(archive.namelist())
        assert b'input_sha256' in archive.read('NOTICE')
    g=GlossaryEngine(tmp_path/'user.db');install_pack(g.db,pack,trusted=True)
    assert g.lookup('测试冷却液','zh','ru','automotive')
    assert not g.lookup('测试冷却液','zh','ru')
    assert list(g.repository.rows())==[]
    uid=first[0]['pack_id'];disable_pack(g.db,uid)
    assert not g.lookup('测试冷却液','zh','ru','automotive')
    enable_pack(g.db,uid);assert g.lookup('测试冷却液','zh','ru','automotive')
    remove_pack(g.db,uid);assert not g.lookup('测试冷却液','zh','ru','automotive')


@pytest.mark.parametrize('status',['UNKNOWN','NOT_REDISTRIBUTABLE','REVIEW_REQUIRED'])
def test_license_gate_cannot_be_bypassed_by_review(pipeline,tmp_path,status):
    store,config=pipeline;store.source_add(metadata('blocked',status))
    feed(pipeline,tmp_path,[entity()],source='blocked');link(store,config)
    assert report(store)['statuses']=={'REVIEW':1}
    candidate=candidates(store)[0]
    decision=dict(candidate_id=candidate['id'],decision='ACCEPT',reviewer='unit-test',evidence_sha256=digest_json(candidate['provenance']))
    path=tmp_path/'review.jsonl';path.write_text(canonical_json(decision)+'\n','utf-8')
    import_reviews(store,path,config)
    with pytest.raises(HarvestError,match='одобрен'):build_packs(store,config,tmp_path/'blocked')


def test_resume_idempotency_and_config_pin(pipeline,tmp_path):
    store,config=pipeline
    rows=[entity(f'Q90000000{i}',zh=f'测试{i}',ru=f'тест {i}') for i in range(1,4)]
    feed(pipeline,tmp_path,rows,sample=1)
    assert report(store)['raw_records']==1
    path=tmp_path/'input.jsonl';ingest(store,path,'test','wikidata',config,sample=1)
    assert report(store)['raw_records']==2
    changed=deepcopy(config);changed['max_aliases']=32
    with pytest.raises(HarvestError):ingest(store,path,'test','wikidata',changed)
    ingest(store,path,'test','wikidata',config)
    ingest(store,path,'test','wikidata',config)
    assert report(store)['raw_records']==3


def test_input_hash_pin_rejects_changed_source(pipeline,tmp_path):
    store,config=pipeline;source=metadata('pinned');source['input_sha256']='0'*64
    store.source_add(source)
    with pytest.raises(HarvestError,match='SHA256'):
        feed(pipeline,tmp_path,[entity()],source='pinned')
    assert report(store)['raw_records']==0


def test_alias_language_must_be_covered_by_source_license(pipeline,tmp_path):
    store,config=pipeline;source=metadata('limited');source['languages']=['zh','en'];store.source_add(source)
    result=feed(pipeline,tmp_path,[entity(ru='')],source='limited')
    assert result['rejected_this_run']==1 and report(store)['raw_records']==0
    with store.connect() as con:
        assert con.execute('SELECT code FROM errors').fetchone()[0]=='unlicensed_language'


def test_dry_run_and_network_opt_in(tmp_path,monkeypatch):
    import tools.knowledge_harvester.network as network
    call=Mock(side_effect=AssertionError('network'));monkeypatch.setattr(network,'urlopen',call)
    with pytest.raises(HarvestError):download('https://example.org/a',tmp_path/'out')
    download('https://example.org/a',tmp_path/'out',allow_network=True,dry_run=True)
    call.assert_not_called();assert not (tmp_path/'out').exists()
    store=Store(tmp_path/'absent.db');store.source_add(metadata(),dry_run=True)
    assert not store.path.exists()
    from tools.knowledge_harvester import acquire_wikidata
    monkeypatch.setattr(acquire_wikidata,'download',call)
    response=tmp_path/'cached.json';response.write_text('{"entities":{}}','utf-8')
    with pytest.raises(HarvestError,match='pinned request'):
        acquire_wikidata.cached_json('https://example.org/first',response,'entities',True)
    response.with_suffix('.request.json').write_text(canonical_json({'url':'https://example.org/first','expected_key':'entities'}),'utf-8')
    with pytest.raises(HarvestError,match='отличается'):
        acquire_wikidata.cached_json('https://example.org/changed',response,'entities',True)
    assert acquire_wikidata.cached_json('https://example.org/first',response,'entities',True)[1]=={'entities':{}}
    call.assert_not_called()


def test_bundled_payload_reads_without_sidecars_and_reverse_aliases(pipeline,tmp_path):
    from tools.knowledge_harvester.build.bundled import prepare
    from app.glossary.bundled import bundled_paths
    store,config=pipeline;feed(pipeline,tmp_path,[entity()]);link(store,config)
    build_packs(store,config,tmp_path/'packs',reverse=True)
    prepare(tmp_path/'packs',tmp_path/'bundled')
    paths=bundled_paths(tmp_path/'bundled');assert len(paths)==2
    before={p.name:file_hash(p) for p in paths}
    g=GlossaryEngine(tmp_path/'user.db',builtin_paths=paths)
    assert g.lookup('测试冷却液','zh','ru','automotive')
    assert g.lookup('тестовая жидкость','ru','zh','automotive')
    assert not g.lookup('тестовый вариант','ru','zh','automotive')
    assert before=={p.name:file_hash(p) for p in paths}
    assert not list((tmp_path/'bundled').glob('*.db-*'))


def test_fetch_blocks_unapproved_source_even_with_network_flag(tmp_path,monkeypatch):
    from tools.knowledge_harvester import cli
    call=Mock(side_effect=AssertionError('network'));monkeypatch.setattr(cli,'download',call)
    path=tmp_path/'source.json';path.write_text(canonical_json(metadata(status='UNKNOWN')),'utf-8')
    with pytest.raises(SystemExit):
        cli.main(['fetch','https://example.org/dump',str(tmp_path/'dump'),'--source-metadata',str(path),'--allow-network'])
    call.assert_not_called()


@pytest.mark.parametrize('bad',['{broken','\udcff','x'*1100])
def test_bad_records_do_not_hide_valid_following_record(pipeline,tmp_path,bad):
    store,config=pipeline;config['max_record_bytes']=1024
    path=tmp_path/'bad.jsonl';path.write_bytes(bad.encode('utf-8',errors='surrogateescape')+b'\n'+canonical_json(entity()).encode()+b'\n')
    result=ingest(store,path,'test','wikidata',config)
    assert result['rejected_this_run']==1 and report(store)['raw_records']==1


def test_compressed_resume_and_limit(pipeline,tmp_path):
    store,config=pipeline;path=tmp_path/'data.jsonl.gz'
    with gzip.open(path,'wb') as stream:stream.write((canonical_json(entity())+'\n'+canonical_json(entity('Q900000002'))+'\n').encode())
    ingest(store,path,'test','wikidata',config,sample=1)
    ingest(store,path,'test','wikidata',config)
    assert report(store)['raw_records']==2
    config['max_decompressed_bytes']=20
    with pytest.raises(HarvestError):ingest(store,path,'test','wikidata',config)


@pytest.mark.parametrize('zh,ru',[('', 'термин'),('术语','')])
def test_missing_language_is_not_verified(pipeline,tmp_path,zh,ru):
    store,config=pipeline;feed(pipeline,tmp_path,[entity(zh=zh,ru=ru)]);link(store,config)
    assert 'VERIFIED' not in report(store)['statuses']


def test_variants_multidomain_and_proper_names(pipeline,tmp_path):
    store,config=pipeline;record=entity(parents=('Q900000000','Q900000010'))
    record['labels']['zh-hant']={'value':'測試冷卻液'}
    feed(pipeline,tmp_path,[record,entity('Q900000002',parents=('Q5','Q900000000'))]);link(store,config)
    rows=candidates(store)
    assert sum(r['status']=='VERIFIED' for r in rows)==2
    assert any(r['status']=='REJECTED' for r in rows)
    assert any('測試冷卻液' in r['zh_variants'] for r in rows)


def test_conflicting_targets_and_aliases_are_queued(pipeline,tmp_path):
    store,config=pipeline;one=entity();two=entity('Q900000002',zh='测试别名',ru='другое значение')
    two['aliases']['zh']=[{'value':'测试冷却液'}]
    feed(pipeline,tmp_path,[one,two]);link(store,config)
    assert report(store)['statuses']=={'REVIEW':2}
    path=tmp_path/'conflicts.jsonl';export_queue(store,path,conflicts_only=True)
    assert len(path.read_text('utf-8').splitlines())==2


@pytest.mark.parametrize('ambiguous',[False,True])
def test_english_pivot_never_automatically_verified(pipeline,tmp_path,ambiguous):
    store,config=pipeline;rows=[entity(zh='',ru='цель')]
    if ambiguous:rows.append(entity('Q900000002',zh='',ru='вторая цель'))
    feed(pipeline,tmp_path,rows)
    path=tmp_path/'cedict.txt';path.write_text('測試 测试 [ce4 shi4] /test coolant/\n','utf-8')
    ingest(store,path,'test','cedict',config);link(store,config)
    pivot=[r for r in candidates(store) if r['link_type'].startswith('ENGLISH_PIVOT')]
    assert pivot and all(r['status']!='VERIFIED' for r in pivot)
    assert all(r['link_type']==('ENGLISH_PIVOT_AMBIGUOUS' if ambiguous else 'ENGLISH_PIVOT_EXACT') for r in pivot)


def test_source_adapters_explicit_mapping(pipeline,tmp_path):
    store,config=pipeline;feed(pipeline,tmp_path,[entity(zh='',ru='тестовая жидкость')])
    store.source_add(metadata('agro'))
    record={'@id':'https://example.org/c1',agrovoc.SKOS+'prefLabel':[{'@language':'zh','@value':'测试冷却液'}],
            agrovoc.SKOS+'exactMatch':[{'@id':'http://www.wikidata.org/entity/Q900000001'}]}
    path=tmp_path/'agro.jsonl';path.write_text(canonical_json(record)+'\n','utf-8')
    ingest(store,path,'agro','agrovoc',config);link(store,config)
    row=candidates(store)[0];assert row['link_type']=='CROSS_SOURCE_CONCEPT' and len(row['provenance'])==2
    c=cedict.parse('測試 测试 [ce4 shi4] /test/experiment/')
    assert c.labels['zh-hant']=='測試' and 'ru' not in c.labels and c.metadata['pinyin']=='ce4 shi4'
    w=wiktionary.parse({'word':'测试','lang_code':'zh','source_record_id':'page:123@rev:2','senses':[{'glosses':['test']} ]})
    assert w.metadata['review_only'] and w.definitions==['test']


def test_new_ingest_invalidates_build_and_stratified_sample(pipeline,tmp_path):
    store,config=pipeline;feed(pipeline,tmp_path,[entity()]);link(store,config)
    path=tmp_path/'review.jsonl';export_queue(store,path,sample=1)
    assert len(path.read_text('utf-8').splitlines())==1
    feed(pipeline,tmp_path,[entity('Q900000002')],name='next.jsonl')
    with pytest.raises(HarvestError,match='повторный'):build_packs(store,config,tmp_path/'out')


def test_same_mirror_does_not_raise_independence_score(pipeline,tmp_path):
    store,config=pipeline;source=metadata('mirror');source['independence_group']='test';store.source_add(source)
    feed(pipeline,tmp_path,[entity()]);feed(pipeline,tmp_path,[entity()],source='mirror',name='mirror.jsonl');link(store,config)
    assert 'independent_source_agreement' not in candidates(store)[0]['reasons']


def test_review_decision_retains_source_evidence(pipeline,tmp_path):
    store,config=pipeline;feed(pipeline,tmp_path,[entity(parents=())]);link(store,config)
    row=candidates(store)[0];assert row['status']=='REVIEW'
    path=tmp_path/'decisions.jsonl';path.write_text(canonical_json(dict(candidate_id=row['id'],decision='CHANGE_TARGET',target='исправленный термин',
            reviewer='unit-test',evidence_sha256=digest_json(row['provenance'])))+'\n','utf-8')
    import_reviews(store,path,config);link(store,config)
    result=candidates(store)[0];assert result['ru']=='исправленный термин' and result['manual_review']
    assert result['provenance']==row['provenance']
