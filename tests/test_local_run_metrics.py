"""Run accounting, privacy, persistence and observer failure isolation."""
import json,sqlite3,subprocess,sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.documents.run_metrics import LocalRun,semantic_segment,observe,measure,current,file_hash
from app.documents.job import DocumentConfig
from app.documents.scanner import SourceFile
from app.engine.types import TranslationResult

def rows(path):return [json.loads(line) for line in path.read_text('utf8').splitlines()]

def item(tmp_path):
 path=tmp_path/'source.pdf';path.write_bytes(b'source')
 return SourceFile(path,None,Path(path.name),path.stat().st_size)

def test_real_block_accounting_is_not_lookup_call_accounting(tmp_path):
 run=LocalRun(tmp_path/'logs',run_id='accounting')
 source=item(tmp_path);output=tmp_path/'out.pdf';output.write_bytes(b'output')
 @measure('model_translation',model=True)
 def infer():return TranslationResult('Результат','zh','ru','m2m100','cpu',1,'',False,'r',glossary_hits_count=1,knowledge_source='glossary')
 with run.activate():
  run.start_document(source,DocumentConfig())
  for n in range(2):
   segment=SimpleNamespace(text='检查传感器。',translated='Результат',block_id=str(n),page=0)
   with semantic_segment(segment,'PROCEDURE_STEP'):
    result=infer();observe('see_result',result);observe('see_result',result)
  with semantic_segment(SimpleNamespace(text='44 ± 5',translated='44 ± 5'), 'MEASUREMENT'):pass
  doc=SimpleNamespace(pages=[1],continuation_count=0,continuations=[])
  run.complete_document(source,doc,output);run.close()
 summary=json.loads((run.directory/'run_summary.json').read_text('utf8'));c=summary['counters']
 assert c['documents']==1 and c['processed_segments']==3 and c['semantic_segments']==2
 assert c['model_fallback_segments']==c['knowledge_segments']==2
 assert summary['model_fallback_rate']==summary['knowledge_coverage']==1
 assert c['direct_known_segments']==0
 assert rows(run.directory/'documents.jsonl')[0]['output_sha256']==file_hash(output)
 assert current() is None

def test_text_and_exception_messages_are_not_leaked(tmp_path):
 run=LocalRun(tmp_path/'logs',run_id='privacy')
 secret='私人文件保密文字'*500
 with run.activate():
  run.start_document(item(tmp_path),DocumentConfig())
  with semantic_segment(SimpleNamespace(text=secret,translated=secret,block_id='private'), 'PROSE'):
   observe('warning',secret)
   observe('guards',['object:'+secret])
  run.close('FAILED',ValueError(secret))
 for path in run.directory.glob('*.json*'):
  assert secret not in path.read_text('utf8')
 assert len(rows(run.directory/'errors.jsonl'))==2
 assert all('primary_category' in r for r in rows(run.directory/'errors.jsonl'))

def test_hard_crash_keeps_flushed_jsonl_and_sqlite(tmp_path):
 directory=tmp_path/'crash'
 script="from app.documents.run_metrics import LocalRun; import os; r=LocalRun(os.environ['TEST_LOG_DIR'],run_id='crash'); r.emit('archive_events',{'event':'checkpoint'}); r.flush(); os._exit(7)"
 import os
 env=dict(os.environ,TEST_LOG_DIR=str(directory))
 proc=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True)
 assert proc.returncode==7
 assert rows(directory/'crash/archive_events.jsonl')[0]['event']=='checkpoint'
 with sqlite3.connect(directory/'crash/index.sqlite3') as con:assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 assert json.loads((directory/'crash/run_manifest.json').read_text('utf8'))['status']=='RUNNING'

def test_warning_sink_failure_does_not_change_translation(tmp_path,monkeypatch):
 run=LocalRun(tmp_path/'logs',run_id='failure')
 with run.activate():
  def broken(*args,**kwargs):raise OSError('private disk detail')
  monkeypatch.setattr(run,'emit',broken)
  assert observe('warning','private document text') is None
  assert run.logging_failed
  @measure('translation')
  def translate():return 'unchanged result'
  assert translate()=='unchanged result'
  run.close()

def test_sampling_is_repeatable_and_archive_members_have_final_bindings(tmp_path):
 run=LocalRun(tmp_path/'logs',run_id='sample')
 src=item(tmp_path);archive=tmp_path/'source.zip'
 src=replace(src,archive=archive,archive_hash='a'*64)
 out=tmp_path/'out.pdf';out.write_bytes(b'output')
 with run.activate():
  run.start_document(src,DocumentConfig());run.complete_document(src,SimpleNamespace(pages=[1],continuation_count=0,continuations=[]),out)
  run.bind_archive_member(archive,src.relative.as_posix(),'translated.pdf',.1,100)
  run.archive_event('published',source=str(archive),output='final.zip',output_sha256='b'*64)
  run.write_sample();before=(run.directory/'quality_sample_manifest.json').read_bytes()
  run.write_sample();assert (run.directory/'quality_sample_manifest.json').read_bytes()==before
  sample=json.loads(before)['random'][0]
  assert sample['output_archive']['path']=='final.zip' and sample['output_archive_member']=='translated.pdf'
  assert sample['output_path'] is None
  run.close()
