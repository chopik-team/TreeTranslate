"""First Frozen A evaluation: real whole PDF jobs, with no semantic auto-grading."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
from time import perf_counter
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.aw081_large_zip import ARCHIVE, production_hashes
from app.documents.run_metrics import LocalRun, file_hash

def run():
    gate_path=ROOT/'qa/aw081/iterations/14_phase_a_closure/acceptance_gate.json'
    gate=json.loads(gate_path.read_text('utf8'))
    assert gate['phase_A']=='PASS' and gate['level_3']=='PASS' and gate['full_pytest']=='PASS'
    sealed=production_hashes()
    assert sealed==gate['production_hashes']
    manifest_path=ROOT/'qa/aw081/final_holdout_manifest.json'
    manifest_hash=file_hash(manifest_path)
    manifest=json.loads(manifest_path.read_text('utf8'))
    assert len(manifest['documents'])==46
    qa=ROOT/'qa/aw081/iterations/14_phase_a_closure/frozen_A_whole'
    qa.mkdir(exist_ok=False)
    original=qa/'originals';original.mkdir()
    output=ROOT/'output/aw081/frozen-A-first-final';output.mkdir(exist_ok=False)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    from app.engine.factory import create_translation_engine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.documents.job import DocumentJob,DocumentConfig
    from app.documents.scanner import SourceFile
    from app.documents.control import JobControl
    from app.documents.pdf_document import PdfDocument
    engine=create_translation_engine(memory=TranslationMemoryEngine(qa/'isolated-tm.db'),
        glossary=GlossaryEngine(qa/'isolated-user.db',builtin_paths=bundled_paths()))
    observer=LocalRun(qa/'logs',metadata=dict(scope='FIRST_FROZEN_A_WHOLE_PRODUCTION',
        manifest_sha256=manifest_hash,production_hashes=sealed,development_prohibited=True))
    real_validate=PdfDocument.validate
    current_index=None
    validation=None
    def validate(document,destination):
        nonlocal validation
        result=real_validate(document,destination)
        validation=dict(validation='PASS',source_pages=len(document.pages),
            output_pages=len(document.pages)+document.continuation_count,
            segments=[asdict(segment) for segment in document.segments])
        return result
    PdfDocument.validate=validate
    source_archive_hash=file_hash(ARCHIVE)
    started=perf_counter()
    rows=[]
    try:
        with observer.activate(), engine.runtime.keep_warm(), ZipFile(ARCHIVE) as archive, (qa/'documents.jsonl').open('x',encoding='utf8') as checkpoints:
            for index,item in enumerate(manifest['documents']):
                current_index=index;validation=None;warnings=[]
                source=original/f'{index}.pdf'
                with archive.open(item['member']) as member,source.open('xb') as target:
                    shutil.copyfileobj(member,target)
                assert file_hash(source)==item['sha256']
                begin=perf_counter()
                row=dict(index=index,member=item['member'],source_sha256=item['sha256'],
                    source_path=str(source),semantic_status='UNREVIEWED')
                job=DocumentJob([SourceFile(source,source.parent,Path(item['member']),source.stat().st_size)],
                    DocumentConfig(source='zh',target='ru',domain='auto',output=output),JobControl(),
                    engine.translate,engine.languages.resolve,warning=warnings.append,run_id=observer.run_id)
                try:
                    result=job.run()
                    assert validation is not None
                    row.update(validation,output=str(result[-1]),output_sha256=file_hash(result[-1]))
                except Exception as error:
                    row.update(validation='FAILED',error_type=type(error).__name__,error_message=str(error))
                row.update(seconds=perf_counter()-begin,warnings=warnings,
                    source_immutable=file_hash(source)==item['sha256'])
                rows.append(row)
                checkpoints.write(json.dumps(row,ensure_ascii=False)+'\n');checkpoints.flush()
                print('FROZEN_A',index+1,'/46',row['validation'],round(row['seconds'],2),'seconds',flush=True)
        observer.close('COMPLETED' if all(r['validation']=='PASS' for r in rows) else 'FAILED')
    except BaseException as error:
        observer.close('FAILED',error)
        raise
    finally:
        PdfDocument.validate=real_validate
        engine.shutdown()
    assert sealed==production_hashes()
    assert file_hash(manifest_path)==manifest_hash
    assert file_hash(ARCHIVE)==source_archive_hash
    report=dict(revision='AW0.81',set_id='FINAL_HOLDOUT_A',first_independent_whole_production_evaluation=True,
        semantic_status='UNREVIEWED',document_count=len(rows),documents=rows,
        manifest_sha256=manifest_hash,source_archive_sha256=source_archive_hash,
        production_hashes=sealed,production_unchanged=True,source_immutable=True,
        logs=str(observer.directory),seconds=perf_counter()-started,
        translation_of_complete_17211_pdf_archive=False,
        next_use='DIAGNOSTIC_A_AFTER_FIRST_REVIEW; no knowledge or router fixes in this task')
    (qa/'execution.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print('FROZEN_A_WHOLE_STRUCTURAL_COMPLETE',len(rows),flush=True)

if __name__=='__main__':run()
