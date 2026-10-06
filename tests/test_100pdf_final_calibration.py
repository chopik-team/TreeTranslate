"""Measurement guards only; no document/model benchmark inside tests."""
from hashlib import sha256
from types import SimpleNamespace
import pytest
from tools.aw081_100pdf_final_speed_calibration import verify_members,LookupObserver
from tools.aw081_speed_calibration_report import exclusive_categories,percentile


def fixture_archive():
    data=b'unchanged source'
    infos=[SimpleNamespace(filename=f'{i}.pdf',file_size=len(data),CRC=17,is_dir=lambda:False) for i in range(17211)]
    class Archive:
        def __init__(self,rows):self.rows=rows
        def infolist(self):return self.rows
        def getinfo(self,name):return next(i for i in self.rows if i.filename==name)
        def read(self,info):return data
        def testzip(self):return None
    docs=[dict(member_path=f'{i}.pdf',inventory_pdf_index=i,source_size=len(data),source_sha256=sha256(data).hexdigest()) for i in range(100)]
    return dict(documents=docs),Archive(infos),Archive(infos[:100])


def test_same_100_order_crc_size_hash():
    m,original,subset=fixture_archive()
    assert len(verify_members(m,original,subset))==100
    subset.rows=list(reversed(subset.rows))
    with pytest.raises(AssertionError):verify_members(m,original,subset)


@pytest.mark.parametrize('field,value',[('source_size',99),('source_sha256','wrong'),('inventory_pdf_index',111)])
def test_same_100_rejects_source_drift(field,value):
    m,original,subset=fixture_archive();m['documents'][0][field]=value
    with pytest.raises(AssertionError):verify_members(m,original,subset)


def test_wall_partition_does_not_double_count_parallel_stages():
    events=[dict(stage='ocr_recognize',seconds=4,elapsed_since_run_start=5),
            dict(stage='model_translation',seconds=6,elapsed_since_run_start=7),
            dict(stage='glossary_lookup',seconds=9,elapsed_since_run_start=10)]
    result=exclusive_categories(events,12)
    assert result=={'OCR':4,'model':2,'glossary':3,'other/orchestration':3}
    assert percentile([0,10,20],.95)==19


def test_sql_observer_preserves_native_connection_and_result(tmp_path):
    import sqlite3
    native=sqlite3.connect;observer=LookupObserver();observer.install();observer.active=True
    try:
        with sqlite3.connect(tmp_path/'isolated-user.db') as connection:
            connection.execute('CREATE TABLE t (x INTEGER)');connection.execute('INSERT INTO t VALUES (9)')
            assert connection.execute('SELECT x FROM t').fetchall()==[(9,)]
        observed=observer.counts['sql_statements']
        with sqlite3.connect(tmp_path/'isolated-tm.db') as connection:
            assert connection.execute('SELECT 11').fetchone()==(11,)
        assert observer.counts['sql_statements']==observed==3
    finally:observer.close()
    assert sqlite3.connect is native


def test_recovered_forecast_reproduces_all_three_historical_scenarios():
    from tools.aw081_100pdf_final_calibration_report import historical_forecast,read,lines,OLD
    baseline=read(OLD/'calibration_analysis.json')
    result=historical_forecast(read(OLD/'sample_manifest.json'),lines(OLD/'documents.jsonl'),baseline['total_wall_seconds'])
    for key in ['optimistic','typical','conservative']:
        assert result['scenarios'][key]['hours']==pytest.approx(baseline['estimates'][key]['hours'],abs=1e-9)
