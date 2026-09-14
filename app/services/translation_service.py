from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.config.settings import PerformanceSettings


class TranslationService(QObject):
    """Controller-facing service boundary; a future implementation will wrap TranslationEngine."""

    state_changed = Signal(object)
    scan_finished = Signal()
    progress_changed = Signal(object)

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
