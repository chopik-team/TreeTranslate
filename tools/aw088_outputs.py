"""Actual production PDF runs and read-only historical regression capture."""
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw088_prepare import QA,ZIP,save


def samples(retry=False):
    from PySide6.QtWidgets import QApplication
    from app.config.logging_config import configure_logging,document_run
    from app.engine.factory import create_translation_engine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.documents.scanner import scan_sources
    from app.documents.control import JobControl
    from app.documents.job import DocumentJob,DocumentConfig
    from app.documents.pdf_document import PdfDocument
    app=QApplication.instance() or QApplication([]);configure_logging()
    frozen=json.loads((QA/'representative_holdout.json').read_text('utf8'))
    destination=ROOT/'output/aw088/comparison';destination.mkdir(parents=True,exist_ok=True)
    source=destination/'CN7C_test_originals.zip'
    with ZipFile(ZIP) as original,ZipFile(source,'w',ZIP_DEFLATED,allowZip64=True) as output:
        for d in frozen['documents']:
            info=original.getinfo(d['member']);assert info.file_size<=16*1024*1024
            data=original.read(info);assert sha256(data).hexdigest()==d['sha256']
            output.writestr(info,data)
    engine=create_translation_engine(memory=TranslationMemoryEngine(QA/'samples-isolated-tm.db'),
        glossary=GlossaryEngine(QA/'samples-isolated-user.db',builtin_paths=bundled_paths()))
    prior=json.loads((QA/'sample_pdf_e2e.json').read_text('utf8')) if retry else None
    records=[r for r in prior['documents'] if r.get('validation')=='PASS'] if prior else []
    original_validate=PdfDocument.validate
    def validate(document,path):
        record=dict(file=str(document.path),source_pages=len(document.pages),output_pages=len(document.pages)+document.continuation_count,
            segments=[asdict(s) for s in document.segments],output_hash=sha256(Path(path).read_bytes()).hexdigest())
        try:result=original_validate(document,path)
        except Exception as error:
            import shutil
            debug=QA/'debug';debug.mkdir(exist_ok=True)
            shutil.copy2(path,debug/f'failed-{len(records)}.pdf')
            record.update(validation='FAILED',error=str(error));records.append(record)
            save('sample_pdf_failure.json',record);raise
        record['validation']='PASS';records.append(record)
        return result
    PdfDocument.validate=validate
    control=JobControl();warnings=[];start=perf_counter();last=[0]
    def progress(value):
        if perf_counter()-last[0]>25:
            print('SAMPLES',value.file_index,value.file_total,value.stage,round(perf_counter()-start,2),flush=True);last[0]=perf_counter()
    job=DocumentJob(scan_sources([source],control).files,DocumentConfig(source='zh',target='ru',output=destination,
        domain='auto',translate_directories=False,translate_filenames=False),control,engine.translate,engine.languages.resolve,
        warning=warnings.append,progress=progress)
    try:
        retry_members={frozen['documents'][i]['member'] for i in [4,5]}
        outputs=[Path(p) for p in prior['outputs']] if prior else []
        failures=[f for f in prior['failures'] if f['member'] not in retry_members] if prior else []
        from tempfile import TemporaryDirectory
        from app.documents.scanner import SourceFile
        with engine.runtime.keep_warm(),TemporaryDirectory(prefix='TreeTranslate-aw088-samples-') as temporary,ZipFile(source) as archive:
            for index,d in enumerate(frozen['documents']):
                if retry and d['member'] not in retry_members:continue
                path=Path(temporary)/f'sample-{index:02}.pdf';path.write_bytes(archive.read(d['member']))
                parent=engine.profile_document('zh','ru',identity=d['sha256'],segments=d['lines'],filename=d['member'],folders=(d['member'],))
                item=SourceFile(path,Path(temporary),Path(d['member']),path.stat().st_size)
                child=DocumentJob([item],DocumentConfig(source='zh',target='ru',output=destination/'translated',domain='auto',parent_context=parent),
                    control,engine.translate,engine.languages.resolve,warning=warnings.append,progress=progress)
                try:
                    with document_run(child.run_id):outputs.extend(child.run())
                except Exception as error:
                    failures.append(dict(member=d['member'],error=type(error).__name__,message=str(error)))
                print('SAMPLE',index+1,'validated',len(outputs),'failed',len(failures),flush=True)
        save('sample_pdf_e2e.json',dict(source=str(source),outputs=[str(p) for p in outputs],documents=records,
            warnings=warnings,failures=failures,seconds=perf_counter()-start,source_sha256=sha256(source.read_bytes()).hexdigest(),
            definition='Whole frozen held PDFs through production writer, not certified perfect translations; compare with semantic review.'))
        print('SAMPLES COMPLETE',len(records),round(perf_counter()-start,2),flush=True)
    finally:engine.shutdown();PdfDocument.validate=original_validate


def historical():
    from app.engine.factory import create_translation_engine
    from app.engine.types import TranslationRequest
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.knowledge.profile import DocumentProfiler
    engine=create_translation_engine(memory=TranslationMemoryEngine(QA/'historical-isolated-tm.db'),
        glossary=GlossaryEngine(QA/'historical-isolated-user.db',builtin_paths=bundled_paths()))
    rows=[];start=perf_counter()
    try:
        with engine.runtime.keep_warm():
            for cycle,name,key,baseline_name in [('aw085','holdout_fresh.json','entries','holdout_regression.json'),
                    ('aw087','automotive_semantic_holdout.json','rows','semantic_holdout_results.json')]:
                path=ROOT/'qa'/cycle/name;digest=sha256(path.read_bytes()).hexdigest();cases=json.loads(path.read_text('utf8'))[key]
                previous=json.loads((ROOT/'qa/aw087'/baseline_name).read_text('utf8'))['rows']
                shared=engine.profile_document('zh','ru',segments=[c['source'] for c in cases])
                result=[]
                for c,old in zip(cases,previous):
                    p=engine.profile_document('zh','ru',segments=[c['profile_cues']]) if 'profile_cues' in c else shared
                    r=engine.translate(TranslationRequest(c['source'],'zh','ru',domain='auto',context_profile=p,segment_type=c.get('segment_type','')))
                    before=old.get('output',old.get('after'))
                    result.append(dict(c,before=before,after=r.translated_text,unchanged=before==r.translated_text,
                        baseline_grade=old.get('grade','REVIEW_REQUIRED'),knowledge_source=r.knowledge_source))
                assert sha256(path.read_bytes()).hexdigest()==digest
                rows.append(dict(cycle=cycle,reference_sha256=digest,references_unchanged=True,rows=result))
        held=ROOT/'qa/aw086/profiler_holdout.json';digest=sha256(held.read_bytes()).hexdigest();profiler=DocumentProfiler();profiles=[]
        for c in json.loads(held.read_text('utf8'))['cases']:
            p=profiler.profile('zh','ru',segments=c['texts']);profiles.append(dict(c,profile=p.summary(),
                passed=p.primary_domain==c['domain'] and set(c['branches'])<=set(dict(p.subdomains))))
        assert sha256(held.read_bytes()).hexdigest()==digest
        save('old_holdout_regression.json',dict(evaluations=rows,profiler=profiles,seconds=perf_counter()-start,
            references_unchanged=True,knowledge_updated_from_failures=False))
        print('HISTORICAL COMPLETE',len(profiles),round(perf_counter()-start,2),flush=True)
    finally:engine.shutdown()


def e2e():
    from tools import aw086_e2e
    aw086_e2e.QA=QA
    for mode in ['body','coolant']:aw086_e2e.run(mode,cycle='aw088',capture_routes=True)


if __name__=='__main__':samples(True) if sys.argv[1]=='retry' else globals()[sys.argv[1]]()
