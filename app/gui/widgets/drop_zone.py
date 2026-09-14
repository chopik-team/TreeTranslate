from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QPushButton, QVBoxLayout

from app.config.paths import icon_path


class DropZone(QFrame):
    paths_dropped = Signal(list)
    browse_files_requested = Signal()
    browse_folder_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent, objectName="dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(390)
        self.setProperty("dragActive", False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 26, 24, 24)
        layout.setSpacing(10)
        layout.addStretch()
        icon = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(QIcon(icon_path("file")).pixmap(62, 62))
        title = QLabel("Перетащите папку, файлы\nили архив сюда", alignment=Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("heading")
        hint = QLabel(
            "Поддерживаются папки и отдельные файлы\n"
            "Архивы: .ZIP, .RAR  •  Документы: .PDF, .DOCX, .TXT, .MD",
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        hint.setObjectName("secondary")
        choose = QPushButton(QIcon(icon_path("folder")), "  Выбрать папку / файлы", objectName="outlinePrimary")
        choose.setMinimumHeight(48)
        choose_menu = QMenu(choose)
        files_action = choose_menu.addAction(QIcon(icon_path("file")), "Выбрать файлы")
        folder_action = choose_menu.addAction(QIcon(icon_path("folder")), "Выбрать папку")
        files_action.triggered.connect(self.browse_files_requested)
        folder_action.triggered.connect(self.browse_folder_requested)
        choose_menu.aboutToShow.connect(lambda: choose_menu.setFixedWidth(choose.width()))
        choose.setMenu(choose_menu)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(8)
        layout.addWidget(choose)
        layout.addStretch()

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag_active(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_drag_active(False)
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()
