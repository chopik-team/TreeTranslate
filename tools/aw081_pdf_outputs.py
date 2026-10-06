"""Actual diagnostic PDFs through the normal document job and strict writer."""
from pathlib import Path
from dataclasses import asdict
from hashlib import sha256
from time import perf_counter
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QA = ROOT / 'qa/aw081'


def run(indices=(10,16)):
    from app.engine.factory import create_translation_engine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.documents.job import DocumentJob, DocumentConfig
    from app.documents.scanner import SourceFile
    from app.documents.control import JobControl
    from app.documents.pdf_document import PdfDocument
    engine = create_translation_engine(memory=TranslationMemoryEngine(QA / 'blockers-isolated-tm.db'),
        glossary=GlossaryEngine(QA / 'blockers-isolated-user.db', builtin_paths=bundled_paths()))
    frozen = json.loads((ROOT / 'qa/aw088/representative_holdout.json').read_text('utf8'))['documents']
    destination = ROOT / 'output/aw081/pdf_blockers'
    destination.mkdir(parents=True, exist_ok=True)
    records, warnings = [], []
    validate_original = PdfDocument.validate
    def validate(document, output):
        record = dict(source_sha256=document.source_hash, output=str(output),
            source_pages=len(document.pages), continuation_pages=document.continuation_count,
            segments=[asdict(s) for s in document.segments])
        try:
            result = validate_original(document, output)
        except Exception as error:
            import shutil
            debug = QA/'pdf_blockers/translated-failure.pdf'
            shutil.copy2(output, debug)
            record.update(validation='FAILED', error=str(error), debug=str(debug))
            records.append(record)
            raise
        record['validation'] = 'PASS'
        records.append(record)
        return result
    PdfDocument.validate = validate
    started = perf_counter()
    try:
        with engine.runtime.keep_warm():
            for index in indices:
                item = frozen[index]
                source = QA / f'pdf_blockers/original-{index}.pdf'
                assert sha256(source.read_bytes()).hexdigest() == item['sha256']
                profile = engine.profile_document('zh', 'ru', identity=item['sha256'], segments=item['lines'], filename=item['member'], folders=(item['member'],))
                config = DocumentConfig(source='zh', target='ru', domain='auto', parent_context=profile, output=destination)
                job = DocumentJob([SourceFile(source, source.parent, Path(f'blocker-{index}.pdf'), source.stat().st_size)],
                    config, JobControl(), engine.translate, engine.languages.resolve, warning=warnings.append)
                try:
                    outputs = job.run()
                    if records and records[-1].get('validation') == 'PASS':
                        records[-1]['output'] = str(outputs[-1])
                except Exception as error:
                    records.append(dict(index=index, validation='FAILED', error=type(error).__name__, message=str(error)))
                print('PDF', index, records[-1]['validation'], round(perf_counter()-started, 2), flush=True)
    finally:
        PdfDocument.validate = validate_original
        engine.shutdown()
    (QA / 'pdf_blockers_production.json').write_text(json.dumps(dict(documents=records, warnings=warnings,
        seconds=perf_counter()-started, definition='Structural production checks; not a semantic certification.'), ensure_ascii=False, indent=2), 'utf8')


if __name__ == '__main__':
    run(tuple(map(int,sys.argv[1:])) if len(sys.argv)>1 else (10,16))
