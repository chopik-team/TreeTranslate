from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from app.models.translation_job import JobState, TranslationProgress
from app.config.settings import PerformanceSettings
from app.services.translation_service import TranslationService


class MockTranslationService(TranslationService):
    """Deterministic UI placeholder; it performs no real translation or inference."""

    FILES = ["系统概述.pdf", "安装说明.docx", "启动车辆.pdf", "配置参考.docx", "readme.txt", "localization.json", "terms.xml", "notes.md"]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = JobState.IDLE
        self.progress = TranslationProgress(total=14)
        self._timer = QTimer(self, interval=420)
        self._timer.timeout.connect(self._tick)
        self.resource_policy = PerformanceSettings()

    def configure(self, policy: PerformanceSettings) -> None:
        self.resource_policy = policy
        intervals = {
            "Эконом": 700,
            "Быстрый": 520,
            "Баланс": 420,
            "Турбо": 260,
            "Максимум": 180,
        }
        self._timer.setInterval(intervals.get(policy.mode, 420))

    def _set_state(self, state: JobState) -> None:
        self.state = state
        self.state_changed.emit(state)

    def scan(self) -> None:
        self._timer.stop()
        self._set_state(JobState.SCANNING)
        QTimer.singleShot(700, self._finish_scan)

    def _finish_scan(self) -> None:
        if self.state is not JobState.SCANNING:
            return
        self._set_state(JobState.READY)
        self.scan_finished.emit()

    def start(self) -> None:
        self.progress = TranslationProgress(total=14)
        self._set_state(JobState.TRANSLATING)
        self._timer.start()
        self.progress_changed.emit(self.progress)

    def pause_or_resume(self) -> None:
        if self.state is JobState.TRANSLATING:
            self._timer.stop()
            self._set_state(JobState.PAUSED)
        elif self.state is JobState.PAUSED:
            self._set_state(JobState.TRANSLATING)
            self._timer.start()

    def cancel(self) -> None:
        self._timer.stop()
        self._set_state(JobState.CANCELLING)
        self._set_state(JobState.CANCELLED)

    def simulate_error(self) -> None:
        self._timer.stop()
        self._set_state(JobState.ERROR)

    def translate_text(self, text: str) -> str:
        if not text.strip():
            return ""
        normalized = text.strip().casefold()
        basic_dictionary = {
            "привет": "Hi",
            "здравствуйте": "Hello",
            "добрый день": "Good afternoon",
            "спасибо": "Thank you",
            "до свидания": "Goodbye",
            "hello": "Привет",
            "hi": "Привет",
            "thank you": "Спасибо",
            "goodbye": "До свидания",
            "你好": "Привет",
            "谢谢": "Спасибо",
        }
        if normalized in basic_dictionary:
            return basic_dictionary[normalized]
        return "Демонстрационный перевод: " + text.strip()

    def _tick(self) -> None:
        p = self.progress
        p.elapsed_seconds += 1
        p.percent = min(100, p.percent + 4)
        p.processed = min(p.total, round(p.total * p.percent / 100))
        p.current_file = self.FILES[min(len(self.FILES) - 1, p.processed * len(self.FILES) // p.total)]
        self.progress_changed.emit(p)
        if p.percent >= 100:
            self._timer.stop()
            self._set_state(JobState.COMPLETED)
