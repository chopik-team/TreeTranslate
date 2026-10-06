"""Normal PDF jobs for existing diagnostic sources; no implicit semantic grades."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from types import MethodType

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'


def run(indices=None, report='whole_diagnostic_probe.json', output=None):
    from app.engine.factory import create_translation_engine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.documents.job import DocumentJob, DocumentConfig
    from app.documents.scanner import SourceFile
    from app.documents.control import JobControl
    from app.documents.pdf_document import PdfDocument
    from tools.aw081_diagnostic_evaluate import Trace

    cases = json.loads((ROOT/'qa/aw088/representative_holdout.json').read_text('utf8'))['documents']
    selected=tuple(range(len(cases))) if indices is None else tuple(indices)
    assert selected and len(set(selected))==len(selected) and all(0<=i<len(cases) for i in selected)
    code = {p:sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app').rglob('*.py')}
    assets = list((ROOT/'assets/config').glob('*.json')) + list(bundled_paths())
    assets += [ROOT/'assets/knowledge/manifest.json']
    sealed = {p:sha256(p.read_bytes()).hexdigest() for p in assets}
    engine = create_translation_engine(memory=TranslationMemoryEngine(QA/'whole-diagnostic-isolated-tm.db'),
        glossary=GlossaryEngine(QA/'whole-diagnostic-isolated-user.db',builtin_paths=bundled_paths()))
    trace = Trace(engine,capture_events=True)
    routes, documents, warnings = [], [], []
    real_translate, real_direct = engine.translate, engine.lookup_direct
    index = None

    def capture(method, request, args, kwargs, kind):
        trace.events.clear()
        result = method(request,*args,**kwargs)
        routes.append(dict(index=index,kind=kind,source=request.text,
            output=result.translated_text if result else None,
            route_reason=result.route_reason if result else None,
            constraint_status=result.constraint_status if result else None,
            segment_type=request.segment_type,events=list(trace.events)))
        return result

    engine.translate = MethodType(lambda self,request,*args,**kwargs:
        capture(real_translate,request,args,kwargs,'translate'),engine)
    engine.lookup_direct = MethodType(lambda self,request,*args,**kwargs:
        capture(real_direct,request,args,kwargs,'direct_lookup'),engine)
    original_validate = PdfDocument.validate

    def validate(document, output):
        result = original_validate(document,output)
        documents.append(dict(index=index,validation='PASS',
            source_pages=len(document.pages),output_pages=len(document.pages)+document.continuation_count,
            output_sha256=sha256(Path(output).read_bytes()).hexdigest(),
            segments=[asdict(segment) for segment in document.segments]))
        return result

    PdfDocument.validate = validate
    started = perf_counter()
    destination = ROOT/output if output else ROOT/'output/aw081/whole_diagnostic'
    destination.mkdir(parents=True,exist_ok=True)
    try:
        with engine.runtime.keep_warm():
            for index in selected:
                item=cases[index]
                source = QA/f'diagnostic/originals/{index}.pdf'
                assert sha256(source.read_bytes()).hexdigest()==item['sha256']
                profile = engine.profile_document('zh','ru',identity=item['sha256'],
                    segments=item['lines'],filename=item['member'],folders=(item['member'],))
                # Numeric cache filenames must not discard the real archive's
                # folder evidence used by normal production profiling.
                job = DocumentJob([SourceFile(source,source.parent,Path(item['member']),source.stat().st_size)],
                    DocumentConfig(source='zh',target='ru',domain='auto',parent_context=profile,output=destination),
                    JobControl(),engine.translate,engine.languages.resolve,warning=warnings.append)
                begin = perf_counter()
                try:
                    outputs = job.run()
                    record = next(record for record in reversed(documents) if record['index']==index)
                    record.update(member=item['member'],source_sha256=item['sha256'],
                        output=str(outputs[-1]),seconds=perf_counter()-begin,
                        semantic_status='UNREVIEWED')
                except Exception as error:
                    documents.append(dict(index=index,member=item['member'],validation='FAILED',
                        error=type(error).__name__,message=str(error),seconds=perf_counter()-begin))
                assert sha256(source.read_bytes()).hexdigest()==item['sha256']
                print('WHOLE PDF',index,documents[-1]['validation'],round(perf_counter()-begin,2),flush=True)
    finally:
        PdfDocument.validate = original_validate
        engine.shutdown()
    assert all(sha256(path.read_bytes()).hexdigest()==digest for path,digest in code.items())
    assert all(sha256(path.read_bytes()).hexdigest()==digest for path,digest in sealed.items())
    result = dict(revision='AW0.81',scope='Whole existing diagnostic PDFs, normal production extraction and writer.',
        final_proof=False,semantic_acceptance=False,raw_157_grades_unchanged=True,
        seconds=perf_counter()-started,timing_is_calibration=False,
        production_hashes={str(p.relative_to(ROOT)):h for p,h in {**code,**sealed}.items()},
        selected_indices=selected,documents=documents,routes=routes,warnings=warnings)
    report_path=QA/report
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--indices',nargs='+',type=int)
    parser.add_argument('--report',default='whole_diagnostic_probe.json')
    parser.add_argument('--output')
    args=parser.parse_args()
    run(args.indices,args.report,args.output)
