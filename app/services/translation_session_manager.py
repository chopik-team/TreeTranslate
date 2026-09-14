from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class TranslationSessionManager(QObject):
    """Central policy for active translation jobs; concurrency may grow later."""

    active_jobs_changed = Signal()

    def __init__(self, max_active_translation_jobs: int = 1, parent=None) -> None:
        super().__init__(parent)
        self.max_active_translation_jobs = max_active_translation_jobs
        self._active_jobs: set[str] = set()

    def can_start(self, job_kind: str) -> bool:
        return job_kind in self._active_jobs or len(self._active_jobs) < self.max_active_translation_jobs

    def start(self, job_kind: str) -> bool:
        if not self.can_start(job_kind):
            return False
        if job_kind not in self._active_jobs:
            self._active_jobs.add(job_kind)
            self.active_jobs_changed.emit()
        return True

    def finish(self, job_kind: str) -> None:
        if job_kind in self._active_jobs:
            self._active_jobs.remove(job_kind)
            self.active_jobs_changed.emit()

    def is_active(self, job_kind: str) -> bool:
        return job_kind in self._active_jobs

    def conflicts_with(self, job_kind: str) -> bool:
        return not self.can_start(job_kind)
