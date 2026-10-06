import json
from types import SimpleNamespace
from pathlib import Path

from app.documents.measurements import collect, calibration
from app.documents.batch_eta import BatchEta
from app.documents.job import DocumentConfig
from app.models.translation_job import TranslationProgress, JobState


def test_archive_handles_russian_settings_and_survives_log_rotation(tmp_path):
    logs, archive = tmp_path / 'logs', tmp_path / 'archive'
    logs.mkdir()
    run = 'abcdef123456'
    lines = [f'run={run} operation=translate started version=AW 0.8.2 files=1 requested_source=Определить автоматически target=Русский device=auto',
             f'run={run} source=test.pdf bytes=30 sha256=aa pages=5 segments=10 chars=800 native_segments=10 ocr_segments=0',
             f'run={run} route source=en target=ru domain=general backend=argos device=cpu compute_type=int8',
             f'run={run} process=engine_translation event=end page=None block=None seconds=20 state=ok',
             f'run={run} process=document_write event=end page=None block=None seconds=5 state=ok',
             f'run={run} finished state=COMPLETED elapsed=26 warnings=0']
    path = logs / 'documents.log'
    path.write_text('\n'.join(lines), 'utf-8')
    collect(logs, archive)
    saved = json.loads((archive / (run + '.json')).read_text('utf-8'))
    assert saved['sources'][0]['chars'] == 800
    assert calibration(DocumentConfig(), archive)['segment_seconds'] == 2
    assert calibration(DocumentConfig(target='de'), archive) is None
    path.write_text('', 'utf-8')
    collect(logs, archive)
    assert (archive / (run + '.json')).exists()


def test_batch_eta_accounts_for_unprocessed_files_and_final_write():
    control = SimpleNamespace(active_seconds=0)
    rates = dict(segment_seconds=2, ocr_seconds=30, write_page_seconds=5)
    eta = BatchEta(rates, control)
    eta.files = [dict(extract=0, translate=20, write=5), dict(extract=0, translate=40, write=10)]
    progress = TranslationProgress(file_index=1, total=30, processed=10, stage='WRITING')
    eta.update(progress, [])
    assert progress.eta_scope == 'batch' and progress.eta_seconds == 55
    control.active_seconds = 3
    assert eta.remaining() == 52
    eta.published(1)
    assert eta.remaining() == 50


def test_archive_preserves_input_container_and_document_kind(tmp_path):
    logs, archive = tmp_path / 'logs', tmp_path / 'archive'
    logs.mkdir()
    scan, run = '111111111111', '222222222222'
    lines = [f'run={scan} operation=scan started version=AW files=0 requested_source=auto target=ru device=auto',
             f'run={scan} selection=' + json.dumps(dict(path='C:/docs', kind='folder')),
             f'run={scan} finished state=READY elapsed=1 warnings=0',
             f'run={run} operation=translate started version=AW files=1 requested_source=auto target=ru device=auto',
             f'run={run} scan_run={scan}',
             f'run={run} document_metadata=' + json.dumps(dict(format='pdf', kind='pdf_mixed', input_kind='folder', container='C:/docs', relative_path='nested/manual.pdf', archive_origin='unconfirmed')),
             f'run={run} finished state=COMPLETED elapsed=4 warnings=0']
    (logs / 'documents.log').write_text('\n'.join(lines), 'utf-8')
    collect(logs, archive)
    saved = json.loads((archive / (run + '.json')).read_text('utf-8'))
    assert saved['selections'][0]['kind'] == 'folder'
    assert saved['documents'][0]['kind'] == 'pdf_mixed'
    assert saved['documents'][0]['relative_path'] == 'nested/manual.pdf'
    assert saved['documents'][0]['archive_origin'] == 'unconfirmed'


def test_inventory_reads_pdf_text_without_running_ocr(tmp_path):
    from tools.pdf_fixtures import make_pdf
    from tools.ocr_fixtures import rasterize
    from app.documents.control import JobControl
    from app.documents.scanner import scan_sources
    source = make_pdf(tmp_path / 'text.pdf', pages=2)
    scan = tmp_path / 'scan.pdf'
    rasterize(source, scan)
    control = JobControl()
    rates = dict(segment_seconds=2, ocr_seconds=30, write_page_seconds=5, segments_per_page=10, runs=[])
    eta = BatchEta(rates, control)
    eta.prepare(scan_sources([source, scan], control).files, DocumentConfig(), 'abcdef123456')
    assert eta.available
    assert sorted(f['extract'] for f in eta.files) == [0, 60]
    assert eta.remaining() >= 100


def test_total_eta_remains_visible_during_long_ocr_and_save(qt_application, monkeypatch):
    from app.gui.widgets.progress_panel import ProgressPanel
    monkeypatch.setattr('app.gui.widgets.progress_panel.monotonic', lambda: 100)
    panel = ProgressPanel()
    panel.set_state(JobState.TRANSLATING)
    for stage in ('OCR', 'WRITING', 'VALIDATING', 'PUBLISHING'):
        panel.set_progress(TranslationProgress(stage=stage, eta_scope='batch', eta_seconds=90, sampled_at=80))
        assert panel.remaining.text() == '00:01:10'


def test_row_progress_survives_pause_and_publication(qt_application):
    from app.gui.widgets.file_tree import FileTree
    from app.models.file_item import FileItem
    from PySide6.QtCore import Qt
    tree = FileTree()
    source = Path('C:/input.pdf')
    tree.populate(FileItem('root', True, children=[FileItem(source.name, path=str(source))]))
    tree.set_busy(True)
    progress = TranslationProgress(source_path=str(source), file_percent=55)
    tree.set_progress(progress)
    tree.set_busy(True)
    item = tree.tree.topLevelItem(0).child(0)
    assert item.data(0, Qt.ItemDataRole.UserRole + 4) == 55
    tree.mark_completed(source, Path('C:/result.pdf'))
    progress.file_percent = 100
    tree.set_progress(progress)
    assert item.data(0, Qt.ItemDataRole.UserRole + 3) == 'C:\\result.pdf' or item.data(0, Qt.ItemDataRole.UserRole + 3) == 'C:/result.pdf'
