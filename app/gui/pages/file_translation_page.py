from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.config.paths import icon_path
from app.gui.widgets.acceleration_selector import AccelerationSelector
from app.gui.widgets.drop_zone import DropZone
from app.gui.widgets.file_tree import FileTree
from app.gui.widgets.language_selector import LanguageSelector
from app.gui.widgets.progress_panel import ProgressPanel
from app.gui.widgets.toggle_switch import ToggleSwitch
from app.gui.widgets.translation_mode import TranslationMode
from app.gui.widgets.workspace_splitter import WorkspaceSplitter


class FileTranslationPage(QWidget):
    start_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(8)
        splitter = WorkspaceSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(13)
        splitter.addWidget(self._build_source_panel())
        splitter.addWidget(self._build_workspace())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 7)
        splitter.setSizes([470, 820])
        root.addWidget(splitter)
        self._initial_splitter_timer = QTimer(self, singleShot=True)
        self._initial_splitter_timer.timeout.connect(
            lambda: splitter.setSizes([470, max(700, splitter.width() - 477)])
        )
        self._initial_splitter_timer.start(0)

    def _build_source_panel(self) -> QWidget:
        panel = QFrame(objectName="sourcePanel")
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(540)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)
        self.drop_zone = DropZone()
        layout.addWidget(self.drop_zone, 1)
        divider = QFrame(objectName="divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addWidget(QLabel("Дополнительные параметры", objectName="caption"))
        layout.addLayout(self._option_row("Перевести папки", "Названия каталогов", True))
        return panel

    def _option_row(self, title: str, suffix: str, checked: bool) -> QHBoxLayout:
        row = QHBoxLayout()
        toggle = ToggleSwitch(checked)
        if title == "Перевести папки":
            self.translate_folders = toggle
        text = QLabel(title + (f" ({suffix})" if suffix else ""))
        row.addWidget(toggle)
        row.addWidget(text)
        row.addStretch()
        return row

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_options_panel())
        self.file_tree = FileTree()
        layout.addWidget(self.file_tree, 1)
        self.progress = ProgressPanel()
        layout.addWidget(self.progress)
        return workspace

    def _build_options_panel(self) -> QWidget:
        panel = QFrame(objectName="panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(11)
        self.languages = LanguageSelector()
        layout.addWidget(self.languages)
        controls = QHBoxLayout()
        self.mode = TranslationMode()
        self.acceleration = AccelerationSelector()
        controls.addWidget(self.mode, 1)
        controls.addSpacing(18)
        controls.addWidget(self.acceleration, 1)
        layout.addLayout(controls)
        self.start_button = QPushButton(QIcon(icon_path("play")), "  Начать перевод", objectName="primary")
        self.start_button.clicked.connect(self.start_requested)
        self.start_button.setEnabled(False)
        layout.addWidget(self.start_button)
        return panel
