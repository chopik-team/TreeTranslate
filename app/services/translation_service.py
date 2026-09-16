from __future__ import annotations

from PySide6.QtCore import QObject, Signal, QTimer

from app.config.settings import PerformanceSettings


class TranslationService(QObject):
    """Controller-facing boundary for text and document jobs."""

    state_changed = Signal(object)
    scan_finished = Signal()
    progress_changed = Signal(object)
    file_outputs_ready = Signal(object)
    text_completed = Signal(object)
    text_failed = Signal(str, str)
    text_busy_changed = Signal(bool)
    text_busy = False

    def submit_text(self, text: str, source: str, target: str,
                    policy: PerformanceSettings, request_id: str) -> None:
        """Compatibility adapter for the AW 0.3 mock, never used for real inference."""
        from app.engine.types import TranslationResult
        self.text_busy = True
        self.text_busy_changed.emit(True)

        def complete():
            self.text_completed.emit(TranslationResult(self.translate_text(text), source, target,
                                                       "mock", "none", 0, "UI test mock", False, request_id))
            self.text_busy = False
            self.text_busy_changed.emit(False)
        QTimer.singleShot(0, complete)

    def cancel_text(self) -> None:
        pass

    def shutdown(self) -> None:
        self.cancel()

    def configure(self, policy: PerformanceSettings) -> None:
        raise NotImplementedError

    def scan(self) -> None:
        raise NotImplementedError

    def start(self) -> None:
        raise NotImplementedError

    def pause_or_resume(self) -> None:
        raise NotImplementedError

    def cancel(self) -> None:
        raise NotImplementedError

    def translate_text(self, text: str) -> str:
        raise NotImplementedError
