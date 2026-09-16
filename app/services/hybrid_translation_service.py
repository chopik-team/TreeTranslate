from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from PySide6.QtCore import Qt, Signal, Slot

from app.config.settings import PerformanceSettings
from app.engine.errors import TranslationCancelledError, TranslationError
from app.engine.interfaces import TextTranslationEngine
from app.engine.types import DevicePreference, PerformanceProfile, TranslationRequest
from app.services.document_translation_service import DocumentTranslationService
from app.services.translation_service import TranslationService

PROFILE_NAMES = {
    "Эконом": PerformanceProfile.ECONOMY, "Быстрый": PerformanceProfile.FAST,
    "Баланс": PerformanceProfile.BALANCED, "Турбо": PerformanceProfile.TURBO,
    "Максимум": PerformanceProfile.MAXIMUM, "Автоматический": PerformanceProfile.AUTOMATIC,
}


class HybridTranslationService(TranslationService):
    """One native call plus one replaceable pending request, entirely off the GUI thread."""

    _worker_finished = Signal(object)

    def __init__(self, parent=None, *, engine: TextTranslationEngine | None = None) -> None:
        super().__init__(parent)
        if engine is None:
            from app.engine.factory import create_translation_engine
            engine = create_translation_engine()
        self.engine = engine
        self.real_files = True
        self.files = DocumentTranslationService(self)
        self.files.state_changed.connect(self.state_changed)
        self.files.scan_finished.connect(self.scan_finished)
        self.files.progress_changed.connect(self.progress_changed)
        self.files.file_outputs_ready.connect(self.file_outputs_ready)
        self._executor = None
        self._pending = None
        self._active_cancel = None
        self._closed = False
        self.text_busy = False
        self._worker_finished.connect(self._complete, Qt.ConnectionType.QueuedConnection)

    @property
    def state(self):
        return self.files.state

    @property
    def progress(self):
        return self.files.progress

    def configure(self, policy: PerformanceSettings) -> None:
        self.files.configure(policy)

    def executor(self):
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="TreeTranslate")
        return self._executor

    def scan(self, paths):
        self.files.scan(paths)

    def start(self):
        self.files.start()

    def pause_or_resume(self):
        self.files.pause_or_resume()

    def cancel(self):
        self.files.cancel()

    def submit_text(self, text: str, source: str, target: str,
                    policy: PerformanceSettings, request_id: str) -> None:
        if self._closed or self.files.busy:
            return
        request = TranslationRequest(
            text, source, target, DevicePreference(policy.device.lower()),
            PROFILE_NAMES.get(policy.mode, PerformanceProfile.AUTOMATIC), request_id,
            int(policy.cpu_threads) if policy.cpu_threads.isdigit() else None)
        self._pending = (request, policy.unload_model)
        if self._active_cancel:
            self._active_cancel.set()
        else:
            self._dispatch()

    def _dispatch(self):
        request, unload = self._pending
        self._pending = None
        cancelled = self._active_cancel = Event()
        if not self.text_busy:
            self.text_busy = True
            self.text_busy_changed.emit(True)
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="TreeTranslate")

        def work():
            try:
                # Worker-owned policy update, never racing an active native call.
                if hasattr(self.engine, "runtime"):
                    self.engine.runtime.idle_timeout_seconds = self.engine.policy.idle_timeout_seconds if unload else 0
                result = self.engine.translate(request, cancelled)
                return request.request_id, result, None, cancelled
            except TranslationCancelledError:
                return request.request_id, None, None, cancelled
            except Exception as error:
                message = str(error) if isinstance(error, TranslationError) else TranslationError.default_message
                return request.request_id, None, message, cancelled

        future = self._executor.submit(work)
        future.add_done_callback(lambda future: self._worker_finished.emit(future.result()))

    @Slot(object)
    def _complete(self, completion):
        request_id, result, error, cancelled = completion
        self._active_cancel = None
        if not self._closed and not cancelled.is_set():
            if result is not None:
                self.text_completed.emit(result)
            elif error:
                self.text_failed.emit(request_id, error)
        if self._pending and not self._closed:
            self._dispatch()
        else:
            self.text_busy = False
            self.text_busy_changed.emit(False)

    def cancel_text(self):
        self._pending = None
        if self._active_cancel:
            self._active_cancel.set()

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self.cancel_text()
        self.files.cancel()
        if self._executor:
            # Release native resources on their worker before tearing down that
            # thread's CUDA context. Main-thread cleanup after executor shutdown
            # can crash the Windows CUDA runtime during interpreter finalization.
            self._executor.submit(self.engine.shutdown).result()
            self._executor.shutdown(wait=True, cancel_futures=True)
        else:
            self.engine.shutdown()
