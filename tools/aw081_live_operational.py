"""Only Diagnostic A's 46 PDFs: real archive operational regression, no full CN7C run."""
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path,PurePosixPath
import sys
import sqlite3
from time import perf_counter
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.aw081_large_zip import production_hashes
from app.documents.run_metrics import file_hash
QA=ROOT/'qa/aw081/iterations/15_diagnostic_live_readiness'

def run():
    before=production_hashes()
    manifest=json.loads((ROOT/'qa/aw081/final_holdout_manifest.json').read_text('utf8'))
    previous=json.loads((ROOT/'qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/execution.json').read_text('utf8'))
    work=QA/'operational';work.mkdir(exist_ok=False)
    source=work/'Diagnostic A.zip'
    original=ROOT/'qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/originals'
    with ZipFile(source,'w',compression=ZIP_DEFLATED) as archive:
        for index,item in enumerate(manifest['documents']):
            path=original/f'{index}.pdf'
            assert file_hash(path)==item['sha256']
            archive.write(path,item['member'])
        archive.writestr('diagnostic_metadata.json',b'{"documents":46,"scope":"operational"}')
    source_hash=file_hash(source)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    from app.engine.factory import create_translation_engine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.documents.job import DocumentJob,DocumentConfig
    from app.documents.control import JobControl
    from app.documents.scanner import scan_sources
    from app.documents.pdf_document import PdfDocument
    engine=create_translation_engine(memory=TranslationMemoryEngine(work/'isolated-tm.db'),
        glossary=GlossaryEngine(work/'isolated-user.db',builtin_paths=bundled_paths()))
    indices={item['sha256']:i for i,item in enumerate(manifest['documents'])}
    captures={}
    real_validate=PdfDocument.validate
    checkpoint=(work/'successful_documents.jsonl').open('x',encoding='utf8')
    def validate(doc,destination):
        result=real_validate(doc,destination)
        index=indices[doc.source_hash]
        row=dict(index=index,member=manifest['documents'][index]['member'],source_sha256=doc.source_hash,
            source_pages=len(doc.pages),output_pages=len(doc.pages)+doc.continuation_count,
            segments=[asdict(segment) for segment in doc.segments])
        captures[index]=row
        checkpoint.write(json.dumps(row,ensure_ascii=False)+'\n');checkpoint.flush()
        return result
    PdfDocument.validate=validate
    started=perf_counter()
    control=JobControl()
    scanned=scan_sources([source],control)
    assert len(scanned.files)==46
    config=DocumentConfig(source='zh',target='ru',domain='auto',output=ROOT/'output/aw081/diagnostic-live-readiness',
        metrics_directory=work/'logs')
    last=0
    def progress(value):
        nonlocal last
        if value.file_index!=last:
            last=value.file_index
            print('DIAGNOSTIC_OPERATIONAL',last,'/46',value.stage,flush=True)
    job=DocumentJob(scanned.files,config,control,engine.translate,engine.languages.resolve,progress=progress)
    job.metrics_metadata=dict(scope='DIAGNOSTIC_A_OPERATIONAL_ONLY',manual_live_run=False,
        previous_failures=[r['index'] for r in previous['documents'] if r['validation']!='PASS'])
    try:
        with engine.runtime.keep_warm():outputs=job.run()
    finally:
        checkpoint.close();PdfDocument.validate=real_validate;engine.shutdown()
    assert len(outputs)==1
    summary=json.loads((job.metrics_path/'run_summary.json').read_text('utf8'))
    with sqlite3.connect(job.metrics_path/'index.sqlite3') as database:
        rows=[json.loads(payload) for payload, in database.execute('SELECT payload FROM documents')]
    assert len(rows)==46 and summary['total_documents']==46
    assert summary['translated_documents']+summary['source_preserved_documents']==46
    assert summary['fatal_errors']==0 and summary['logging_status']=='COMPLETE'
    preserved=[]
    with ZipFile(outputs[0]) as final,ZipFile(source) as initial:
        assert final.testzip() is None
        names=final.namelist()
        assert sum(name.endswith('.pdf') for name in names)==46
        assert len(names)==len(set(names))
        for row in rows:
            if row['output_status']=='FAILED_SOURCE_PRESERVED':
                member=row['archive_member_path']
                assert final.read(member)==initial.read(member)
                preserved.append(member)
            else:
                assert row['output_status']=='TRANSLATED'
                # The recovery/packaging boundary cannot alter a successful
                # normal DocumentJob result, including its semantic text/layout.
                assert sha256(final.read(row['output_archive_member'])).hexdigest()==row['output_sha256']
        assert final.read('diagnostic_metadata.json')==initial.read('diagnostic_metadata.json')
    comparisons=[]
    for row in previous['documents']:
        index=row['index']
        if row['validation']!='PASS' or index not in captures:continue
        old={(s['page'],s['block_id']):s for s in row['segments']}
        changes=[]
        for segment in captures[index]['segments']:
            key=(segment['page'],segment['block_id'])
            prior=old.get(key)
            if not prior or prior['translated']!=segment['translated']:
                changes.append(dict(page=segment['page'],block_id=segment['block_id'],source=segment['text'],
                    before=prior['translated'] if prior else None,after=segment['translated']))
        comparisons.append(dict(index=index,unchanged=not changes,changes=changes,
            previous_blocks=len(old),current_blocks=len(captures[index]['segments'])))
    cata=[]
    known=json.loads((ROOT/'qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/semantic_review.json').read_text('utf8'))
    from app.knowledge.safety import violations
    for old in known['rows']:
        if old['grade']!='CATA':continue
        index=old['index'];page=int(old['block_id'].split('-')[0][1:])-1
        current=next(s for s in captures[index]['segments'] if s['page']==page and s['block_id']==old['block_id'])
        assert current['text']==old['source']
        assert current['translated']!=current['text'] and not violations(current['text'],current['translated'])
        cata.append(dict(index=index,block_id=old['block_id'],source=current['text'],
            translated=current['translated'],published=current.get('rendered_text') or current['translated'],
            grade='PENDING_PUBLICATION_VISUAL_REVIEW',safety_guard_issues=[]))
    result=dict(scope='46_DOCUMENT_OPERATIONAL_REGRESSION_NOT_SEMANTIC_REVIEW',status=job.run_status,
        summary=summary,logs=str(job.metrics_path),source_archive=str(source),source_archive_sha256=source_hash,
        output_archive=str(outputs[0]),output_archive_sha256=file_hash(outputs[0]),crc='PASS',
        successful_member_bytes_unchanged=True,
        inventory_pdf_count=46,failed_members_preserved_byte_for_byte=preserved,source_immutable=file_hash(source)==source_hash,
        processed=46,translated=summary['translated_documents'],failed_source_preserved=summary['source_preserved_documents'],
        fatal=0,previous_failures=[dict(index=r['index'],old_error=r['error_type'],
            new_status=next(d['output_status'] for d in rows if d['source_sha256']==r['source_sha256']))
            for r in previous['documents'] if r['validation']!='PASS'],
        previous_successful_semantics=comparisons,known_cata=cata,seconds=perf_counter()-started,
        production_unchanged=before==production_hashes(),large_zip_started=False)
    assert result['source_immutable'] and result['production_unchanged']
    (work/'execution.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print('OPERATIONAL_COMPLETE',result['translated'],result['failed_source_preserved'],flush=True)
def finish_existing():
    """Reconstruct an evidence receipt from a completed run, never rerun translation.

    Early JSONL checkpoints contain staging paths. Only SQLite has the final
    archive-member bindings, as documented by the logging contract.
    """
    work=QA/'operational'
    logs=next((work/'logs').iterdir())
    summary=json.loads((logs/'run_summary.json').read_text('utf8'))
    assert summary['status'] in {'COMPLETED','COMPLETED_WITH_FAILURES'}
    with sqlite3.connect(logs/'index.sqlite3') as database:
        rows=[json.loads(payload) for payload, in database.execute('SELECT payload FROM documents')]
        archives=list(database.execute('SELECT source,output,sha256 FROM archives'))
    assert len(archives)==1
    source_name,output_name,output_hash=archives[0]
    source=Path(source_name);output=Path(output_name)
    manifest=json.loads((ROOT/'qa/aw081/final_holdout_manifest.json').read_text('utf8'))
    previous=json.loads((ROOT/'qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/execution.json').read_text('utf8'))
    captures={row['index']:row for row in (json.loads(line) for line in (work/'successful_documents.jsonl').read_text('utf8').splitlines())}
    published=[json.loads(line) for line in (logs/'archive_events.jsonl').read_text('utf8').splitlines() if json.loads(line)['event']=='published']
    assert len(published)==1
    source_hash=published[0]['source_sha256']
    assert len(rows)==46 and summary['translated_documents']+summary['source_preserved_documents']==46
    assert summary['fatal_errors']==0 and summary['logging_status']=='COMPLETE'
    preserved=[]
    with ZipFile(output) as final,ZipFile(source) as initial:
        assert final.testzip() is None
        assert len([name for name in final.namelist() if name.endswith('.pdf')])==46
        assert len(final.namelist())==len(set(final.namelist()))
        for row in rows:
            member=row['archive_member_path']
            if row['output_status']=='FAILED_SOURCE_PRESERVED':
                assert final.read(member)==initial.read(member)
                preserved.append(member)
            else:
                assert row['output_status']=='TRANSLATED'
                assert sha256(final.read(row['output_archive_member'])).hexdigest()==row['output_sha256']
        assert final.read('diagnostic_metadata.json')==initial.read('diagnostic_metadata.json')
    comparisons=[]
    for row in previous['documents']:
        index=row['index']
        if row['validation']!='PASS' or index not in captures:continue
        old={(s['page'],s['block_id']):s for s in row['segments']}
        changes=[]
        for segment in captures[index]['segments']:
            prior=old.get((segment['page'],segment['block_id']))
            if not prior or prior['translated']!=segment['translated']:
                changes.append(dict(page=segment['page'],block_id=segment['block_id'],source=segment['text'],
                    before=prior['translated'] if prior else None,after=segment['translated']))
        comparisons.append(dict(index=index,unchanged=not changes,changes=changes,
            previous_blocks=len(old),current_blocks=len(captures[index]['segments'])))
    known=json.loads((ROOT/'qa/aw081/iterations/14_phase_a_closure/frozen_A_whole/semantic_review.json').read_text('utf8'))
    from app.knowledge.safety import violations
    cata=[]
    for old in known['rows']:
        if old['grade']!='CATA':continue
        page=int(old['block_id'].split('-')[0][1:])-1
        segment=next(s for s in captures[old['index']]['segments'] if s['page']==page and s['block_id']==old['block_id'])
        assert segment['text']==old['source'] and segment['translated']!=segment['text']
        assert not violations(segment['text'],segment['translated'])
        cata.append(dict(index=old['index'],block_id=old['block_id'],source=segment['text'],translated=segment['translated'],
            grade='PENDING_PUBLICATION_VISUAL_REVIEW',safety_guard_issues=[]))
    ready=json.loads((QA/'production_ready.json').read_text('utf8'))
    result=dict(scope='46_DOCUMENT_OPERATIONAL_REGRESSION_NOT_SEMANTIC_REVIEW',status=summary['status'],
        summary=summary,logs=str(logs),source_archive=str(source),source_archive_sha256=source_hash,
        output_archive=str(output),output_archive_sha256=output_hash,crc='PASS',inventory_pdf_count=46,
        successful_member_bytes_unchanged=True,failed_members_preserved_byte_for_byte=preserved,
        source_immutable=file_hash(source)==source_hash,processed=46,translated=summary['translated_documents'],
        failed_source_preserved=summary['source_preserved_documents'],fatal=0,
        previous_failures=[dict(index=r['index'],old_error=r['error_type'],new_status=next(d['output_status'] for d in rows if d['source_sha256']==r['source_sha256']))
            for r in previous['documents'] if r['validation']!='PASS'],
        previous_successful_semantics=comparisons,known_cata=cata,seconds=summary['total_wall_seconds'],
        production_unchanged=ready==production_hashes(),large_zip_started=False,
        receipt_note='Receipt rebuilt from final SQLite bindings, not early staging-path JSONL. No translation rerun.')
    assert result['production_unchanged'] and result['source_immutable'] and file_hash(output)==output_hash
    (work/'execution.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print('OPERATIONAL_COMPLETE',result['translated'],result['failed_source_preserved'])

if __name__=='__main__':
    if '--finish-existing' in sys.argv:finish_existing()
    else:run()
