"""Filename/publication and honest ETA regressions for the PDF hotfix."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.documents.control import JobControl
from app.documents.errors import DocumentError
from app.documents.job import DocumentConfig, DocumentJob, safe_filename_base
from app.documents.scanner import scan_sources
from app.gui.widgets.progress_panel import ProgressPanel
from app.models.translation_job import JobState, TranslationProgress
from app.services.document_translation_service import DocumentTranslationService
from app.localization import localization, LOCALES
from tools.pdf_fixtures import make_pdf


@pytest.mark.parametrize('name', ['维修程序.pdf.pdf', '维修程序.pdf(1).pdf', '维修程序.PDF.PDF'])
@pytest.mark.parametrize('target,title', [('ru', 'Программа ремонта'), ('en', 'Repair procedure')])
def test_pdf_name_translates_meaningful_stem_and_keeps_source(tmp_path, name, target, title):
    source = make_pdf(tmp_path / name, 'Original text.', lines=1)
    before = sha256(source.read_bytes()).hexdigest()
    control = JobControl()
    requests = []
    def translate(request, cancel):
        requests.append(request.text)
        return SimpleNamespace(translated_text=title + '.pdf.pdf' if request.text == '维修程序' else request.text)
    result, = DocumentJob(scan_sources([source], control).files,
        DocumentConfig(source='zh', target=target, translate_filenames=True), control,
        translate, lambda text, source, target: (source, target)).run()
    assert result.name == title + '_' + target + source.suffix
    assert '维修程序' in requests
    assert all('.pdf' not in text.casefold() for text in requests)
    assert sha256(source.read_bytes()).hexdigest() == before
    assert source.name == name


@pytest.mark.parametrize('value', ['pdf', '.pdf', '.pdf.pdf', 'CON.pdf', 'NUL.extra.pdf'])
def test_extension_or_device_name_cannot_replace_meaningful_filename(value):
    assert safe_filename_base(value, '维修程序', '.pdf') == '维修程序'


def test_publication_is_last_stage_before_100(tmp_path):
    source = make_pdf(tmp_path / 'manual.pdf', 'Original text.', lines=1)
    control = JobControl()
    progress = []
    published = []
    def record(value):
        if value.percent == 100:
            assert published and all(p.exists() for p in published)
        elif value.stage in {'WRITING', 'VALIDATING', 'PUBLISHING'}:
            assert value.percent < 100 and value.eta_seconds is None
        progress.append(value)
    DocumentJob(scan_sources([source], control).files, DocumentConfig(source='en'), control,
        lambda request, cancel: SimpleNamespace(translated_text=request.text),
        lambda text, source, target: (source, target), progress=record, outputs=published.extend).run()
    stages = [p.stage for p in progress]
    assert stages.index('TRANSLATING') < stages.index('WRITING') < stages.index('VALIDATING') < stages.index('PUBLISHING') < stages.index('COMPLETED')
    assert [p.percent for p in progress] == sorted(p.percent for p in progress)


def test_validation_failure_never_reaches_publication_or_100(tmp_path, monkeypatch):
    from app.documents.pdf_document import PdfDocument
    source = make_pdf(tmp_path / 'manual.pdf', lines=1)
    def fail(*args):
        raise DocumentError('validation failed')
    monkeypatch.setattr(PdfDocument, 'validate', fail)
    control = JobControl()
    progress = []
    outputs = []
    with pytest.raises(DocumentError):
        DocumentJob(scan_sources([source], control).files, DocumentConfig(source='en'), control,
            lambda request, cancel: SimpleNamespace(translated_text=request.text),
            lambda text, source, target: (source, target), progress=progress.append, outputs=outputs.extend).run()
    assert not outputs and all(p.percent < 100 for p in progress)
    assert 'PUBLISHING' not in {p.stage for p in progress}


def test_eta_excludes_extraction_and_first_cold_translation(tmp_path, monkeypatch):
    import app.documents.job as module
    from docx import Document
    class ClockControl(JobControl):
        now = 0
        @property
        def active_seconds(self):
            return self.now
    source = tmp_path / 'manual.docx'
    doc = Document()
    for i in range(8):
        doc.add_paragraph(f'Segment number {i}')
    doc.save(source)
    control = ClockControl()
    open_document = module.open_document
    def delayed_open(*args, **kwargs):
        control.now += 600
        return open_document(*args, **kwargs)
    monkeypatch.setattr(module, 'open_document', delayed_open)
    calls = []
    def translate(request, cancel):
        control.now += 900 if not calls else 2
        calls.append(request)
        return SimpleNamespace(translated_text=request.text)
    progress = []
    DocumentJob(scan_sources([source], control).files, DocumentConfig(source='en'), control,
        translate, lambda text, source, target: (source, target), progress=progress.append).run()
    samples = [p for p in progress if p.stage == 'TRANSLATING']
    assert all(p.eta_seconds is None for p in samples if p.processed < 4)
    assert next(p for p in samples if p.processed == 4).eta_seconds == 8


def test_eta_uncertainty_staleness_and_stage_recovery(qt_application, monkeypatch):
    monkeypatch.setattr('app.gui.widgets.progress_panel.monotonic', lambda: 100)
    panel = ProgressPanel()
    panel.set_state(JobState.TRANSLATING)
    panel.set_progress(TranslationProgress(stage='OCR', total=0, sampled_at=100))
    assert panel.remaining.text() == 'Оценка времени…'
    panel.set_progress(TranslationProgress(percent=10, eta_seconds=70, sampled_at=80))
    assert panel.remaining.text() == 'Оценка уточняется…'
    panel.set_progress(TranslationProgress(percent=20, eta_seconds=30, sampled_at=100))
    assert panel.remaining.text() == '00:00:30'
    for stage in ('WRITING', 'VALIDATING', 'PUBLISHING'):
        panel.set_progress(TranslationProgress(percent=99, processed=86, total=86, eta_seconds=0, stage=stage, sampled_at=100))
        assert panel.remaining.text() == 'Оценка уточняется…'
    panel.set_progress(TranslationProgress(percent=100, stage='COMPLETED', sampled_at=100))
    assert panel.remaining.text() == '00:00:00'


def test_service_heartbeat_preserves_worker_sample_time(qt_application):
    from PySide6.QtCore import QObject
    owner = QObject()
    owner._closed = False
    service = DocumentTranslationService(owner)
    service.progress = TranslationProgress(stage='OCR', total=0, sampled_at=1)
    service.control.started -= 25
    emitted = []
    service.progress_changed.connect(emitted.append)
    service._tick()
    qt_application.processEvents()
    assert emitted[-1].elapsed_seconds >= 25
    assert emitted[-1].sampled_at == 1


def test_new_progress_strings_in_all_static_locales(qt_application):
    panel = ProgressPanel()
    panel.set_state(JobState.TRANSLATING)
    for locale in LOCALES:
        catalog = json.loads((Path('assets/locales') / (locale + '.json')).read_text('utf-8'))
        for source in ('Оценка времени…', 'Оценка уточняется…', 'Сохранение результата…'):
            assert catalog.get(source)
        localization.use(locale)
        panel.set_progress(TranslationProgress(stage='OCR', total=0))
        assert panel.remaining.text() == catalog['Оценка времени…']
    localization.use('ru-RU')


def test_timing_records_success_and_failure_without_document_text(monkeypatch, caplog):
    from app.documents.pdf_diagnostics import timed_stage
    clock = iter([10, 10.25, 20, 20.5])
    monkeypatch.setattr('app.config.logging_config.perf_counter', lambda: next(clock))
    with caplog.at_level('INFO', logger='treetranslate.documents'):
        with timed_stage('test_success', page=2, block=12):
            pass
        with pytest.raises(ValueError), timed_stage('test_failure', page=2):
            raise ValueError('PRIVATE_DOCUMENT_TEXT')
    assert 'seconds=0.2500 state=ok' in caplog.text
    assert 'seconds=0.5000 state=ValueError' in caplog.text
    assert 'PRIVATE_DOCUMENT_TEXT' not in caplog.text


def test_document_file_log_is_utf8_rotating_and_not_duplicated(tmp_path, monkeypatch):
    import logging
    import app.config.logging_config as module
    monkeypatch.setattr(module, 'LOGS_DIR', tmp_path)
    names = ('treetranslate', 'treetranslate.documents')
    previous = {name: list(logging.getLogger(name).handlers) for name in names}
    levels = {name: logging.getLogger(name).level for name in names}
    propagate = logging.getLogger('treetranslate').propagate
    for name in names:
        logging.getLogger(name).handlers = []
    try:
        module.configure_logging()
        module.configure_logging()
        logger = logging.getLogger('treetranslate.documents')
        assert len(logger.handlers) == 1
        logger.info('PDF проверка UTF-8')
        assert 'PDF проверка UTF-8' in (tmp_path / 'documents.log').read_text('utf-8')
        assert logger.handlers[0].maxBytes == 1_000_000
    finally:
        for name in names:
            for handler in logging.getLogger(name).handlers:
                handler.close()
            logging.getLogger(name).handlers = previous[name]
            logging.getLogger(name).setLevel(levels[name])
        logging.getLogger('treetranslate').propagate = propagate


def test_failure_log_has_last_worker_stage_and_safe_stack(tmp_path, qt_application, caplog):
    from time import monotonic, sleep
    from app.services.hybrid_translation_service import HybridTranslationService
    owner = HybridTranslationService(engine=SimpleNamespace(shutdown=lambda: None))
    service = owner.files
    def operation():
        service._worker_progress(TranslationProgress(stage='VALIDATING', processed=86, total=86))
        raise ValueError('PRIVATE_DOCUMENT_TEXT')
    try:
        with caplog.at_level('INFO', logger='treetranslate.documents'):
            service._submit(operation)
            deadline = monotonic() + 5
            while service.busy and monotonic() < deadline:
                qt_application.processEvents()
                sleep(.01)
        assert service.state == JobState.ERROR
        assert 'type=ValueError stage=VALIDATING' in caplog.text
        assert 'segments=86/86' in caplog.text
        assert 'error_frames=' in caplog.text
        assert 'PRIVATE_DOCUMENT_TEXT' not in caplog.text
    finally:
        owner.shutdown()
