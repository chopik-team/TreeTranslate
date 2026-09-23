from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout
from PySide6.QtGui import QIcon
from pathlib import Path

from app.config.paths import icon_path

from app.models.translation_job import JobState, TranslationProgress


def _time(seconds: int) -> str:
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


class ProgressPanel(QFrame):
    pause_requested = Signal()
    cancel_requested = Signal()
    show_output_requested = Signal()
    open_file_requested = Signal()

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
            ("Обработано сегментов", self.processed),
            ("Прошло времени", self.elapsed),
            ("Осталось примерно", self.remaining),
        )
        for col, (caption, value) in enumerate(details):
            info.setColumnStretch(col, 1)
            label=QLabel(caption, objectName="progressCaption")
            if col==1:self.processed_caption=label
            info.addWidget(label, 0, col)
            info.addWidget(value, 1, col)
        layout.addLayout(info)
        layout.addSpacing(12)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        self.show_output = QPushButton(QIcon(icon_path("folder")), "  Открыть папку")
        self.open_file = QPushButton("Открыть файл")
        self.open_file.clicked.connect(self.open_file_requested)
        buttons.addWidget(self.open_file)
        self.pause = QPushButton(QIcon(icon_path("pause")), "  Приостановить")
        self.cancel = QPushButton(QIcon(icon_path("cancel")), "  Отменить", objectName="danger")
        self.show_output.clicked.connect(self.show_output_requested)
        self.pause.clicked.connect(self.pause_requested)
        self.cancel.clicked.connect(self.cancel_requested)
        buttons.addWidget(self.show_output)
        buttons.addWidget(self.pause)
        buttons.addWidget(self.cancel)
        layout.addLayout(buttons)
        self.output_location = QLabel('', objectName='secondary')
        self.output_location.setWordWrap(True)
        layout.addWidget(self.output_location)
        self._output_paths: tuple[Path, ...] = ()
        self.set_state(JobState.IDLE)

    def set_state(self, state: JobState) -> None:
        self._state = state
        labels = {
            JobState.IDLE: "Ожидание", JobState.DRAGGING: "Добавление…", JobState.SCANNING: "Сканирование…",
            JobState.READY: "Готово к запуску", JobState.TRANSLATING: "Выполняется", JobState.PAUSED: "Приостановлено",
            JobState.CANCELLING: "Отмена…", JobState.COMPLETED: "Перевод завершён", JobState.ERROR: "Ошибка", JobState.CANCELLED: "Отменено",
        }
        self.status.setText(labels[state])
        active = state in {JobState.TRANSLATING, JobState.PAUSED}
        self.pause.setEnabled(active)
        self.cancel.setEnabled(active or state == JobState.SCANNING)
        self.show_output.setEnabled(bool(self._output_paths))
        self.open_file.setEnabled(bool(self._output_paths))
        if state is JobState.PAUSED:
            self.pause.setIcon(QIcon(icon_path("play")))
            self.pause.setText("  Продолжить")
        else:
            self.pause.setIcon(QIcon(icon_path("pause")))
            self.pause.setText("  Приостановить")

    def set_output_paths(self, paths) -> None:
        self._output_paths = tuple(Path(path) for path in paths if Path(path).exists())
        self.output_location.setText(str(self._output_paths[-1]) if self._output_paths else '')
        self.show_output.setEnabled(bool(self._output_paths))
        self.open_file.setEnabled(bool(self._output_paths))

    @property
    def output_paths(self) -> tuple[Path, ...]:
        return self._output_paths

    def set_progress(self, progress: TranslationProgress) -> None:
        stages = {'EXTRACTING': 'Извлечение текста…', 'TRANSLATING': 'Перевод…',
                  'RENDERING': 'Подготовка страницы…', 'OCR': 'Распознавание текста…',
                  'LAYOUT_ANALYSIS': 'Анализ структуры страницы…',
                  'WRITING': 'Запись документа…', 'VALIDATING': 'Проверка результата…'}
        if self._state == JobState.TRANSLATING and progress.stage in stages:
            self.status.setText(stages[progress.stage])
        self.bar.setValue(progress.percent)
        self.percent.setText(f"{progress.percent}%")
        prefix = f"{progress.file_index}/{progress.file_total} · " if progress.file_total else ""
        self.current.setText(prefix + progress.current_file)
        self.processed.setText(f"{progress.page_index} / {progress.page_total} стр." if progress.page_total else f"{progress.processed} / {progress.total}")
        self.processed_caption.setText('Страница OCR' if progress.page_total else 'Обработано сегментов')
        self.elapsed.setText(_time(progress.elapsed_seconds))
        remaining = progress.eta_seconds if progress.eta_seconds is not None else round(progress.elapsed_seconds * (100 - progress.percent) / progress.percent) if progress.percent else 0
        self.remaining.setText(_time(remaining) if progress.percent or progress.eta_seconds is not None else "—")
