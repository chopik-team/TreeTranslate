"""Diagnostic-only production adapter retaining the engine's direct boundary."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
QA = ROOT / 'qa/aw081'


class Trace:
    def __init__(self, engine, *, capture_events=False):
        self.engine, self.results = engine, []
        self.events = []
        if not capture_events:
            return
        from app.glossary.models import entry_metadata
        lookup = engine.glossary.lookup
        def traced_lookup(*args,**kwargs):
            matches = lookup(*args,**kwargs)
            self.events.append(dict(layer='glossary_lookup',text=args[0],selected=[dict(
                source=m.entry.source_term,target=m.entry.target_term,start=m.start,end=m.end,
                concept_id=entry_metadata(m.entry).get('concept_id'),entry_id=m.entry.id,
                store=m.store,pack=m.entry.source_pack,origin=m.entry.origin,
                trust=m.entry.trust,mode=m.entry.mode,metadata=entry_metadata(m.entry)) for m in matches]))
            return matches
        engine.glossary.lookup = traced_lookup
        template = engine._template
        def traced_template(request):
            result = template(request)
            self.events.append(dict(layer='template',text=request.text,
                selected_template=result.route_reason if result else None,
                output=result.translated_text if result else None))
            return result
        engine._template = traced_template
        translate = engine.router.translate
        def traced_model(request,*args,**kwargs):
            event = dict(layer='model',input=request.text,status='STARTED')
            self.events.append(event)
            try:
                result = translate(request,*args,**kwargs)
                event.update(status='COMPLETED',output=result.translated_text,backend=result.backend,
                             fallback_used=result.fallback_used,route_reason=result.route_reason)
                return result
            except Exception as failure:
                event.update(status='FAILED',exception_type=type(failure).__name__)
                raise
        engine.router.translate = traced_model

    def translate(self, request, *args, **kwargs):
        result = self.engine.translate(request,*args,**kwargs)
        self.results.append(result)
        return result

    def lookup_direct(self, request, *args, **kwargs):
        result = self.engine.lookup_direct(request,*args,**kwargs)
        if result is not None:
            self.results.append(result)
        return result


def run():
    from app.engine.factory import create_translation_engine
    from app.engine.errors import TranslationError
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.documents.job import DocumentJob, DocumentConfig
    from app.documents.control import JobControl
    from app.documents.pdf_fidelity import FidelityMismatch
    from app.knowledge.segments import SegmentClassifier
    cases_path = QA/'diagnostic/representative_holdout.json'
    cases = json.loads(cases_path.read_text('utf8'))['documents']
    assets = [ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db',*sorted((ROOT/'assets/config').glob('*.json'))]
    sealed = {str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in assets}
    code_sealed = {str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()
                   for p in sorted((ROOT/'app').rglob('*.py'))}
    engine = create_translation_engine(memory=TranslationMemoryEngine(QA/'diagnostic/production-tm.db'),
        glossary=GlossaryEngine(QA/'diagnostic/production-user.db',builtin_paths=bundled_paths()))
    trace = Trace(engine,capture_events=True)
    warnings = []
    job = DocumentJob([],DocumentConfig(source='zh',target='ru',domain='auto'),JobControl(),trace.translate,
                      engine.languages.resolve,warning=warnings.append)
    rows, started = [], perf_counter()
    try:
        with engine.runtime.keep_warm():
            for index, doc in enumerate(cases):
                profile = engine.profile_document('zh','ru',identity=doc['sha256'],segments=doc['lines'],
                                                   filename=doc['member'],folders=(doc['member'],))
                job._domain, job._context_profile = profile.primary_domain, profile
                job._snapshot = engine.context_router.snapshot(profile)
                for offset, source in enumerate(doc['lines']):
                    trace.results.clear()
                    trace.events.clear()
                    counters_before = dict(engine.glossary.counters)
                    job._segment_type = SegmentClassifier.classify(source).value
                    error = None
                    try:
                        output = job._pdf_translation(source,'zh','ru')
                    except (TranslationError,FidelityMismatch,IndexError) as failure:
                        output, error = source, str(failure)
                    result = trace.results[-1] if trace.results else None
                    rows.append(dict(id=f'{index}:{offset}',member=doc['member'],sha256=doc['sha256'],stratum=doc['stratum'],
                        source=source,output=output,error=error,segment_type=job._segment_type,
                        knowledge_source=result.knowledge_source if result else 'protected',
                        constraint_status=result.constraint_status if result else 'none',
                        route_reason=result.route_reason if result else None,
                        backend=result.backend if result else None,
                        fallback_used=result.fallback_used if result else False,
                        question_kind=result.question_kind if result else '',
                        events=list(trace.events),
                        glossary_counter_delta={k:v-counters_before.get(k,0) for k,v in engine.glossary.counters.items()
                                               if v!=counters_before.get(k,0)},
                        profile=profile.summary()))
                print('diagnostic',index+1,len(cases),'segments',len(rows),'seconds',round(perf_counter()-started,2),flush=True)
    finally:
        engine.shutdown()
    assert all(sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in sealed.items())
    assert all(sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in code_sealed.items())
    result = dict(set_id='DIAGNOSTIC_REGRESSION_SET',final_proof=False,whole_documents=len(cases),segments=len(rows),
        seconds=perf_counter()-started,manifest_sha256=sha256(cases_path.read_bytes()).hexdigest(),
        production_direct_boundary_retained=True,knowledge_hashes=sealed,rows=rows,warnings=warnings,
        production_code_sha256=code_sealed,
        knowledge_sources=dict(Counter(r['knowledge_source'] for r in rows)))
    (QA/'diagnostic/holdout_after_production.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')


if __name__ == '__main__':
    run()
