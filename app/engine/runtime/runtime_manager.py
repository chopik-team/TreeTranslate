from __future__ import annotations

from threading import Event, RLock, Timer
from time import monotonic
from contextlib import contextmanager

from app.engine.backends.base_backend import BaseBackend, check_cancelled
from app.engine.errors import TranslationCancelledError
from app.engine.types import InferenceOptions, PairKind, TranslationRequest


class RuntimeManager:
    """Keep one selected backend warm; idle unload never races native inference.

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

    @contextmanager
    def keep_warm(self):
        with self._lock:
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

    def run(self, backend: str, request: TranslationRequest, kind: PairKind,
            options: InferenceOptions, cancelled: Event):
        with self._lock:
            if self._closed:
                raise TranslationCancelledError()
            check_cancelled(cancelled)
            if self._timer:
                self._timer.cancel()
            if self._warm and self._warm != backend:
                self.backends[self._warm].shutdown()
            self._warm = backend
            try:
                return self.backends[backend].translate(request, kind, options, cancelled)
            except Exception:
                self.backends[backend].shutdown()
                self._warm = None
                raise
            finally:
                self._last_used = self.clock()
                self._schedule_idle()

    def release_idle(self) -> bool:
        with self._lock:
            if not self._pins and self._warm and self.idle_timeout_seconds > 0 and self.clock() - self._last_used >= self.idle_timeout_seconds:
                self.backends[self._warm].shutdown()
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

    def release_models(self) -> None:
        """Yield memory to document OCR at an admission-controlled job boundary."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
            if self._warm:
                self.backends[self._warm].shutdown()
                self._warm = None
