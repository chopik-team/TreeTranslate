"""Paired production PDF runs: logging must not change content or rendering.

PDFium generates a new trailer /ID independently of the observer. Raw file
hashes are retained; only that identifier is excluded from comparison hashes.
"""
from pathlib import Path
from dataclasses import replace
from statistics import median
from time import perf_counter
import json,sqlite3,sys,re
from hashlib import sha256
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw081/local_metrics_self_test'/uuid4().hex

def signature(path):
 import pypdfium2 as pdf
 data=Path(path).read_bytes()
 canonical=re.sub(rb'/ID\[<[0-9A-Fa-f]{32}><[0-9A-Fa-f]{32}>\]',b'/ID[<RUN-ID><RUN-ID>]',data)
 pages=[]
 document=pdf.PdfDocument(path)
 try:
  for index in range(len(document)):
   page=document[index];text=page.get_textpage();bitmap=page.render(scale=1)
   try:
    text_hash=sha256(text.get_text_range().encode('utf8')).hexdigest()
    pixel_hash=sha256(bitmap.to_pil().tobytes()).hexdigest()
    pages.append(dict(text_sha256=text_hash,pixels_sha256=pixel_hash,size=page.get_size()))
   finally:bitmap.close();text.close();page.close()
 finally:document.close()
 return dict(file_sha256=sha256(data).hexdigest(),pdf_excluding_trailer_id_sha256=sha256(canonical).hexdigest(),pages=pages)

def run(pairs=5):
 from app.documents.run_metrics import file_hash
 from app.engine.factory import create_translation_engine
 from app.glossary.engine import GlossaryEngine
 from app.glossary.bundled import bundled_paths
 from app.translation_memory.engine import TranslationMemoryEngine
 from app.documents.job import DocumentJob,DocumentConfig
 from app.documents.scanner import SourceFile
 from app.documents.control import JobControl
 QA.mkdir(parents=True,exist_ok=True)
 cases=json.loads((ROOT/'qa/aw081/diagnostic/representative_holdout.json').read_text('utf8'))['documents']
 files=[]
 for i in (0,15):
  source=ROOT/f'qa/aw081/diagnostic/originals/{i}.pdf'
  assert file_hash(source)==cases[i]['sha256']
  files.append(SourceFile(source,None,Path(cases[i]['member']),source.stat().st_size))
 engine=create_translation_engine(memory=TranslationMemoryEngine(QA/'isolated-tm.db'),glossary=GlossaryEngine(QA/'isolated-user.db',builtin_paths=bundled_paths()))
 records=[]
 try:
  with engine.runtime.keep_warm():
   # Warm the PDF/font path independently; exclude the warmup from overhead.
   DocumentJob(files,DocumentConfig(source='zh',target='ru',domain='auto',output=QA/'warmup'),JobControl(),engine.translate,engine.languages.resolve).run()
   for pair in range(pairs):
    timings={};hashes={};signatures={};log_path=None
    for enabled in ((False,True) if pair%2==0 else (True,False)):
     config=DocumentConfig(source='zh',target='ru',domain='auto',output=QA/f'pair-{pair}'/('enabled' if enabled else 'disabled'),metrics_directory=QA/'logs' if enabled else None)
     job=DocumentJob(files,config,JobControl(),engine.translate,engine.languages.resolve)
     begin=perf_counter();outputs=job.run();timings[enabled]=perf_counter()-begin
     hashes[enabled]=[file_hash(p) for p in outputs]
     signatures[enabled]=[signature(p) for p in outputs]
     if enabled:
      assert not job.metrics_failed
      log_path=job.metrics_path
      summary=json.loads((log_path/'run_summary.json').read_text('utf8'))
      docs=[json.loads(line) for line in (log_path/'documents.jsonl').read_text('utf8').splitlines()]
      assert len(docs)==summary['counters']['documents']==2
      for d in docs:
       assert d['source_immutable'] and d['output_sha256']==file_hash(d['output_path'])
       c=d['counters'];assert c.get('model_fallback_segments',0)<=c['semantic_segments'] and c.get('knowledge_segments',0)<=c['eligible_semantic_segments']
      for path in log_path.glob('*.jsonl'):
       for line in path.read_text('utf8').splitlines():json.loads(line)
      with sqlite3.connect(log_path/'index.sqlite3') as con:assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert [{k:v for k,v in s.items() if k!='file_sha256'} for s in signatures[False]]==[{k:v for k,v in s.items() if k!='file_sha256'} for s in signatures[True]], 'Logging changed PDF content/rendering'
    assert all(file_hash(f.path)==cases[i]['sha256'] for f,i in zip(files,(0,15)))
    records.append(dict(pair=pair,disabled_seconds=timings[False],enabled_seconds=timings[True],content_and_rendering_identical=True,raw_bytes_identical=hashes[False]==hashes[True],signatures={'disabled':signatures[False],'enabled':signatures[True]},log_directory=str(log_path)))
    print('PAIR',pair,round(timings[False],3),round(timings[True],3),flush=True)
 finally:engine.shutdown()
 ratios=[(r['enabled_seconds']/r['disabled_seconds']-1)*100 for r in records]
 result=dict(revision='AW0.81',corpus='Two existing diagnostic native PDFs, normal extraction/OCR policy and writer; no Frozen A content.',pairs=records,
  overhead_percent=median(ratios),aggregate_overhead_percent=(sum(r['enabled_seconds'] for r in records)/sum(r['disabled_seconds'] for r in records)-1)*100,
  pair_overhead_percent=ratios,overhead_goal_percent=5,overhead_goal_met=median(ratios)<5,
  output_content_and_rendering_equivalent=True,source_immutable=True,limitations=['PDFium generates fresh trailer /ID values. Comparison hashes exclude only these IDs; raw SHA-256 hashes are retained.','Small paired local benchmark; overhead is not a forecast for the full archive. Negative measured overhead is timing noise, not a speedup claim.'])
 (QA/'benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
 print('OVERHEAD',round(result['overhead_percent'],2),'%',flush=True)

if __name__=='__main__':run()
