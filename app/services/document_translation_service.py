from contextlib import nullcontext
from dataclasses import replace
import logging
import json
from pathlib import Path
import traceback
from uuid import uuid4
from time import perf_counter, monotonic

from PySide6.QtCore import Signal, Qt, QTimer

from app.documents.control import JobControl
from app.documents.errors import DocumentError
from app.documents.job import DocumentJob, DocumentConfig
from app.documents.scanner import scan_sources, ScanResult
from app.engine.errors import TranslationCancelledError, TranslationError
from app.models.translation_job import JobState, TranslationProgress
from app.services.translation_service import TranslationService
from app.config.constants import APP_VERSION

logger = logging.getLogger('treetranslate.documents')


class DocumentTranslationService(TranslationService):
    finished = Signal(object)
    failed = Signal(str)
    warning = Signal(str)
    notice = Signal(str)
    file_completed = Signal(object, object)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.state = JobState.IDLE
        self.progress = TranslationProgress(total=0)
        self.scan_result = ScanResult(())
        self.selected = ()
        self.config = DocumentConfig()
        self.control = JobControl()
        self.policy = None
        self.warnings = []
        self.completed_sources = {}
        self.completed_outputs = ()
        self.warning.connect(self._record_warning, Qt.ConnectionType.QueuedConnection)
        self.finished.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self.progress_changed.connect(self._progress, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self._tick)

    def _state(self, state):
        self.state = state
        self.state_changed.emit(state)

    def _record_warning(self, message):
        if self.owner._closed:
            return
        if message not in self.warnings:
            self.warnings.append(message)
            self.notice.emit(f'Предупреждений: {len(self.warnings)}. {message}')

    def _progress(self, progress):
        if self.owner._closed:
            return
        self.progress = progress

    def _worker_progress(self, progress):
        # Read this worker snapshot on failure, even if GUI signals are pending.
        progress = replace(progress, sampled_at=monotonic())
        self._last_worker_progress = progress
        self._eta_anchor = (progress.eta_seconds,self.control.active_seconds) if progress.eta_seconds is not None else None
        self.progress_changed.emit(progress)

    def _tick(self):
        if self.owner._closed:
            self.timer.stop()
            return
        progress = replace(self.progress, elapsed_seconds=int(self.control.elapsed))
        estimator = getattr(self, '_eta_estimator', None)
        if estimator and estimator.available and estimator.files and self.state in {JobState.TRANSLATING,JobState.PAUSED}:
            progress = replace(progress, eta_scope='batch', eta_seconds=max(0, round(estimator.remaining())), sampled_at=monotonic())
        elif progress.eta_seconds is not None and self.state in {JobState.TRANSLATING,JobState.PAUSED}:
            # Without a calibrated workload, retain the last worker deadline;
            # heartbeat snapshots must not restart it or spend paused seconds.
            anchor = getattr(self, '_eta_anchor', None)
            if anchor is not None:
                progress = replace(progress, eta_seconds=max(0, round(anchor[0]-(self.control.active_seconds-anchor[1]))), sampled_at=monotonic())
        self.progress_changed.emit(progress)

    def configure(self, policy):
        self.policy = policy

    @property
    def busy(self):
        return self.state in {JobState.SCANNING, JobState.TRANSLATING, JobState.PAUSED, JobState.CANCELLING}

    def _submit(self, operation, scanning=False):
        if self.busy or self.owner.text_busy or self.owner._closed or self.owner._closing:
            return
        self.control = JobControl()
        self.progress = TranslationProgress(total=0)
        self.warnings = []
        self._run_id = uuid4().hex[:12]
        self._last_worker_progress = self.progress
        self._eta_estimator = None
        self._eta_anchor = None
        logger.info('run=%s operation=%s started version=%s files=%d requested_source=%s target=%s device=%s',
                    self._run_id, 'scan' if scanning else 'translate', APP_VERSION, len(self.selected),
                    self.config.source, self.config.target, self.config.device.value)
        self._state(JobState.SCANNING if scanning else JobState.TRANSLATING)
        self.progress_changed.emit(self.progress)
        self.timer.start()
        def work():
            try:
                from app.config.logging_config import document_run
                with document_run(self._run_id):
                    return scanning, operation(), None, False
            except TranslationCancelledError:
                return scanning, None, None, True
            except Exception as error:
                p = self._last_worker_progress
                logger.warning('run=%s failed type=%s stage=%s file=%d/%d page=%d/%d segments=%d/%d elapsed=%.2f',
                               self._run_id, type(error).__name__, p.stage, p.file_index, p.file_total,
                               p.page_index, p.page_total, p.processed, p.total, self.control.elapsed)
                if getattr(error, 'diagnostic', None):
                    logger.warning('run=%s PDF diagnostic %s', self._run_id, error.diagnostic)
                # Stack locations only: exception text/locals may contain document content.
                frames = traceback.extract_tb(error.__traceback__)[-8:]
                logger.warning('run=%s error_frames=%s', self._run_id,
                               [(frame.filename, frame.lineno, frame.name) for frame in frames])
                message = str(error) if isinstance(error, (DocumentError, TranslationError)) else 'Не удалось обработать документ или сохранить результат.'
                return scanning, None, message, False
        self.owner.executor().submit(work).add_done_callback(lambda f: self.finished.emit(f.result()))

    def scan(self, paths):
        if self.busy:
            return
        self.completed_sources = {}
        self.completed_outputs = ()
        self.scan_result = ScanResult(())
        self.selected = ()
        paths = tuple(Path(p).resolve() for p in paths)
        def scan():
            scan_started = perf_counter()
            for path in paths:
                kind = 'folder' if path.is_dir() else 'archive' if path.suffix.lower() in {'.zip', '.rar', '.7z'} else 'file'
                logger.info('run=%s selection=%s', self._run_id, json.dumps(dict(path=str(path), kind=kind,
                    format=path.suffix.lower().lstrip('.'), archive_supported=path.suffix.lower() == '.zip' if kind == 'archive' else None), ensure_ascii=False))
            def archive_progress(index, total):
                # Use the existing panel; scanning has no defensible batch ETA.
                if index <= 1 or index % 100 == 0 or index == total:
                    self._worker_progress(TranslationProgress(total=total, processed=index,
                        stage='ARCHIVE_SCANNING', percent=int(index * 100 / total) if total else 0,
                        elapsed_seconds=int(self.control.elapsed), eta_scope='archive'))
            result = scan_sources(paths, self.control, archive_progress)
            self._scan_seconds = perf_counter() - scan_started
            logger.info('run=%s scan_result=%s', self._run_id, json.dumps(dict(found=len(result.files),
                skipped=[str(p) for p in result.skipped], formats={ext: sum(f.path.suffix.lower() == '.'+ext for f in result.files)
                for ext in ('docx', 'pdf')}), ensure_ascii=False))
            from app.documents.measurements import calibration
            from app.documents.batch_eta import BatchEta
            rates = calibration(self.config)
            self._eta_preview = BatchEta(rates,self.control) if rates and result.files else None
            if self._eta_preview:
                self._eta_preview.prepare(result.files,self.config,self._run_id)
            return result
        self._submit(scan, True)

    def _completed_file(self, source, output):
        self.completed_sources[source] = output
        self.completed_outputs = tuple(dict.fromkeys((*self.completed_outputs, output)))
        self.file_outputs_ready.emit(self.completed_outputs)
        self.file_completed.emit(source, output)

    def start(self):
        def run():
            logger.info('run=%s scan_run=%s', self._run_id, getattr(self, '_scan_run_id', 'unknown'))
            from app.documents.measurements import calibration
            from app.documents.batch_eta import BatchEta
            rates = calibration(self.config)
            self._eta_estimator = BatchEta(rates, self.control) if rates else None
            if self._eta_estimator:
                preview = getattr(self,'_eta_preview',None)
                if preview:self._eta_estimator.catalog=dict(preview.catalog)
                self._eta_estimator.prepare(self.selected,self.config,self._run_id)
                self._eta_estimator.begin()
                self._worker_progress(TranslationProgress(total=0,file_total=len(self.selected),
                    current_file=self.selected[0].path.name if self.selected else '—',
                    stage='ARCHIVE_PREPARING' if any(f.archive for f in self.selected) else 'EXTRACTING',
                    eta_scope='batch',eta_seconds=round(self._eta_estimator.remaining())))
            engine = self.owner.engine
            runtime = getattr(engine, 'runtime', None)
            if runtime and self.policy:
                runtime.idle_timeout_seconds = engine.policy.idle_timeout_seconds if self.policy.unload_model else 0
            with runtime.keep_warm() if runtime else nullcontext():
                job = DocumentJob(self.selected, self.config, self.control, engine.translate, engine.languages.resolve,
                                   self._worker_progress, lambda outputs: None, self.warning.emit,
                                   getattr(runtime, 'release_models', lambda: None), run_id=self._run_id,
                                   file_completed=self._completed_file, eta_estimator=self._eta_estimator)
                job.metrics_metadata = dict(entrypoint='TreeTranslate GUI',
                    scan_run_id=getattr(self, '_scan_run_id', None),
                    scan_seconds=getattr(self, '_scan_seconds', None),
                    selected_files=len(self.selected))
                return job.run()
        self._submit(run)

    def _finish(self, result):
        if self.owner._closed:
            self.timer.stop()
            return
        scanning, value, error, cancelled = result
        self.timer.stop()
        if self.control.cancelled.is_set():
            cancelled = True
        if cancelled:
            self._state(JobState.CANCELLED)
        elif error:
            self._state(JobState.ERROR)
            self.failed.emit(error)
        elif scanning:
            self._scan_run_id = self._run_id
            self.scan_result = value
            self.selected = value.files
            self._state(JobState.READY)
            self.scan_finished.emit()
            preview = getattr(self,'_eta_preview',None)
            if preview and preview.available:
                self._worker_progress(TranslationProgress(total=0,file_total=len(self.selected),stage='READY',
                    current_file=self.selected[0].path.name if len(self.selected)==1 else 'Выбранные документы',
                    eta_scope='batch',eta_seconds=round(preview.remaining())))
        else:
            self._state(JobState.COMPLETED)
        logger.info('run=%s finished state=%s elapsed=%.2f warnings=%d active_seconds=%.2f', self._run_id,
                    self.state.name, self.control.elapsed, len(self.warnings), self.control.active_seconds)
        try:
            from app.documents.measurements import collect
            collect()
        except OSError:
            logger.warning('run=%s measurements archive unavailable', self._run_id)

    def pause_or_resume(self):
        if self.state == JobState.TRANSLATING:
            self.control.pause()
            self._state(JobState.PAUSED)
        elif self.state == JobState.PAUSED:
            self.control.resume()
            self._state(JobState.TRANSLATING)

    def cancel(self):
        if self.busy:
            self.control.cancel()
            self._state(JobState.CANCELLING)
