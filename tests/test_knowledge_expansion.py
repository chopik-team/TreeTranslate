import json
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import Mock

import pytest

from tools.knowledge_harvester.prepare_agrovoc import convert, literal
from tools.knowledge_harvester.sources.agrovoc import parse, SKOS
from tools.knowledge_harvester.models import HarvestError
from tools.knowledge_harvester.config import load


def test_agrovoc_lod_stream_preserves_concepts_and_licensed_languages(tmp_path):
    uri='http://aims.fao.org/aos/agrovoc/c_test'
    text='\n'.join([
        f'<{uri}> <{SKOS}prefLabel> "钢"@zh .',
        f'<{uri}> <{SKOS}prefLabel> "сталь"@ru .',
        f'<{uri}> <{SKOS}prefLabel> "steel"@en .',
        f'<{uri}> <{SKOS}prefLabel> "Stahl"@de .',
        f'<{uri}> <{SKOS}altLabel> "鋼"@zh .',
        f'<{uri}> <{SKOS}broader> <http://aims.fao.org/aos/agrovoc/c_parent> .',
        f'<{uri}> <{SKOS}exactMatch> <http://www.wikidata.org/entity/Q11427> .',
    ])+'\n'
    archive=tmp_path/'source.zip'
    with ZipFile(archive,'w') as z:z.writestr('source.nt',text)
    first=convert(archive,tmp_path/'first.jsonl',staging=tmp_path/'staging.db')
    second=convert(archive,tmp_path/'second.jsonl',staging=tmp_path/'staging.db')
    assert first['jsonl_sha256']==second['jsonl_sha256']
    node=json.loads((tmp_path/'first.jsonl').read_text('utf-8'));record=parse(node)
    assert record.labels=={'en':'steel','ru':'сталь','zh':'钢'}
    assert record.aliases=={'zh':['鋼']}
    assert record.mappings==['wikidata:Q11427']
    assert record.relations==[('broader','agrovoc:http://aims.fao.org/aos/agrovoc/c_parent')]
    with ZipFile(archive,'a') as z:z.writestr('extra.txt','changed source')
    with pytest.raises(HarvestError,match='SHA256'):
        convert(archive,tmp_path/'third.jsonl',staging=tmp_path/'staging.db')


def test_nt_literal_escapes_and_uncompressed_size_guard(tmp_path):
    assert literal(r'\u94a2\U00020000\n\"x\"')=='钢𠀀\n"x"'
    with pytest.raises(HarvestError):literal(r'wrong\q')
    archive=tmp_path/'source.zip'
    with ZipFile(archive,'w') as z:z.writestr('source.nt','x'*100)
    with pytest.raises(HarvestError):
        convert(archive,tmp_path/'out.jsonl',staging=tmp_path/'staging.db',max_uncompressed=10)


def test_expansion_preserves_trust_thresholds_and_does_not_relax_gates():
    baseline=load();expanded=load(Path('tools/knowledge_harvester/expansion_policy.json'))
    for key,value in baseline.items():
        if key not in ('domains','domain_review_keywords'):assert expanded[key]==value
    for domain,words in baseline['domain_review_keywords'].items():
        assert set(words)<=set(expanded['domain_review_keywords'][domain])
    assert set(expanded['domains'])==set(baseline['domains'])
    for domain,rule in baseline['domains'].items():
        assert set(rule['roots'])<=set(expanded['domains'][domain]['roots'])
        assert rule['keywords']==expanded['domains'][domain]['keywords']


def test_wikidata_expansion_pins_plan_and_uses_supported_union(tmp_path,monkeypatch):
    from tools.knowledge_harvester import expand_wikidata as module
    config=load();config['domains']={'technical-core':{'roots':['wikidata:Q1','wikidata:Q2'],'keywords':[]}}
    monkeypatch.setattr(module,'load',lambda *args:config)
    queries=[]
    def cached(url,path,key,allow_network):
        from urllib.parse import parse_qs,urlsplit
        query=parse_qs(urlsplit(url).query);queries.append(query)
        data={'query':{'search':[{'title':'Q3'}]}} if key=='query' else {'entities':{q:{'id':q,'lastrevid':1} for q in query['ids'][0].split('|')}}
        path.write_text(json.dumps(data),'utf-8');return path,data
    monkeypatch.setattr(module,'cached_json',cached)
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    with pytest.raises(HarvestError):module.expand(tmp_path/'off')
    result=module.expand(tmp_path/'on',allow_network=True,per_domain=10,depth=1)
    assert queries[0]['srsearch']==['haswbstatement:P279=Q1|P279=Q2']
    assert result['entities']==3
    with pytest.raises(HarvestError,match='План'):
        module.expand(tmp_path/'on',allow_network=True,per_domain=11,depth=1)
