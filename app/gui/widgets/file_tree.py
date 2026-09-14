from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from app.models.file_item import FileItem
from app.config.paths import icon_path


class FileTree(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, objectName="panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        header = QHBoxLayout()
        title = QLabel("Предпросмотр найденных файлов", objectName="heading")
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(title, 1)
        self.badge = QLabel("")
        self.badge.setStyleSheet("background:#225f39; padding:3px 8px; border-radius:7px; font-weight:700")
        self.badge.hide()
        header.addWidget(self.badge)
        header.addStretch()
        self.stats = QLabel("Найдено: 0  •  Файлы: 0  •  Папки: 0", objectName="secondary")
        self.stats.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.stats.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.stats)
        layout.addLayout(header)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemChanged.connect(self._propagate_check)
        layout.addWidget(self.tree)
        self.show_empty()

    def show_empty(self) -> None:
        self.tree.clear()
        item = QTreeWidgetItem(["Здесь появится структура выбранных файлов"])
        item.setForeground(0, Qt.GlobalColor.gray)
        self.tree.addTopLevelItem(item)
        self.stats.setText("Найдено: 0  •  Файлы: 0  •  Папки: 0")
        self.badge.hide()

    def populate(self, root: FileItem) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        top = self._make_item(root)
        self.tree.addTopLevelItem(top)
        top.setExpanded(True)
        for index in range(top.childCount()):
            top.child(index).setExpanded(True)
        self.tree.blockSignals(False)
        files, folders = self._counts(root)
        self.stats.setText(f"Найдено: {files + folders}  •  Файлы: {files}  •  Папки: {folders}")
        suffix = Path(root.name).suffix.upper().removeprefix(".")
        if suffix in {"ZIP", "RAR"}:
            self.badge.setText(suffix)
            self.badge.show()
        else:
            self.badge.hide()

    def _make_item(self, model: FileItem) -> QTreeWidgetItem:
        item = QTreeWidgetItem([model.name])
        item.setIcon(0, QIcon(icon_path("folder" if model.is_folder else "file")))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked if model.checked else Qt.CheckState.Unchecked)
        for child in model.children:
            item.addChild(self._make_item(child))
        return item

    @staticmethod
    def _counts(item: FileItem) -> tuple[int, int]:
        files = 0 if item.is_folder else 1
        folders = 1 if item.is_folder else 0
        for child in item.children:
            child_files, child_folders = FileTree._counts(child)
            files += child_files
            folders += child_folders
        return files, folders

    def _propagate_check(self, item: QTreeWidgetItem, column: int) -> None:
        self.tree.blockSignals(True)
        state = item.checkState(0)
        for index in range(item.childCount()):
            child = item.child(index)
            child.setCheckState(0, state)
            self._propagate_to_children(child, state)
        self._update_parent(item.parent())
        self.tree.blockSignals(False)

    def _propagate_to_children(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for index in range(item.childCount()):
            child = item.child(index)
            child.setCheckState(0, state)
            self._propagate_to_children(child, state)

    def _update_parent(self, parent: QTreeWidgetItem | None) -> None:
        if parent is None:
            return
        states = {parent.child(i).checkState(0) for i in range(parent.childCount())}
        state = states.pop() if len(states) == 1 else Qt.CheckState.PartiallyChecked
        parent.setCheckState(0, state)
        self._update_parent(parent.parent())
