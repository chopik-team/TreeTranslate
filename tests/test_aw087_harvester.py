import json
from pathlib import Path
import pytest
from tools.knowledge_harvester.storage import Store
from tools.knowledge_harvester.corpus import candidate,intake,review,export
from tools.knowledge_harvester.models import HarvestError
from tools.knowledge_harvester.provenance import digest_json,file_hash

def test_intake_idempotent_and_read_only(tmp_path):
    path=tmp_path/'service.txt';path.write_text('冷却液 散热器\n检查冷却液液位。\nGDS\n水泵','utf-8')
    digest=file_hash(path);store=Store(tmp_path/'store.db')
    first=intake(store,path,corpus_id='one',language='zh',origin='USER_PROVIDED')
    with store.connect() as con:count=con.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]
    second=intake(store,path,corpus_id='one',language='zh',origin='USER_PROVIDED')
    assert first[0]['id']==second[0]['id'] and file_hash(path)==digest
    with store.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]==count
        assert {json.loads(r[0])['type'] for r in con.execute('SELECT payload FROM candidates')} >= {'TERM','COMPOUND','PHRASE','TEMPLATE','ABBREVIATION'}
        assert con.execute("SELECT COUNT(*) FROM candidates WHERE status='VERIFIED'").fetchone()[0]==0
    assert export(store,tmp_path/'queue.jsonl')==count

def test_model_cannot_be_verified(tmp_path):
    store=Store(tmp_path/'store.db');uid=candidate(store,source='水泵',target='насос',origin='MODEL_SUGGESTED')
    with store.connect() as con:payload=json.loads(con.execute('SELECT payload FROM candidates WHERE id=?',(uid,)).fetchone()[0])
    digest=digest_json(payload['provenance'])
    with pytest.raises(HarvestError):review(store,uid,'VERIFIED',reviewer='QA',reason='test',evidence_sha256=digest)
    review(store,uid,'REVIEWED',reviewer='QA',reason='test',evidence_sha256=digest)
    with pytest.raises(HarvestError):review(store,uid,'VERIFIED',reviewer='QA',reason='test',evidence_sha256=digest)

def test_context_polysemy_conflicts_and_dedup(tmp_path):
    store=Store(tmp_path/'store.db')
    first=candidate(store,source=' 排气 ',target='удаление воздуха',domain='automotive',subdomains=['cooling'])
    assert first==candidate(store,source='排气',target='удаление воздуха',domain='automotive',subdomains=['cooling'])
    second=candidate(store,source='排气',target='выпуск',domain='automotive',subdomains=['engine'])
    third=candidate(store,source='排气',target='сброс',domain='automotive',subdomains=['cooling'])
    with store.connect() as con:
        assert con.execute('SELECT count(*) FROM conflicts').fetchone()[0]==1
        assert con.execute('SELECT status FROM candidates WHERE id=?',(third,)).fetchone()[0]=='AMBIGUOUS'
        assert con.execute('SELECT status FROM candidates WHERE id=?',(second,)).fetchone()[0]=='CANDIDATE'

def test_changed_evidence_invalidates_review(tmp_path):
    store=Store(tmp_path/'store.db');uid=candidate(store,source='水泵',target='водяной насос',origin='AUTHORED')
    with store.connect() as con:payload=json.loads(con.execute('SELECT payload FROM candidates WHERE id=?',(uid,)).fetchone()[0])
    digest=digest_json(payload['provenance'])
    review(store,uid,'REVIEWED',reviewer='QA',reason='meaning',evidence_sha256=digest)
    review(store,uid,'VERIFIED',reviewer='QA',reason='meaning',evidence_sha256=digest)
    candidate(store,source='水泵',target='водяной насос',origin='AUTHORED',provenance={'revision':2})
    with pytest.raises(HarvestError):review(store,uid,'VERIFIED',reviewer='QA',reason='meaning',evidence_sha256=digest)

def test_docx_and_zip_intake(tmp_path):
    from docx import Document
    from zipfile import ZipFile
    doc=Document();doc.add_paragraph('检查冷却液和散热器。');path=tmp_path/'a.docx';doc.save(path)
    archive=tmp_path/'corpus.zip'
    with ZipFile(archive,'w') as z:z.write(path,'folder/a.docx')
    rows=intake(Store(tmp_path/'store.db'),archive,corpus_id='zip',language='zh',origin='USER_PROVIDED')
    assert len(rows)==1 and rows[0]['archive_member']=='folder/a.docx'
    assert rows[0]['usage_permission_status']=='REVIEW_REQUIRED'

def test_unsafe_zip_rejected(tmp_path):
    from zipfile import ZipFile
    from app.documents.errors import DocumentError
    path=tmp_path/'bad.zip'
    with ZipFile(path,'w') as z:z.writestr('../evil.docx','bad')
    with pytest.raises(DocumentError):intake(Store(tmp_path/'s.db'),path,corpus_id='bad',language='zh',origin='USER_PROVIDED')

def test_pack_adapter_requires_redistribution_permission(tmp_path):
    from tools.knowledge_harvester.corpus import reviewed_entries
    store=Store(tmp_path/'s.db')
    for source,permission in [('水泵','AUTHORED_FOR_PROJECT'),('油泵','REVIEW_REQUIRED')]:
        uid=candidate(store,source=source,target='насос',origin='AUTHORED',provenance={'permission':permission})
        with store.connect() as con:row=json.loads(con.execute('SELECT payload FROM candidates WHERE id=?',(uid,)).fetchone()[0])
        for state in ['REVIEWED','VERIFIED']:review(store,uid,state,reviewer='QA',reason='reviewed',evidence_sha256=digest_json(row['provenance']))
    assert [r['source_term'] for r in reviewed_entries(store)]==['水泵']

def test_language_pairs_do_not_conflict(tmp_path):
    store=Store(tmp_path/'s.db')
    candidate(store,source='pump',target='насос',source_language='en')
    candidate(store,source='pump',target='Pumpe',source_language='en',target_language='de')
    with store.connect() as con:assert con.execute('SELECT count(*) FROM conflicts').fetchone()[0]==0

def test_declared_alias_dedup_and_conflict(tmp_path):
    store=Store(tmp_path/'s.db')
    first=candidate(store,source='散热器排放塞',target='сливная пробка радиатора',aliases=['散热器排放螺塞'],subdomains=['cooling'])
    same=candidate(store,source='散热器排放螺塞',target='сливная пробка радиатора',subdomains=['cooling'])
    assert first==same
    candidate(store,source='散热器排放螺塞',target='крышка',subdomains=['cooling'])
    with store.connect() as con:assert con.execute('SELECT count(*) FROM conflicts').fetchone()[0]==1
