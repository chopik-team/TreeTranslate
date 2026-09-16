from contextlib import nullcontext
from dataclasses import replace
import logging

from PySide6.QtCore import Signal, Qt, QTimer

from app.documents.control import JobControl
from app.documents.errors import DocumentError
from app.documents.job import DocumentJob, DocumentConfig
from app.documents.scanner import scan_sources, ScanResult
from app.engine.errors import TranslationCancelledError, TranslationError
from app.models.translation_job import JobState, TranslationProgress
from app.services.translation_service import TranslationService


class DocumentTranslationService(TranslationService):
    finished = Signal(object)
    failed = Signal(str)

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
        self.finished.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self.progress_changed.connect(self._progress, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self._tick)

    def _state(self, state):
        self.state = state
        self.state_changed.emit(state)

    def _progress(self, progress):
        self.progress = progress

    def _tick(self):
        self.progress_changed.emit(replace(self.progress, elapsed_seconds=int(self.control.elapsed)))

    def configure(self, policy):
        self.policy = policy

    @property
    def busy(self):
        return self.state in {JobState.SCANNING, JobState.TRANSLATING, JobState.PAUSED, JobState.CANCELLING}

    def _submit(self, operation, scanning=False):
        if self.busy or self.owner.text_busy or self.owner._closed:
            return
        self.control = JobControl()
        self.progress = TranslationProgress(total=0)
        self._state(JobState.SCANNING if scanning else JobState.TRANSLATING)
        self.progress_changed.emit(self.progress)
        self.timer.start()
        def work():
            try:
                return scanning, operation(), None, False
            except TranslationCancelledError:
                return scanning, None, None, True
            except Exception as error:
                logging.getLogger(__name__).warning('DOCX operation failed type=%s', type(error).__name__)
                message = str(error) if isinstance(error, (DocumentError, TranslationError)) else 'Не удалось обработать DOCX или сохранить результат.'
                return scanning, None, message, False
        self.owner.executor().submit(work).add_done_callback(lambda f: self.finished.emit(f.result()))

    def scan(self, paths):
        self._submit(lambda: scan_sources(paths, self.control), True)

    def start(self):
        def run():
            engine = self.owner.engine
            runtime = getattr(engine, 'runtime', None)
            if runtime and self.policy:
                runtime.idle_timeout_seconds = engine.policy.idle_timeout_seconds if self.policy.unload_model else 0
            with runtime.keep_warm() if runtime else nullcontext():
                return DocumentJob(self.selected, self.config, self.control, engine.translate, engine.languages.resolve,
                                   self.progress_changed.emit, self.file_outputs_ready.emit).run()
        self._submit(run)

    def _finish(self, result):
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
            self.scan_result = value
            self.selected = value.files
            self._state(JobState.READY)
            self.scan_finished.emit()
        else:
            self._state(JobState.COMPLETED)

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
