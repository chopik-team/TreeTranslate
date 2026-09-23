from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout

from app.config.paths import icon_path
from app.gui.widgets.animated_icon import AnimatedIcon


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
        icons = QHBoxLayout()
        icons.setSpacing(16)
        icons.addStretch()
        for format_name in ("docx", "pdf"):
            icon = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
            icon.setObjectName(f"dropIcon_{format_name}")
            icon.setPixmap(QIcon(icon_path(format_name)).pixmap(62, 62))
            icon.setToolTip(format_name.upper())
            icon.setAccessibleName(format_name.upper())
            icons.addWidget(icon)
        icons.addStretch()
        title = QLabel("Перетащите DOCX/PDF\nили папку сюда", alignment=Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("heading")
        hint = QLabel(
            "Документы .DOCX и .PDF\n"
            "Папки проверяются вместе с вложенными каталогами",
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        hint.setObjectName("secondary")
        choose = QPushButton(QIcon(icon_path("folder")), "  Выбрать папку / файлы", objectName="outlinePrimary")
        choose.setMinimumHeight(48)
        choose_menu = QMenu(choose)
        files_action = choose_menu.addAction(QIcon(icon_path("file")), "Выбрать файлы")
        folder_action = choose_menu.addAction(QIcon(icon_path("folder")), "Выбрать папку")
        self._menu_icons = {}
        for action, name in ((files_action, "document"), (folder_action, "add-folder")):
            animation = AnimatedIcon(name, choose_menu)
            action.setIcon(animation.icon)
            animation.changed.connect(action.setIcon)
            self._menu_icons[action] = animation
        choose_menu.hovered.connect(self._animate_menu_icon)
        choose_menu.aboutToHide.connect(self._stop_menu_icons)
        self._choose_menu = choose_menu
        choose_menu.installEventFilter(self)
        files_action.triggered.connect(self.browse_files_requested)
        folder_action.triggered.connect(self.browse_folder_requested)
        choose_menu.aboutToShow.connect(lambda: choose_menu.setFixedWidth(choose.width()))
        choose.setMenu(choose_menu)
        layout.addLayout(icons)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(8)
        layout.addWidget(choose)
        layout.addStretch()

    def _animate_menu_icon(self, hovered):
        for action, animation in self._menu_icons.items():
            animation.start() if action == hovered else animation.stop()

    def _stop_menu_icons(self):
        for animation in self._menu_icons.values():
            animation.stop()

    def eventFilter(self, watched, event):
        if watched is self._choose_menu:
            if event.type() == QEvent.Type.Leave:
                self._stop_menu_icons()
            elif event.type() == QEvent.Type.MouseMove:
                self._animate_menu_icon(self._choose_menu.actionAt(event.pos()))
        return super().eventFilter(watched, event)

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
