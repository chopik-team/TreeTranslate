"""Bounded execution, canonical publication, real PDF recovery and cancellation."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile, BadZipFile
from threading import Event, Thread, enumerate as threads
from time import sleep
import json
import pytest

from app.documents.pipeline import PipelineCapabilities, PipelineHardwarePlan, SchedulePolicy, StagedPipeline, WorkItem, GIB, MIB
from app.documents.control import JobControl
from app.engine.errors import TranslationCancelledError, TranslationError
from app.documents.errors import SourceChangedError, DocumentError


def plan(depth=3, budget=256*MIB):
    return PipelineHardwarePlan(1,1,depth,max(1,depth-1),1,budget,budget,2*GIB,1)


@pytest.mark.parametrize('cpu,ram,vram,cuda',[(4,8,0,False),(8,16,4,True),(16,32,12,True),(32,64,24,True)])
def test_planner_bounds_and_pressure(cpu,ram,vram,cuda):
    caps=PipelineCapabilities(cpu,max(1,cpu//2),ram*GIB,int(ram*.8*GIB),cuda,vram*GIB,int(vram*.8*GIB),768*MIB,2*GIB,.2)
    chosen=PipelineHardwarePlan.build(caps)
    assert 1<=chosen.depth<=3 and chosen.gpu_owners==1
    assert chosen.prepare_workers+chosen.semantic_workers <= max(2,cpu-chosen.cpu_headroom)
    assert 0<=chosen.max_inflight_bytes<=max(0,caps.ram_available-chosen.ram_reserve_bytes)
    assert chosen.writer_depth==1
    assert PipelineHardwarePlan.build(replace(caps,memory_pressure=.9)).depth==1
    assert PipelineHardwarePlan.build(replace(caps,ram_available=0)).depth==1
    assert 'quality' not in chosen.as_dict()


def test_stronger_hardware_does_not_reduce_capacity():
    plans=[PipelineHardwarePlan.build(PipelineCapabilities(c,c//2,r*GIB,int(r*.8*GIB),True,v*GIB,int(v*.8*GIB)))
           for c,r,v in [(4,8,0),(8,16,4),(16,32,12),(32,64,24)]]
    assert [p.depth for p in plans]==sorted(p.depth for p in plans)
    assert [p.max_inflight_bytes for p in plans]==sorted(p.max_inflight_bytes for p in plans)


@pytest.mark.parametrize('policy',[SchedulePolicy.ORIGINAL,SchedulePolicy.EASY_FIRST])
def test_reversed_execution_slow_writer_and_canonical_commit(policy):
    pipeline=StagedPipeline(plan(),JobControl(),policy,pressure=lambda:0)
    prepared=[];translated=[];written=[];committed=[];cleaned=[]
    items=[WorkItem(i,str(i),32*MIB,3-i,value=str(i)) for i in range(6)]
    def prepare(item):
        prepared.append(item.sequence_id);item.current_bytes=10
        return item.value
    def translate(item):
        translated.append(item.sequence_id)
        return item.value
    def write(item):
        sleep(.01);written.append(item.sequence_id)
        return item.value
    pipeline.run(items,prepare,translate,write,lambda i:committed.append(i.sequence_id),lambda i:cleaned.append(i.sequence_id))
    assert committed==cleaned==list(range(6))
    assert len(set(written))==6
    if policy==SchedulePolicy.EASY_FIRST:
        assert prepared[0]==translated[0]==written[0]==2
    assert pipeline.metrics['inflight_high_water']<=3
    assert pipeline.metrics['estimated_bytes_high_water']<=plan().max_inflight_bytes
    assert pipeline.metrics['workers_joined'] and not any(t.name.startswith('tt-') for t in threads())


@pytest.mark.parametrize('failed_stage',['prepare','translate','write'])
def test_child_failure_between_successes_releases_leases(failed_stage):
    pipeline=StagedPipeline(plan(),JobControl(),pressure=lambda:0)
    result=[];clean=[]
    def callback(stage):
        def call(item):
            if item.sequence_id==1 and stage==failed_stage:
                raise TranslationError()
            return item.value
        return call
    pipeline.run([WorkItem(i,i,32*MIB,value=i) for i in range(5)],callback('prepare'),callback('translate'),callback('write'),
        lambda i:result.append((i.sequence_id,type(i.error).__name__ if i.error else 'ok')),lambda i:clean.append(i.sequence_id))
    assert result==[(0,'ok'),(1,'TranslationError'),(2,'ok'),(3,'ok'),(4,'ok')]
    assert clean==list(range(5)) and pipeline.metrics['remaining_inflight']==0


@pytest.mark.parametrize('operation',['cancel','append_failure','fatal_prepare'])
def test_cancel_or_fatal_joins_workers_and_cleans_nonempty_queues(operation):
    control=JobControl();pipeline=StagedPipeline(plan(),control,pressure=lambda:0)
    cleaned=[];prepared=[];committed=[]
    def prepare(item):
        prepared.append(item.sequence_id)
        if operation=='fatal_prepare' and item.sequence_id==0:
            raise OSError('injected')
        return item.value
    def translate(item):
        if operation=='cancel':control.cancel();control.checkpoint()
        return item.value
    def commit(item):
        if operation=='append_failure':raise OSError('injected append')
        committed.append(item.sequence_id)
    with pytest.raises((OSError,TranslationCancelledError)):
        pipeline.run([WorkItem(i,i,32*MIB,value=i) for i in range(8)],prepare,translate,lambda i:i.value,commit,
            lambda i:cleaned.append(i.sequence_id))
    assert sorted(cleaned)==[0,1,2] and not committed
    assert pipeline.metrics['workers_joined'] and not any(t.name.startswith('tt-') for t in threads())


def test_memory_and_pressure_backpressure_prevents_eager_preparation():
    pressure=[0.]
    pipeline=StagedPipeline(plan(3,64*MIB),JobControl(),pressure=lambda:pressure[0])
    prepared=[];committed=[]
    def prepare(item):prepared.append(item.sequence_id);return item.value
    def translate(item):
        assert len(prepared)-len(committed)<=2
        pressure[0]=.95
        return item.value
    pipeline.run([WorkItem(i,i,32*MIB,value=i) for i in range(10)],prepare,translate,lambda i:i.value,
        lambda i:committed.append(i.sequence_id))
    assert committed==list(range(10))
    assert pipeline.metrics['estimated_bytes_high_water']<=64*MIB


def test_gpu_admission_serializes_before_ocr_model_release_and_translation():
    pipeline=StagedPipeline(plan(),JobControl(),pressure=lambda:0)
    entered=Event();ocr=Event()
    def recognition():
        entered.set()
        with pipeline.gpu.own('ocr'):ocr.set()
    with pipeline.gpu.own('nmt'):
        worker=Thread(target=recognition);worker.start()
        assert entered.wait(1) and not ocr.wait(.03)
    worker.join(1)
    assert ocr.is_set() and not worker.is_alive()


def real_archive(tmp_path, depth, policy=SchedulePolicy.ORIGINAL, fail=None, hook=None):
    from tools.pdf_fixtures import make_pdf
    from app.documents.scanner import scan_sources
    from app.documents.job import DocumentJob,DocumentConfig
    from app.documents.run_metrics import LocalRun
    folder=tmp_path/('d'+str(depth)+'_'+policy.value)
    folder.mkdir(parents=True)
    source=tmp_path/'source.zip'
    if not source.exists():
        with ZipFile(source,'w') as z:
            for i,name in enumerate(['first.pdf','bad.pdf','third.pdf','taken.pdf']):
                file=make_pdf(tmp_path/(str(i)+'.pdf'),f'body document {i}',lines=1)
                z.writestr('folder/'+name,file.read_bytes())
            z.writestr('asset.txt',b'asset')
    control=JobControl()
    def translate(req,event):
        if fail and req.text.startswith('body document 1'):raise TranslationError()
        return SimpleNamespace(translated_text='taken' if req.segment_type=='FILENAME' else 'Перевод документа')
    job=DocumentJob(scan_sources([source],control).files,DocumentConfig(source='en',target='ru',
        output=folder/'out',metrics_directory=folder/'logs',ocr_enabled=False,translate_filenames=True,template='{name}'),
        control,translate,lambda *args:('en','ru'))
    job._pipeline_plan=plan(depth)
    job._pipeline_policy=policy
    if hook:hook(job)
    output,=job.run()
    return job,output


@pytest.mark.parametrize('depth,policy',[(2,SchedulePolicy.ORIGINAL),(3,SchedulePolicy.ORIGINAL),(3,SchedulePolicy.EASY_FIRST)])
def test_real_pdf_depth1_equivalence_collisions_preservation_and_binding(tmp_path,depth,policy):
    from tools.aw081_hardware_scaling_20 import fingerprint_pdf
    one,out1=real_archive(tmp_path,1,fail=True)
    job,out2=real_archive(tmp_path,depth,policy,fail=True)
    with ZipFile(out1) as a,ZipFile(out2) as b,ZipFile(tmp_path/'source.zip') as original:
        assert a.namelist()==b.namelist() and b.testzip() is None
        assert b.read('folder/bad.pdf')==original.read('folder/bad.pdf')
        assert 'folder/taken.pdf' not in b.namelist()
        for member in a.namelist():
            if member.endswith('.pdf'):
                assert fingerprint_pdf(a.read(member),True)==fingerprint_pdf(b.read(member),True)
            else:assert a.read(member)==b.read(member)
    summary=json.loads((job.metrics_path/'run_summary.json').read_text('utf8'))
    assert summary['logging_status']=='COMPLETE' and summary['translated_documents']==3
    assert summary['failed_documents']==1 and summary['fatal_errors']==0
    assert not list((out2.parent).glob('.treetranslate-*'))
    assert not any(t.name.startswith('tt-') for t in threads())
    rows=[json.loads(s) for s in (job.metrics_path/'documents.jsonl').read_text('utf8').splitlines()]
    assert len(rows)==4 and len({r['document_id'] for r in rows})==4
    for row in rows:
        assert row['archive_member_path'].split('/')[-1] in {'first.pdf','bad.pdf','third.pdf','taken.pdf'}


@pytest.mark.parametrize('stage',['ocr','writer','append','cancel'])
def test_real_archive_injected_errors_cleanup_and_atomicity(tmp_path,monkeypatch,stage):
    import app.documents.job as jobs
    import app.documents.archive_pipeline as adapter
    from app.documents.pdf_document import PdfDocument
    if stage=='ocr':
        original=jobs.open_document
        def fail(path,*args,**kwargs):
            if path.name=='bad.pdf':raise TranslationError()
            return original(path,*args,**kwargs)
        monkeypatch.setattr(jobs,'open_document',fail)
    elif stage=='writer':
        original=PdfDocument.write
        def fail(doc,*args,**kwargs):
            if doc.path.name=='bad.pdf':raise TranslationError()
            return original(doc,*args,**kwargs)
        # PdfDocument source path is public in the writer implementation.
        monkeypatch.setattr(PdfDocument,'write',fail)
    else:
        original=adapter.append_file
        def fail(*args,**kwargs):raise OSError('append failure')
        monkeypatch.setattr(adapter,'append_file',fail)
    if stage in {'append','cancel'}:
        if stage=='cancel':
            def hook(job):
                def fail(*args,**kwargs):job.control.cancel();job.control.checkpoint()
                monkeypatch.setattr(adapter,'append_file',fail)
        else:hook=None
        with pytest.raises((OSError,TranslationCancelledError)):
            real_archive(tmp_path,3,hook=hook)
        assert not list(tmp_path.rglob('*out/*.zip'))
    else:
        job,output=real_archive(tmp_path,3)
        assert job.archive_summaries[0]['failed_documents']==1
        with ZipFile(output) as z,ZipFile(tmp_path/'source.zip') as source:
            assert z.read('folder/bad.pdf')==source.read('folder/bad.pdf')
    assert not any(t.name.startswith('tt-') for t in threads())


def test_easy_first_writer_failure_keeps_serial_collision_reservations(tmp_path,monkeypatch):
    from app.documents.pdf_document import PdfDocument
    original=PdfDocument.write
    def write(doc,*args,**kwargs):
        if doc.path.name=='bad.pdf':raise TranslationError()
        return original(doc,*args,**kwargs)
    monkeypatch.setattr(PdfDocument,'write',write)
    _,before=real_archive(tmp_path,1)
    _,after=real_archive(tmp_path,3,SchedulePolicy.EASY_FIRST)
    with ZipFile(before) as a,ZipFile(after) as b:
        assert a.namelist()==b.namelist()
        assert b.read('folder/bad.pdf')==a.read('folder/bad.pdf')


def test_pause_then_cancel_with_admitted_items_wakes_all_workers():
    control=JobControl();pipeline=StagedPipeline(plan(),control,pressure=lambda:0)
    paused=Event();finished=Event();errors=[];clean=[]
    def translate(item):
        control.pause();paused.set();pipeline.checkpoint()
        return item.value
    def run():
        try:
            pipeline.run([WorkItem(i,i,32*MIB,value=i) for i in range(8)],lambda i:i.value,
                translate,lambda i:i.value,lambda i:None,lambda i:clean.append(i.sequence_id))
        except TranslationCancelledError:errors.append('cancelled')
        finally:finished.set()
    worker=Thread(target=run);worker.start()
    assert paused.wait(2)
    control.cancel()
    assert finished.wait(2)
    worker.join(1)
    assert errors==['cancelled'] and sorted(clean)==[0,1,2]
    assert not any(t.name.startswith('tt-') for t in threads())


def test_easy_first_cheap_writer_finishes_before_heavy_prepare_takes_pdf_lock():
    pipeline=StagedPipeline(plan(2),JobControl(),SchedulePolicy.EASY_FIRST,pressure=lambda:0)
    first_written=Event()
    def prepare(item):
        if item.sequence_id==0:
            assert first_written.is_set()
        return item.value
    def write(item):
        if item.sequence_id==1:first_written.set()
        return item.value
    committed=[]
    pipeline.run([WorkItem(0,0,32*MIB,100,value=0),WorkItem(1,1,32*MIB,1,value=1)],
        prepare,lambda i:i.value,write,lambda i:committed.append(i.sequence_id))
    assert committed==[0,1]


def test_thousand_member_pipeline_starts_first_child_without_path_translation(tmp_path,monkeypatch):
    from app.documents.job import DocumentJob,DocumentConfig
    from app.documents.scanner import scan_sources
    from test_zip_output import docx_bytes
    source=tmp_path/'thousand.zip'
    payload=docx_bytes()
    with ZipFile(source,'w') as z:
        for index in range(1000):z.writestr(f'目录{index}/文件.docx',payload)
    control=JobControl();calls=[];entered=[]
    def translate(request,event):
        calls.append(request)
        return SimpleNamespace(translated_text='Имя')
    original=DocumentJob._document_stages
    def stages(child):
        if getattr(child,'_pipeline_active',False):
            entered.append(child.files[0].relative.as_posix())
            assert not calls and not tuple(child.config.output.rglob('*'))
            control.cancel();control.checkpoint()
        yield from original(child)
    monkeypatch.setattr(DocumentJob,'_document_stages',stages)
    job=DocumentJob(scan_sources([source],control).files,DocumentConfig(source='zh',target='ru',
        output=tmp_path/'out',translate_filenames=True,translate_directories=True),
        control,translate,lambda *args:('zh','ru'))
    job._pipeline_plan=plan(2)
    with pytest.raises(TranslationCancelledError):job.run()
    assert entered==['目录0/文件.docx'] and not calls
    assert not list((tmp_path/'out').iterdir())
    assert not any(t.name.startswith('tt-') for t in threads())


@pytest.mark.parametrize('exception',[BadZipFile, DocumentError])
def test_container_extract_failure_retains_original_global_exception_and_io_category(tmp_path,monkeypatch,exception):
    import app.documents.archive_pipeline as adapter
    def extract(*args,**kwargs):raise exception('injected container failure')
    monkeypatch.setattr(adapter,'extract',extract)
    with pytest.raises(exception):real_archive(tmp_path,2)
    folder=tmp_path/'d2_original'
    summary=json.loads(next((folder/'logs').glob('*/run_summary.json')).read_text('utf8'))
    assert summary['status']=='FATAL_ARCHIVE_FAILURE' and summary['fatal_errors']==1
    events=[json.loads(s) for s in next((folder/'logs').glob('*/archive_events.jsonl')).read_text('utf8').splitlines()]
    fatal=next(e for e in events if e['event']=='fatal')
    assert fatal['exception_type']==exception.__name__ and fatal['primary_category']=='ARCHIVE_IO'
    assert not list((folder/'out').iterdir())
    assert not any(t.name.startswith('tt-') for t in threads())
