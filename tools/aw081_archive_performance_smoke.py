"""Real CN7C inventory, normal production processing, hard stop after five PDFs.

Never publishes or processes the complete archive. Validated child outputs are
copied into QA evidence before the controlled cancellation cleans staging.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import shutil
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aw081_large_zip import ARCHIVE, production_hashes
QA = ROOT / 'qa/aw081/iterations/16_archive_performance'


def run():
    work = QA / 'smoke_bounded'
    work.mkdir(exist_ok=False)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.documents.archive_job import ArchiveJob
    from app.documents.control import JobControl
    from app.documents.job import DocumentConfig, DocumentJob
    from app.documents.pdf_document import PdfDocument
    from app.documents.run_metrics import LocalRun, file_hash
    from app.documents.scanner import scan_sources
    from app.engine.errors import TranslationCancelledError
    from app.engine.factory import create_translation_engine
    from app.glossary.bundled import bundled_paths
    from app.glossary.engine import GlossaryEngine
    from app.translation_memory.engine import TranslationMemoryEngine
    production_before = production_hashes()
    handler = logging.FileHandler(work / 'timing.log', encoding='utf8')
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s'))
    logger = logging.getLogger('treetranslate')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    control = JobControl()
    started_scan = perf_counter()
    scanned = scan_sources([ARCHIVE], control)
    scan_seconds = perf_counter() - started_scan
    assert len(scanned.files) == 17211
    wanted = [item.relative.as_posix() for item in scanned.files[:5]]
    (work / 'scan.json').write_text(json.dumps(dict(seconds=scan_seconds, documents=len(scanned.files),
        source_sha256=scanned.files[0].archive_hash, crc='PASS', first_five=wanted), ensure_ascii=False, indent=2), 'utf8')
    engine = create_translation_engine(memory=TranslationMemoryEngine(work / 'isolated-tm.db'),
        glossary=GlossaryEngine(work / 'isolated-user.db', builtin_paths=bundled_paths()))
    config = DocumentConfig(source='auto', target='ru', domain='auto', translate_directories=True,
        translate_filenames=True, output=work / 'output', metrics_directory=work / 'logs')
    times = dict(preflight=None, first_start=None, first_complete=None)
    events, starts, completed, captures, profiles = [], [], [], [], []
    original_event = LocalRun.archive_event
    original_bind = LocalRun.bind_archive_member
    original_validate = PdfDocument.validate
    original_start = LocalRun.start_document
    original_complete = LocalRun.complete_document
    original_archive_run = ArchiveJob._run
    cache = {}
    job_started = perf_counter()
    def event(observer, kind, **data):
        now = perf_counter() - job_started
        events.append(dict(event=kind, elapsed_since_job_start=now, **data))
        if kind == 'preflight_completed':
            times['preflight'] = now
            print('PREFLIGHT_COMPLETE', round(now, 3), flush=True)
        if kind == 'document_start':
            starts.append(dict(member=data['member'], seconds=now))
            if times['first_start'] is None:
                times['first_start'] = now
            print('DOCUMENT_START', len(starts), round(now, 3), flush=True)
        return original_event(observer, kind, **data)
    def start(observer, item, config, engine=None):
        # Capture the unchanged archive prior for the semantic baseline run.
        if not profiles and config.parent_context:
            profiles.append(asdict(config.parent_context))
        return original_start(observer, item, config, engine)
    def complete(observer, *args, **kwargs):
        if times['first_complete'] is None:
            times['first_complete'] = perf_counter() - job_started
        return original_complete(observer, *args, **kwargs)
    def validate(document, destination):
        result = original_validate(document, destination)
        index = len(captures)
        saved = work / f'validated-{index}.pdf'
        shutil.copy2(destination, saved)
        captures.append(dict(source_sha256=document.source_hash, output=str(saved), output_sha256=file_hash(saved),
            source_pages=len(document.pages), segments=[asdict(segment) for segment in document.segments]))
        (work / 'validated_children.json').write_text(json.dumps(captures, ensure_ascii=False, indent=2), 'utf8')
        return result
    def bind(observer, source, member, output_member, seconds, temporary_bytes):
        result = original_bind(observer, source, member, output_member, seconds, temporary_bytes)
        completed.append(member)
        print('DOCUMENT_PACKAGED', len(completed), round(perf_counter()-job_started, 3), flush=True)
        if len(completed) == 5:
            control.cancel()  # Next normal checkpoint stops before child six.
        return result
    def archive_run(archive):
        try:
            return original_archive_run(archive)
        finally:
            cache.update(hits=archive.path_translation.hits, misses=archive.path_translation.misses,
                         entries=len(archive.path_translation.cache), folder_components=len(archive.folder_names))
    LocalRun.archive_event, LocalRun.bind_archive_member = event, bind
    LocalRun.start_document, LocalRun.complete_document = start, complete
    PdfDocument.validate, ArchiveJob._run = validate, archive_run
    # Selection is the hard translation ceiling, independent of metrics hooks.
    job = DocumentJob(scanned.files[:5], config, control, engine.translate, engine.languages.resolve,
                      before_ocr=engine.runtime.release_models)
    job.metrics_metadata = dict(scope='REAL_CN7C_FIRST_FIVE_ONLY', hard_stop_after=5,
                                scan_seconds=scan_seconds, selected_files=5, inventory_documents=len(scanned.files))
    try:
        with engine.runtime.keep_warm():
            try:
                job.run()
                raise AssertionError('Smoke limit did not stop the archive')
            except TranslationCancelledError:
                pass
    finally:
        LocalRun.archive_event, LocalRun.bind_archive_member = original_event, original_bind
        LocalRun.start_document, LocalRun.complete_document = original_start, original_complete
        PdfDocument.validate, ArchiveJob._run = original_validate, original_archive_run
        engine.shutdown()
        logger.removeHandler(handler)
        handler.close()
    assert completed == wanted and [row['member'] for row in starts] == wanted
    assert times['first_start'] - times['preflight'] < 10
    stages = defaultdict(lambda: dict(calls=0, seconds=0.0))
    for line in (job.metrics_path / 'stages.jsonl').read_text('utf8').splitlines():
        row = json.loads(line)
        bucket = stages[row['stage']]
        bucket['calls'] += row['count']
        bucket['seconds'] += row['seconds']
    errors = [json.loads(line) for line in (job.metrics_path / 'errors.jsonl').read_text('utf8').splitlines()]
    errors = [row for row in errors if row['event'] == 'model_attempt_failed']
    receipt = dict(scope='REAL_CN7C_FIRST_FIVE_ONLY', status=job.run_status,
        stop='intentional cancellation after exactly five packaged documents; no final ZIP',
        scan_seconds=scan_seconds, times=times,
        time_to_first_document_start_after_preflight=times['first_start']-times['preflight'],
        time_to_first_document_complete_after_preflight=times['first_complete']-times['preflight'] if times['first_complete'] else None,
        filename_path_seconds=stages['path_translation']['seconds'], path_cache=cache,
        source=str(ARCHIVE), source_sha256=scanned.files[0].archive_hash,
        source_immutable=file_hash(ARCHIVE)==scanned.files[0].archive_hash,
        processed_members=completed, document_starts=starts, validated_children=len(captures),
        logs=str(job.metrics_path), stages=dict(stages), events=events,
        backend_failures=len(errors), backend_failure_types=dict(Counter(
            row['backend']+'/'+row['device']+'/'+row['exception_type'] for row in errors)),
        summary=json.loads((job.metrics_path/'run_summary.json').read_text('utf8')),
        parent_context=profiles[0] if profiles else None,
        production_unchanged=production_hashes()==production_before)
    assert receipt['source_immutable'] and receipt['production_unchanged']
    (work / 'execution.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', 'utf8')
    print('SMOKE_COMPLETE',receipt['time_to_first_document_start_after_preflight'],receipt['validated_children'], flush=True)


if __name__ == '__main__':
    run()
