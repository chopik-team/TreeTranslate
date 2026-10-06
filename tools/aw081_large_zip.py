"""Read-only archive preflight by default; --run explicitly starts translation.

Uses the existing production scanner, ZIP guards, router and PDF writer.
The future run writes only local streaming diagnostics and isolated TM data.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARCHIVE = Path('C:/Users/PC/Downloads/2022_USER_REPAIR_MAINTENANCE_DISASSEMBLE_(CN7C)_CHINA_koreacustom.ru.zip')
OUTPUT = ROOT / 'output/aw081/large_corpus'
LOGS = ROOT / 'qa/aw081/large_corpus'


def preflight(archive, output, logs):
    from app.documents.control import JobControl
    from app.documents.zip_archive import inventory, disk_budget, digest
    from app.documents.run_metrics import resource_sample
    from app.engine.runtime.device_manager import DeviceManager
    control = JobControl()
    members = inventory(archive, control, verify_crc=False)
    counts = Counter(Path(m.name).suffix.lower() for m in members if not m.directory)
    budget = disk_budget(members, archive.stat().st_size)
    # Estimate for logs is deliberately separate from production ZIP budget.
    # Segment counts are unknown before extraction; allowance is not a bound.
    supported = counts['.pdf'] + counts['.docx']
    log_allowance = max(256 * 1024**2, supported * 256 * 1024)
    temporary = Path(tempfile.gettempdir())
    needs = {}
    for path, size in ((output, budget['output'] + budget['reserve']),
                       (temporary, budget['working_member'] + budget['rendering']),
                       (logs, log_allowance)):
        parent = path
        while not parent.exists():
            parent = parent.parent
        volume = parent.resolve().anchor
        needs.setdefault(volume, dict(required_bytes=0, free_bytes=shutil.disk_usage(parent).free))['required_bytes'] += size
    disk_ready = all(v['free_bytes'] >= v['required_bytes'] for v in needs.values())
    return dict(revision='AW0.81',operation='READ_ONLY_PREFLIGHT',translation_started=False,
        source_archive=str(archive),source_sha256=digest(archive,control),archive_bytes=archive.stat().st_size,
        members=len(members),file_members=sum(not m.directory for m in members),directories=sum(m.directory for m in members),
        pdf_count=counts['.pdf'],docx_count=counts['.docx'],types=dict(counts),uncompressed_bytes=sum(m.size for m in members),
        source_pages=None,page_count_status='Unknown; full PDF extraction deliberately not started.',
        scanner_security='PASS: bounded central-directory validation; production scan additionally verifies every member CRC.',
        crc_status='NOT_RUN_PREFLIGHT',disk_budget=budget,estimated_log_allowance_bytes=log_allowance,
        disk_volumes=needs,disk_ready=disk_ready,scanner_ready=True,device='auto',
        cuda_available=DeviceManager().gpu_available(),gpu_selection='Existing runtime default device; Auto can fall back to CPU.',
        resources=resource_sample(),output_directory=str(output),log_directory=str(logs),temporary_directory=str(temporary),
        technical_preflight='READY' if disk_ready else 'NOT_READY',
        limitations=['Disk/log allowances are estimates, not hard upper bounds.',
                      'Preflight readiness does not constitute semantic acceptance or permission to translate.'])


def production_hashes():
    from app.glossary.bundled import bundled_paths
    from app.documents.run_metrics import file_hash
    files = [*sorted((ROOT/'app').rglob('*.py')), *sorted((ROOT/'assets/config').glob('*.json')), *bundled_paths()]
    return {str(p.relative_to(ROOT)):file_hash(p) for p in files}


def translate(archive, output, logs):
    from app.documents.run_metrics import LocalRun, file_hash
    from app.documents.scanner import scan_sources
    from app.documents.control import JobControl
    from app.documents.job import DocumentJob, DocumentConfig
    from app.engine.factory import create_translation_engine
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.config.logging_config import configure_logging, document_run
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    configure_logging()
    readiness = preflight(archive,output,logs)
    if not readiness['disk_ready']:
        raise RuntimeError('Archive preflight: insufficient free disk space.')
    run_id = uuid4().hex
    seal = production_hashes()
    journal = LocalRun(logs,run_id=run_id,metadata=dict(preflight=readiness,production_hashes=seal,
                       knowledge_changes_allowed=False,mode='auto',telemetry=False))
    runtime = journal.directory/'runtime'
    runtime.mkdir()
    engine = None
    with journal.activate(), document_run(run_id):
        try:
            control = JobControl()
            files = scan_sources([archive],control).files
            engine = create_translation_engine(memory=TranslationMemoryEngine(runtime/'isolated-tm.db'),
                glossary=GlossaryEngine(runtime/'isolated-user.db',builtin_paths=bundled_paths()))
            config = DocumentConfig(source='zh',target='ru',domain='auto',output=output,
                translate_directories=True,translate_filenames=True,metrics_directory=logs)
            with engine.runtime.keep_warm():
                outputs = DocumentJob(files,config,control,engine.translate,engine.languages.resolve,run_id=run_id).run()
            if production_hashes() != seal:
                raise RuntimeError('Production code/Knowledge changed during the run.')
            if file_hash(archive) != readiness['source_sha256']:
                raise RuntimeError('Source archive changed during the run.')
        except BaseException as error:
            journal.close('FAILED',error)
            raise
        else:
            journal.close()
            print(json.dumps(dict(run_id=run_id,outputs=[str(p) for p in outputs],logs=str(journal.directory),
                                  logging_failed=journal.logging_failed),ensure_ascii=False))
        finally:
            if engine is not None:
                engine.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,default=ARCHIVE)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--logs',type=Path,default=LOGS)
    parser.add_argument('--report',type=Path,default=ROOT/'qa/aw081/iterations/14_phase_a_closure/large_zip_preflight.json')
    parser.add_argument('--run',action='store_true',help='Start the full archive translation; requires separate user authorization.')
    args = parser.parse_args()
    if args.run:
        translate(args.archive,args.output,args.logs)
    else:
        result = preflight(args.archive,args.output,args.logs)
        if args.report.exists():
            raise FileExistsError('Preflight report already exists; specify a fresh --report to preserve QA history.')
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
