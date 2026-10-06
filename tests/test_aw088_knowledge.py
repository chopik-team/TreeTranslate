from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import pytest
from app.knowledge.units import capacity_line
from app.documents.pdf_fidelity import faithful_result
from app.documents.pdf_ocr_policy import protected_kind
from app.knowledge.segments import SegmentClassifier
from tools.knowledge_harvester.corpus import harvest_manifest
from tools.knowledge_harvester.models import HarvestError
from tools.knowledge_harvester.storage import Store

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('unit',['mm','cm','m','N.m','kgf.m','L','mL','V','A','Ω','kPa','MPa','°C','rpm','inch','gal','qt','lb-ft','psi'])
def test_numeric_unit_line_is_protected(unit):
    assert protected_kind('12.5 '+unit)=='measurement'
    assert protected_kind('13.0 - 17.0 '+unit)=='measurement'


def test_capacity_source_values_and_ambiguity_retained():
    source='IVT :约6.6公升 （1.74加仑,6.97美升,5.80加仑/夸脱）'
    result=capacity_line(source,'zh','ru')
    assert 'неоднозначно в источнике' in result
    assert '6.97 литр' not in result
    assert faithful_result(source,result)==result
    assert capacity_line('向发动机添加6.6公升燃油。','zh','ru') is None
    assert capacity_line(source,'zh','en') is None


def test_source_unit_pair_has_no_conversion():
    source='6.1升 (1.61 美国加仑, 6.44 美国夸脱, 5.36加仑/夸脱)'
    result=capacity_line(source,'zh','ru')
    assert '6.1л' in result and '1.61 US gal' in result and '6.44 US qt' in result
    assert faithful_result(source,result)==result


def test_cross_reference_classification():
    assert SegmentClassifier.classify('（参考发动机机械系统- “空气滤清器”）').value=='CROSS_REFERENCE'
    assert SegmentClassifier.classify('检查发动机是否损坏。').value=='PROCEDURE_STEP'


def test_positional_full_phrase_forms_and_rejected_verb_overlap():
    forms={f['source']:f for f in json.loads((ROOT/'assets/config/automotive-slot-forms.json').read_text('utf8'))['forms']}
    assert forms['后车门装饰板']['accusative']=='облицовку задней двери'
    assert forms['前座椅安全带拉紧器']['genitive']=='преднатяжителя ремня безопасности переднего сиденья'
    with sqlite3.connect(ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db') as con:
        sources={r[0] for r in con.execute('SELECT source_term FROM entries')}
    assert not {'损坏线束','螺母螺栓','下方向盘'} & sources
    assert forms['下散热器软管']['accusative']=='нижний шланг радиатора'
    assert forms['后座椅靠背总成']['genitive']=='спинки заднего сиденья в сборе'
    assert not {'下散热器','左方向盘','右方向盘','冷却水箱盖','右仪表盘'} & sources


def test_manifest_harvester_never_reads_holdout_into_store(tmp_path):
    cache=tmp_path/'cache.db'
    with sqlite3.connect(cache) as con:
        con.execute('CREATE TABLE documents(member TEXT,sha256 TEXT,size INTEGER,payload TEXT)')
        for member,text in [('development.pdf','拆卸连接器。'),('held.pdf','拆卸控制器。')]:
            con.execute('INSERT INTO documents VALUES(?,?,?,?)',(member,'digest',1,json.dumps(dict(lines=[text]))))
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(dict(native_cache_sha256=sha256(cache.read_bytes()).hexdigest(),corpus_id='qa',source_sha256='container',
        documents=[dict(member='development.pdf',sha256='digest',domain='automotive',subdomains=['automotive.electrical'],stratum='automotive.electrical')])),'utf8')
    store=Store(tmp_path/'harvester.db')
    result=harvest_manifest(store,cache,manifest)
    assert result['documents']==1 and result['automatic_verified']==0
    with store.connect() as con:
        rows=[json.loads(r[0]) for r in con.execute('SELECT payload FROM corpus_documents')]
        assert {r['archive_member'] for r in rows}=={'development.pdf'}
        assert not con.execute("SELECT 1 FROM candidates WHERE status='VERIFIED'").fetchone()
    with sqlite3.connect(cache) as con:con.execute('UPDATE documents SET size=2')
    with pytest.raises(HarvestError,match='changed_native_cache'):harvest_manifest(store,cache,manifest)
