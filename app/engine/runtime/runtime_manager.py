from __future__ import annotations

from threading import Event, RLock, Timer
from time import monotonic
from contextlib import contextmanager
from app.config.logging_config import timed_process
from app.documents.run_metrics import measure

from app.engine.backends.base_backend import BaseBackend, check_cancelled
from app.engine.errors import BackendUnavailableError, DeviceUnavailableError, TranslationCancelledError, TranslationError
from app.engine.types import InferenceOptions, PairKind, TranslationRequest


class RuntimeManager:
    """Keep run backends warm; idle unload never races native inference.

    This resource lock is not job admission policy; the session manager owns that.
    """

    def __init__(self, backends: dict[str, BaseBackend], idle_timeout_seconds: float = 180,
                 clock=monotonic) -> None:
        self.backends = backends
        self.idle_timeout_seconds = idle_timeout_seconds
        self.clock = clock
        self._lock = RLock()
        self._warm: str | None = None
        self._last_used = 0.0
        self._timer: Timer | None = None
        self._closed = False
        self._pins = 0
        self._loaded = set()
        self._blocked = {}

    @contextmanager
    def keep_warm(self):
        with self._lock:
            if not self._pins:
                self._blocked.clear()  # A new run can retry repaired devices/models.
            self._pins += 1
            if self._timer:
                self._timer.cancel()
        try:
            yield
        finally:
            with self._lock:
                self._pins -= 1
                self._last_used = self.clock()
                self._schedule_idle()

    def _schedule_idle(self) -> None:
        if self._timer:
            self._timer.cancel()
        if self.idle_timeout_seconds > 0 and not self._closed and not self._pins:
            self._timer = Timer(self.idle_timeout_seconds, self.release_idle)
            self._timer.daemon = True
            self._timer.start()

    @staticmethod
    def _failure_key(backend, request, kind, options):
        return (backend, request.source_language, request.target_language, kind,
                options.device, options.compute_type, options.threads)

    def blocked_error(self, backend, request, kind, options):
        with self._lock:
            return self._blocked.get(self._failure_key(backend, request, kind, options)) if self._pins else None

    @timed_process('translation_backend')
    @measure('model_translation',model=True)
    def run(self, backend: str, request: TranslationRequest, kind: PairKind,
            options: InferenceOptions, cancelled: Event):
        with self._lock:
            if self._closed:
                raise TranslationCancelledError()
            check_cancelled(cancelled)
            if self._timer:
                self._timer.cancel()
            blocked = self.blocked_error(backend, request, kind, options)
            if blocked is not None:
                raise type(blocked)() from None
            if not self._pins:
                for previous in self._loaded - {backend}:
                    self.backends[previous].shutdown()
                self._loaded.intersection_update({backend})
            self._warm = backend
            self._loaded.add(backend)
            try:
                return self.backends[backend].translate(request, kind, options, cancelled)
            except Exception as error:
                # Model/device initialization failures are deterministic for this
                # run. A rejected input/decoder result is NOT a circuit failure.
                if isinstance(error, (BackendUnavailableError, DeviceUnavailableError)):
                    if self._pins:
                        self._blocked[self._failure_key(backend, request, kind, options)] = error
                    self.backends[backend].shutdown()
                    self._loaded.discard(backend)
                    self._warm = next(iter(self._loaded), None)
                elif not isinstance(error, TranslationError):
                    self.backends[backend].shutdown()
                    self._loaded.discard(backend)
                    self._warm = next(iter(self._loaded), None)
                raise
            finally:
                self._last_used = self.clock()
                self._schedule_idle()

    def release_idle(self) -> bool:
        with self._lock:
            if not self._pins and self._loaded and self.idle_timeout_seconds > 0 and self.clock() - self._last_used >= self.idle_timeout_seconds:
                for name in self._loaded:
                    self.backends[name].shutdown()
                self._loaded.clear()
                self._warm = None
                self._timer = None
                return True
            return False

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            if self._timer:
                self._timer.cancel()
            for backend in self.backends.values():
                backend.shutdown()
            self._warm = None
            self._loaded.clear()
            self._blocked.clear()

    def release_models(self) -> None:
        """Yield memory to document OCR at an admission-controlled job boundary."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
            for name in self._loaded:
                self.backends[name].shutdown()
            self._loaded.clear()
            self._warm = None
