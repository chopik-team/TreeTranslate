import os
from types import SimpleNamespace
from hashlib import sha256
from unittest.mock import patch
from pathlib import Path
import pytest
from time import monotonic, sleep

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from docx import Document
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from app.documents.job import DocumentConfig
from app.gui.main_window import MainWindow
from app.models.translation_job import JobState
from app.services.hybrid_translation_service import HybridTranslationService
from app.services.settings_service import SettingsService
from test_hybrid_service import SlowEngine


def wait_for(predicate, timeout=3000):
    deadline = monotonic() + timeout / 1000
    while not predicate() and monotonic() < deadline:
        QApplication.processEvents()
        # qWait can retain the GIL on Windows; let the Python document worker run.
        sleep(.005)
    QApplication.processEvents()
    assert predicate()


def make_source(tmp_path):
    path = tmp_path / 'test.docx'
    doc = Document()
    doc.add_paragraph('Private paragraph one')
    doc.add_paragraph('Private paragraph two')
    doc.save(path)
    return path


def make_engine():
    engine = SlowEngine()
    engine.languages = SimpleNamespace(resolve=lambda text, source, target: ('en', 'ru'))
    return engine


@pytest.mark.parametrize('failed_document',[False,True])
def test_gui_zip_run_saves_local_diagnostics(tmp_path,failed_document):
    import json
    from zipfile import ZipFile
    app = QApplication.instance() or QApplication([])
    source = make_source(tmp_path)
    archive = tmp_path / 'manual.zip'
    with ZipFile(archive, 'w') as bundle:
        bundle.write(source, 'chapter/one.docx')
        bundle.write(source, 'chapter/two.docx')
        if failed_document:
            bundle.writestr('chapter/broken.pdf',b'not a PDF')
    source_hash = sha256(archive.read_bytes()).hexdigest()
    engine = make_engine()
    engine.release.set()
    service = HybridTranslationService(engine=engine)
    window = MainWindow(translation_service=service)
    try:
        window.translation.accept_paths([archive])
        wait_for(lambda: service.state == JobState.READY)
        with patch('app.controllers.translation_ui_controller.LOGS_DIR', tmp_path / 'logs'):
            window.translation._start_translation()
        wait_for(lambda: service.state in {JobState.COMPLETED, JobState.ERROR}, timeout=10000)
        assert service.state == JobState.COMPLETED
        directories = list((tmp_path / 'logs/document_runs').iterdir())
        assert len(directories) == 1
        manifest = json.loads((directories[0] / 'run_manifest.json').read_text('utf8'))
        summary = json.loads((directories[0] / 'run_summary.json').read_text('utf8'))
        assert manifest['metadata']['entrypoint'] == 'TreeTranslate GUI'
        assert manifest['metadata']['scan_run_id'] == service.files._scan_run_id
        assert manifest['metadata']['scan_seconds'] >= 0
        assert summary['status'] == ('COMPLETED_WITH_FAILURES' if failed_document else 'COMPLETED')
        assert summary['logging_status'] == 'COMPLETE'
        assert summary['counters']['documents'] == (3 if failed_document else 2)
        if failed_document:
            assert summary['source_preserved_documents']==1
            assert window.file_page.progress.status.text()=='Завершено с ошибками; оригиналы сохранены'
        assert sha256(archive.read_bytes()).hexdigest() == source_hash
        output, = window.file_page.progress.output_paths
        with ZipFile(output) as bundle:
            assert bundle.testzip() is None
            if failed_document:assert bundle.read('chapter/broken.pdf')==b'not a PDF'
        documents = [json.loads(line) for line in (directories[0] / 'documents.jsonl').read_text('utf8').splitlines()]
        assert len(documents) == (3 if failed_document else 2)
        assert all(d['source_immutable'] and d['output_sha256'] for d in documents)
        assert (directories[0] / 'quality_sample_manifest.json').exists()
        assert all('Private paragraph' not in p.read_text('utf8') for p in directories[0].glob('*.jsonl'))
    finally:
        window.close()


def test_file_cancel_retains_session_until_worker_finishes(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = make_source(tmp_path)
    digest = sha256(source.read_bytes()).hexdigest()
    engine = make_engine()
    service = HybridTranslationService(engine=engine)
    window = MainWindow(translation_service=service)
    errors = []
    service.files.failed.connect(errors.append)
    try:
        window.translation.accept_paths([source])
        wait_for(lambda: service.state == JobState.READY)
        window.translation._start_translation()
        assert engine.entered.wait(2)
        service.cancel()
        assert service.state == JobState.CANCELLING
        assert window.sessions.is_active('file')
        window.translation.translate_text('must not run')
        assert not window.sessions.is_active('text')
        assert len(engine.calls) == 1
        engine.release.set()
        wait_for(lambda: service.state == JobState.CANCELLED)
        assert not window.sessions.is_active('file')
        assert not window.file_page.progress.output_paths
        assert sha256(source.read_bytes()).hexdigest() == digest
    finally:
        engine.release.set()
        window.close()


def test_file_service_completed_output_and_open_actions(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = make_source(tmp_path)
    engine = make_engine()
    engine.release.set()
    service = HybridTranslationService(engine=engine)
    window = MainWindow(translation_service=service)
    errors = []
    service.files.failed.connect(errors.append)
    try:
        window.translation.accept_paths([source])
        wait_for(lambda: service.state == JobState.READY)
        service.files.config = DocumentConfig(source='en', output=tmp_path / 'result')
        service.start()
        wait_for(lambda: service.state in {JobState.COMPLETED, JobState.ERROR})
        assert service.state == JobState.COMPLETED, errors
        output, = window.file_page.progress.output_paths
        assert output.is_file()
        assert window.file_page.progress.bar.value() == 100
        with patch('app.controllers.translation_ui_controller.QDesktopServices.openUrl', return_value=True) as open_url:
            window.file_page.progress.open_file.click()
            assert Path(open_url.call_args.args[0].toLocalFile()) == output.resolve()
        with patch('app.controllers.translation_ui_controller.QProcess.startDetached', return_value=True) as explorer:
            window.file_page.progress.show_output.click()
            assert explorer.call_args.args[0] == 'explorer.exe'
            assert '/select,' in explorer.call_args.args[1]
    finally:
        window.close()


def test_corrupted_pdf_has_no_fake_translation(tmp_path):
    app = QApplication.instance() or QApplication([])
    pdf = tmp_path / 'manual.pdf'
    pdf.write_bytes(b'%PDF')
    engine = make_engine()
    engine.release.set()
    window = MainWindow(translation_service=HybridTranslationService(engine=engine))
    try:
        window.translation.accept_paths([pdf])
        wait_for(lambda: window.translation_service.state == JobState.READY)
        assert window.file_page.start_button.isEnabled()
        window.translation._start_translation()
        wait_for(lambda: window.translation_service.state == JobState.ERROR)
        assert 'повреждён' in window.file_page.file_status.text()
        assert not engine.calls
        assert window.file_page.progress.bar.value() == 0
    finally:
        window.close()


def test_completed_job_opens_output_folder_only_when_enabled(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(translation_service=HybridTranslationService(engine=make_engine()))
    output = tmp_path / 'result' / 'translated.docx'
    output.parent.mkdir()
    output.write_bytes(b'result')
    try:
        window.file_page.progress.set_output_paths([output])
        with patch.object(window.translation.settings, 'value', return_value=False), \
             patch('app.controllers.translation_ui_controller.QDesktopServices.openUrl', return_value=True) as open_url:
            window.translation._state_changed(JobState.COMPLETED)
            open_url.assert_not_called()

        with patch.object(window.translation.settings, 'value', return_value=True), \
             patch('app.controllers.translation_ui_controller.QDesktopServices.openUrl', return_value=True) as open_url:
            window.translation._state_changed(JobState.COMPLETED)
        open_url.assert_called_once()
        assert Path(open_url.call_args.args[0].toLocalFile()) == output.parent.resolve()
    finally:
        window.close()


def test_unfinished_job_is_restored_as_ready_without_auto_start(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = make_source(tmp_path)
    settings = SettingsService(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    settings.save_value('general/restore_job', True)
    settings.save_unfinished_job([source])
    engine = make_engine()
    engine.release.set()
    service = HybridTranslationService(engine=engine)
    window = MainWindow(translation_service=service)
    window.translation.settings = settings
    window.translation.preferences.settings = settings
    try:
        window.show()
        wait_for(lambda: service.state == JobState.READY)
        assert window.file_page.start_button.isEnabled()
        assert window.file_page.file_tree.selected_paths() == [source.resolve()]
        assert 'Задача восстановлена' in window.file_page.file_status.text()
        assert not engine.calls
    finally:
        window.close()


def test_finished_or_cancelled_job_is_not_restored(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = make_source(tmp_path)
    settings = SettingsService(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    settings.save_value('general/restore_job', True)
    settings.save_unfinished_job([source])
    window = MainWindow(translation_service=HybridTranslationService(engine=make_engine()))
    window.translation.settings = settings
    try:
        window.translation._state_changed(JobState.CANCELLED)
        assert settings.unfinished_job_paths() == ()
    finally:
        window.close()


def test_completed_job_stays_cleared_until_restarted(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = make_source(tmp_path)
    settings = SettingsService(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    settings.save_value('general/restore_job', True)
    engine = make_engine()
    engine.release.set()
    service = HybridTranslationService(engine=engine)
    window = MainWindow(translation_service=service)
    window.translation.settings = settings
    try:
        window.translation.accept_paths([source])
        wait_for(lambda: service.state == JobState.READY)
        window.translation._start_translation()
        wait_for(lambda: service.state == JobState.COMPLETED)
        window.translation.update_restore_preference()
        assert settings.unfinished_job_paths() == ()
        window.translation._start_translation()
        assert settings.unfinished_job_paths() == (source.resolve(),)
        wait_for(lambda: service.state == JobState.COMPLETED)
    finally:
        window.close()


def test_shutdown_preserves_active_job_and_ignores_rejected_paths(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = make_source(tmp_path)
    settings = SettingsService(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    settings.save_value('general/restore_job', True)
    engine = make_engine()
    service = HybridTranslationService(engine=engine)
    window = MainWindow(translation_service=service)
    window.translation.settings = settings
    try:
        window.translation.accept_paths([source])
        wait_for(lambda: service.state == JobState.READY)
        window.translation._start_translation()
        assert engine.entered.wait(2)
        window.translation.accept_paths([tmp_path / 'rejected.docx'])
        assert settings.unfinished_job_paths() == (source.resolve(),)
    finally:
        engine.release.set()
        window.close()
    QApplication.processEvents()
    assert settings.unfinished_job_paths() == (source.resolve(),)
