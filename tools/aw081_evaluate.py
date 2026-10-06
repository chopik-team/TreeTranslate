"""Run the frozen native-line benchmark without touching historical QA."""
import json
import sqlite3
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QA = ROOT / 'qa/aw081'


def save(name, data):
    (QA / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf8')


def run(stage):
    if stage not in {'before_production','after_production'}:
        raise ValueError('Unknown evaluation stage')
    if stage=='before_production' and (QA/'final_holdout_before.json').exists():
        raise RuntimeError('The frozen baseline already exists and must not be overwritten')
    manifest = QA / 'final_holdout_manifest.json'
    frozen = json.loads(manifest.read_text('utf8'))
    case_path = QA / 'representative_holdout.json'
    if not case_path.exists():
        documents = []
        with sqlite3.connect(ROOT / 'qa/aw088/native_corpus.db') as connection:
            for item in frozen['documents']:
                digest, raw = connection.execute('SELECT sha256,payload FROM documents WHERE member=?',
                                                  (item['member'],)).fetchone()
                assert digest == item['sha256']
                documents.append(dict(item, lines=json.loads(raw)['lines']))
        save(case_path.name, dict(set_id=frozen['set_id'], documents=documents,
             manifest_sha256=sha256(manifest.read_bytes()).hexdigest(),
             definition='Frozen native lines; PDF writer validation and semantic review are separate checks.'))
    from app.engine.factory import create_translation_engine
    from app.engine.errors import TranslationError
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.documents.job import DocumentJob, DocumentConfig
    from app.documents.control import JobControl
    from app.documents.pdf_fidelity import FidelityMismatch
    from app.knowledge.segments import SegmentClassifier
    from time import perf_counter
    from collections import Counter
    baseline = stage == 'before_production'
    engine = create_translation_engine(memory=TranslationMemoryEngine(QA / f'{stage}-isolated-tm.db'),
        glossary=GlossaryEngine(QA / f'{stage}-isolated-user.db', builtin_paths=
            [QA / 'baseline/aw083-body-repair-zh-ru.db'] if baseline else bundled_paths()))
    if baseline:
        from app.knowledge.profile import DocumentProfiler
        engine.context_router.profiler = DocumentProfiler(json.loads((QA / 'baseline/knowledge-context.json').read_text('utf8')))
        engine.context_router.templates = json.loads((QA / 'baseline/knowledge-templates.json').read_text('utf8'))['templates']
        engine.context_router.slot_forms = {f['source']: f for f in json.loads((QA / 'baseline/automotive-slot-forms.json').read_text('utf8'))['forms']}
    trace = []
    def translate(request, *args, **kwargs):
        result = engine.translate(request, *args, **kwargs)
        trace.append(result)
        return result
    warnings = []
    if not baseline:
        from tools.aw081_diagnostic_evaluate import Trace
        adapter = Trace(engine)
        translate, trace = adapter.translate, adapter.results
    assets = [ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db',*sorted((ROOT/'assets/config').glob('*.json'))]
    sealed = {str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in assets}
    job = DocumentJob([], DocumentConfig(source='zh', target='ru', domain='auto'), JobControl(), translate,
                      engine.languages.resolve,warning=warnings.append)
    rows = []
    started = perf_counter()
    try:
        with engine.runtime.keep_warm():
            for index, doc in enumerate(json.loads(case_path.read_text('utf8'))['documents']):
                p = engine.profile_document('zh', 'ru', identity=doc['sha256'], segments=doc['lines'], filename=doc['member'], folders=(doc['member'],))
                snapshot = engine.context_router.snapshot(p)
                job._domain, job._context_profile, job._snapshot = p.primary_domain, p, snapshot
                for offset, line in enumerate(doc['lines']):
                    trace.clear()
                    job._segment_type = SegmentClassifier.classify(line).value
                    error = None
                    try:
                        output = job._pdf_translation(line, 'zh', 'ru')
                    except (FidelityMismatch, TranslationError, IndexError) as failure:
                        output, error = line, str(failure)
                    result = trace[-1] if trace else None
                    rows.append(dict(id=f'{index}:{offset}', member=doc['member'], source=line, output=output,
                        error=error, knowledge_source=result.knowledge_source if result else 'protected',
                        constraint_status=result.constraint_status if result else 'none'))
                save(f'final_holdout_{"before" if baseline else "after"}.json', dict(set_id=frozen['set_id'],
                    complete=index + 1 == len(frozen['documents']), whole_documents=index + 1,
                    manifest_sha256=sha256(manifest.read_bytes()).hexdigest(), rows=rows,
                    production_direct_boundary_retained=not baseline,
                    adapter_difference='The historical baseline used a bare trace function; after-mode retains the production direct-lookup boundary.',
                    knowledge_hashes=sealed,warnings=warnings,
                    seconds=perf_counter()-started, knowledge_sources=dict(Counter(r['knowledge_source'] for r in rows))))
                print(stage, index + 1, len(frozen['documents']), 'segments', len(rows), 'seconds', round(perf_counter()-started, 2), flush=True)
    finally:
        engine.shutdown()
    assert all(sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in sealed.items())


if __name__ == '__main__':
    run(sys.argv[1])
