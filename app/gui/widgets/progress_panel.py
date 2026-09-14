from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout
from PySide6.QtGui import QIcon

from app.config.paths import icon_path

from app.models.translation_job import JobState, TranslationProgress


def _time(seconds: int) -> str:
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


class ProgressPanel(QFrame):
    pause_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent, objectName="progressPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        head = QHBoxLayout()
        head.addWidget(QLabel("Перевод", objectName="heading"))
        self.status = QLabel("Ожидание", objectName="progressStatus")
        head.addStretch()
        head.addWidget(self.status)
        layout.addLayout(head)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.bar, 1)
        self.percent = QLabel("0%", objectName="progressPercent")
        progress_row.addWidget(self.percent)
        layout.addLayout(progress_row)
        info = QGridLayout()
        self.current = QLabel("—", objectName="progressValue")
        self.processed = QLabel("0 / 0", objectName="progressValue")
        self.elapsed = QLabel("00:00:00", objectName="progressValue")
        self.remaining = QLabel("—", objectName="progressValue")
        details = (
            ("Текущий файл", self.current),
            ("Обработано объектов", self.processed),
            ("Прошло времени", self.elapsed),
            ("Осталось примерно", self.remaining),
        )
        for col, (caption, value) in enumerate(details):
            info.setColumnStretch(col, 1)
            info.addWidget(QLabel(caption, objectName="progressCaption"), 0, col)
            info.addWidget(value, 1, col)
        layout.addLayout(info)
        layout.addSpacing(12)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        self.pause = QPushButton(QIcon(icon_path("pause")), "  Приостановить")
        self.cancel = QPushButton(QIcon(icon_path("cancel")), "  Отменить", objectName="danger")
        self.pause.clicked.connect(self.pause_requested)
        self.cancel.clicked.connect(self.cancel_requested)
        buttons.addWidget(self.pause)
        buttons.addWidget(self.cancel)
        layout.addLayout(buttons)
        self.set_state(JobState.IDLE)

    def set_state(self, state: JobState) -> None:
        labels = {
            JobState.IDLE: "Ожидание", JobState.DRAGGING: "Добавление…", JobState.SCANNING: "Сканирование…",
            JobState.READY: "Готово к запуску", JobState.TRANSLATING: "Выполняется", JobState.PAUSED: "Приостановлено",
            JobState.CANCELLING: "Отмена…", JobState.COMPLETED: "Завершено", JobState.ERROR: "Ошибка", JobState.CANCELLED: "Отменено",
        }
        self.status.setText(labels[state])
        active = state in {JobState.TRANSLATING, JobState.PAUSED}
        self.pause.setEnabled(active)
        self.cancel.setEnabled(active)
        if state is JobState.PAUSED:
            self.pause.setIcon(QIcon(icon_path("play")))
            self.pause.setText("  Продолжить")
        else:
            self.pause.setIcon(QIcon(icon_path("pause")))
            self.pause.setText("  Приостановить")

    def set_progress(self, progress: TranslationProgress) -> None:
        self.bar.setValue(progress.percent)
        self.percent.setText(f"{progress.percent}%")
        self.current.setText(progress.current_file)
        self.processed.setText(f"{progress.processed} / {progress.total}")
        self.elapsed.setText(_time(progress.elapsed_seconds))
        remaining = round(progress.elapsed_seconds * (100 - progress.percent) / progress.percent) if progress.percent else 0
        self.remaining.setText(f"~{_time(remaining)}" if progress.percent else "—")
