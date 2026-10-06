"""Document failures continue; archive integrity/publication remain fatal."""
from dataclasses import replace
import errno
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile
import pytest
import pypdfium2 as pdfium
from tempfile import TemporaryDirectory
from tools.pdf_fixtures import make_pdf
from app.documents.control import JobControl
from app.documents.errors import DocumentError,SourceChangedError
from app.documents.job import DocumentJob,DocumentConfig
from app.documents.pdf_types import PdfError,PdfKind
from app.documents.run_metrics import file_hash
from app.documents.scanner import scan_sources
from app.engine.errors import TranslationError,TranslationCancelledError

def pdf(text):
    with TemporaryDirectory() as temporary:
        return make_pdf(Path(temporary)/'source.pdf',text,lines=1).read_bytes()

def make_zip(tmp_path):
    source=tmp_path/'manuals.zip'
    with ZipFile(source,'w') as z:
        z.writestr('bad.pdf',pdf('private bad document'))
        z.writestr('next.pdf',pdf('private next document'))
        z.writestr('asset.json',b'{"value":1}')
    return source

def execute(source,tmp_path,*,metrics=True,translator=None):
    control=JobControl();files=scan_sources([source],control).files
    completed=[];progress=[]
    job=DocumentJob(files,DocumentConfig(source='en',target='ru',ocr_enabled=False,
        output=tmp_path/'out',metrics_directory=tmp_path/'logs' if metrics else None),control,
        translator or (lambda request,event:SimpleNamespace(translated_text='Переведённый текст')),
        lambda text,s,t:('en',t),file_completed=lambda *args:completed.append(args),progress=progress.append)
    outputs=job.run()
    return job,outputs[0],completed,progress

@pytest.mark.parametrize('error',[TranslationError(),PdfError(PdfKind.UNSUPPORTED_PDF),IndexError('private backend text')])
def test_bad_pdf_is_preserved_next_pdf_translated_final_zip_and_counts(tmp_path,monkeypatch,error):
    from app.documents.backends import open_document as real_open
    import app.documents.job as module
    source=make_zip(tmp_path);before=file_hash(source)
    def open_doc(path,*args,**kwargs):
        if path.name=='bad.pdf':raise error
        return real_open(path,*args,**kwargs)
    monkeypatch.setattr(module,'open_document',open_doc)
    job,output,completed,progress=execute(source,tmp_path)
    assert job.run_status=='COMPLETED_WITH_FAILURES'
    assert progress[-1].stage=='COMPLETED_WITH_FAILURES'
    assert len(completed)==1 and completed[0][0].name=='next.pdf'
    with ZipFile(source) as original,ZipFile(output) as final:
        assert final.testzip() is None
        assert set(final.namelist())=={'bad.pdf','next_ru.pdf','asset.json'}
        assert final.read('bad.pdf')==original.read('bad.pdf')
        doc=pdfium.PdfDocument(final.read('next_ru.pdf'));page=doc[0];text=page.get_textpage()
        try:assert 'Переведённый текст' in text.get_text_range()
        finally:text.close();page.close();doc.close()
    assert file_hash(source)==before
    summary=json.loads((job.metrics_path/'run_summary.json').read_text('utf8'))
    assert summary['status']=='COMPLETED_WITH_FAILURES'
    assert summary['total_documents']==2 and summary['translated_documents']==1
    assert summary['failed_documents']==summary['source_preserved_documents']==1
    assert summary['skipped_non_documents']==1 and summary['fatal_errors']==0
    rows=[json.loads(s) for s in (job.metrics_path/'documents.jsonl').read_text('utf8').splitlines()]
    assert {r['output_status'] for r in rows}=={'TRANSLATED','FAILED_SOURCE_PRESERVED'}
    failures=[json.loads(s) for s in (job.metrics_path/'errors.jsonl').read_text('utf8').splitlines() if json.loads(s)['event']=='document_source_preserved']
    assert len(failures)==1
    assert failures[0]['original_member_preserved'] and failures[0]['source_sha256']
    assert failures[0]['exception_type']==type(error).__name__
    assert failures[0]['stage'] and failures[0]['elapsed_seconds']>=0
    assert 'private backend text' not in (job.metrics_path/'errors.jsonl').read_text('utf8')

@pytest.mark.parametrize('kind',['enospc','publication','validation','security','crc','source_changed','cancel'])
def test_global_errors_remain_fatal_and_no_final_archive(tmp_path,monkeypatch,kind):
    import app.documents.archive_job as module
    source=make_zip(tmp_path);before=source.read_bytes()
    def fail(*args,**kwargs):
        if kind=='enospc':raise OSError(errno.ENOSPC,'private disk details')
        if kind=='source_changed':raise SourceChangedError()
        if kind=='cancel':raise TranslationCancelledError()
        raise DocumentError('Injected global failure')
    operation={'enospc':'append_file','publication':'publish','validation':'validate_output',
        'security':'inventory','crc':'extract','source_changed':'publish','cancel':'extract'}[kind]
    monkeypatch.setattr(module,operation,fail)
    with pytest.raises((OSError,DocumentError,TranslationCancelledError)):
        execute(source,tmp_path)
    assert source.read_bytes()==before
    assert not list((tmp_path/'out').glob('*.zip'))
    summary=json.loads(next((tmp_path/'logs').glob('*/run_summary.json')).read_text('utf8'))
    assert summary['status']==('CANCELLED' if kind=='cancel' else 'FATAL_ARCHIVE_FAILURE')
    assert summary['fatal_errors']==(0 if kind=='cancel' else 1)

def test_logging_on_off_successful_pdf_output_is_identical(tmp_path):
    source=make_zip(tmp_path)
    one,out1,_,_=execute(source,tmp_path/'on',metrics=True)
    two,out2,_,_=execute(source,tmp_path/'off',metrics=False)
    def text_and_pixels(data):
        d=pdfium.PdfDocument(data);pages=[]
        try:
            for p in d:
                t=p.get_textpage();b=p.render(scale=1)
                try:pages.append((t.get_text_range(),b.to_pil().tobytes()))
                finally:b.close();t.close();p.close()
        finally:d.close()
        return pages
    with ZipFile(out1) as a,ZipFile(out2) as b:
        assert a.namelist()==b.namelist()
        for member in a.namelist():
            if member.endswith('.pdf'):assert text_and_pixels(a.read(member))==text_and_pixels(b.read(member))
            else:assert a.read(member)==b.read(member)

def test_recovery_policy_does_not_change_successful_pdf_semantics(tmp_path):
    source=make_zip(tmp_path)
    def fail_one(request,event):
        if request.text=='private bad document':raise TranslationError()
        return SimpleNamespace(translated_text='Переведённый текст')
    _,out1,_,_=execute(source,tmp_path/'all_good',metrics=False)
    _,out2,_,_=execute(source,tmp_path/'recovery',metrics=True,translator=fail_one)
    def read_pdf(data):
        d=pdfium.PdfDocument(data);p=d[0];t=p.get_textpage();b=p.render(scale=1)
        try:return t.get_text_range(),b.to_pil().tobytes()
        finally:b.close();t.close();p.close();d.close()
    with ZipFile(out1) as a,ZipFile(out2) as b:
        assert read_pdf(a.read('next_ru.pdf'))==read_pdf(b.read('next_ru.pdf'))

def test_known_overlap_stays_a_warning_and_in_quality_sample(tmp_path,monkeypatch):
    import app.documents.pdf_diagnostics as diagnostic
    source=make_zip(tmp_path)
    monkeypatch.setattr(diagnostic,'known_layout_findings',lambda digest:[dict(page=1,kind='table_text_overlap',status='OPEN')])
    job,_,_,_=execute(source,tmp_path)
    rows=[json.loads(s) for s in (job.metrics_path/'documents.jsonl').read_text('utf8').splitlines()]
    assert all(r['layout_status']=='WARNING_KNOWN_OVERLAP' for r in rows)
    sample=json.loads((job.metrics_path/'quality_sample_manifest.json').read_text('utf8'))
    assert len(sample['known_layout_overlap'])==2
    assert all(r['layout_status']!='PASS' for r in sample['known_layout_overlap'])

def test_preservation_cannot_collide_with_translated_member_name(tmp_path):
    source=tmp_path/'source.zip'
    with ZipFile(source,'w') as z:
        z.writestr('first.pdf',pdf('first text'));z.writestr('second.pdf',pdf('second text'))
    def translate(request,event):
        if request.text=='second text':raise TranslationError()
        return SimpleNamespace(translated_text='Перевод')
    control=JobControl();files=scan_sources([source],control).files
    job=DocumentJob(files,DocumentConfig(source='en',translate_filenames=True,template='second',output=tmp_path/'out',ocr_enabled=False),
        control,translate,lambda *args:('en','ru'))
    out,=job.run()
    with ZipFile(out) as z,ZipFile(source) as original:
        assert z.testzip() is None
        assert z.read('second.pdf')==original.read('second.pdf')
        assert 'second (1).pdf' in z.namelist()

def test_translated_nested_folder_cannot_occupy_preserved_original_path(tmp_path):
    source=tmp_path/'source.zip'
    with ZipFile(source,'w') as z:
        z.writestr('a/b/failed.pdf',pdf('broken text'))
        z.writestr('d/b/failed.pdf',pdf('copied PDF not selected'))
    control=JobControl();files=scan_sources([source],control).files[:1]
    def translate(request,event):
        if request.text=='broken text':raise TranslationError()
        return SimpleNamespace(translated_text='a' if request.text=='d' else request.text)
    job=DocumentJob(files,DocumentConfig(source='en',translate_directories=True,output=tmp_path/'out',ocr_enabled=False),
        control,translate,lambda *args:('en','ru'))
    out,=job.run()
    with ZipFile(out) as z,ZipFile(source) as original:
        assert z.testzip() is None
        assert z.read('a/b/failed.pdf')==original.read('a/b/failed.pdf')
        assert z.read('a (1)/b/failed.pdf')==original.read('d/b/failed.pdf')

@pytest.mark.parametrize('stage',['write','validate','disk_full_in_write'])
def test_document_writer_failures_continue_but_disk_full_is_fatal(tmp_path,monkeypatch,stage):
    from app.documents.pdf_document import PdfDocument
    method='validate' if stage=='validate' else 'write'
    real=getattr(PdfDocument,method)
    def operation(document,*args,**kwargs):
        if document.path.name=='bad.pdf':
            if stage=='disk_full_in_write':raise OSError(errno.ENOSPC,'no space')
            raise PdfError(PdfKind.UNSUPPORTED_PDF,dict(stage=stage,page=1))
        return real(document,*args,**kwargs)
    monkeypatch.setattr(PdfDocument,method,operation)
    source=make_zip(tmp_path)
    if stage=='disk_full_in_write':
        with pytest.raises(OSError):execute(source,tmp_path)
        assert not list((tmp_path/'out').glob('*.zip'))
    else:
        job,out,completed,_=execute(source,tmp_path)
        assert job.run_status=='COMPLETED_WITH_FAILURES' and len(completed)==1
        with ZipFile(out) as z,ZipFile(source) as original:
            assert z.testzip() is None and z.read('bad.pdf')==original.read('bad.pdf')
            assert 'next_ru.pdf' in z.namelist()
