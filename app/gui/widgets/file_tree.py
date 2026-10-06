from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Slot
from PySide6.QtGui import QIcon, QColor, QCursor
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QLabel, QSizePolicy, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from app.models.file_item import FileItem
from app.config.paths import icon_path
from app.gui.widgets.animated_icon import AnimatedIcon

from app.localization.widgets import QLabel
from app.documents.job import filename_stem


class _DocumentTree(QTreeWidget):
    """Paint one background across branches, checkboxes and document text."""
    def drawRow(self, painter, option, index):
        super().drawRow(painter, option, index)
        completed = bool(index.data(Qt.ItemDataRole.UserRole + 3))
        progress = index.data(Qt.ItemDataRole.UserRole + 4)
        hovered = self.indexAt(self.viewport().mapFromGlobal(QCursor.pos())) == index
        if completed or progress is not None or hovered:
            painter.save()
            rect = option.rect.adjusted(-option.rect.left(), 0,
                                        self.viewport().width() - option.rect.right() - 1, 0)
            painter.fillRect(rect, QColor(128, 128, 128, 35 if hovered else 20))
            fraction = 100 if completed else int(progress or 0)
            if fraction:
                fill = rect.adjusted(0, 0, -round(rect.width() * (1 - fraction / 100)), 0)
                is_folder = bool(index.data(Qt.ItemDataRole.UserRole + 1))
                opacity = (55 if hovered else 35) if is_folder else (110 if hovered else 85)
                painter.fillRect(fill, QColor(25, 166, 83, opacity))
            painter.restore()


class FileTree(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, objectName="panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        header = QHBoxLayout()
        title = QLabel("Предпросмотр найденных файлов", objectName="heading")
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(title, 1)
        self.badge = QLabel("", objectName="fileCountBadge")
        self.badge.hide()
        header.addWidget(self.badge)
        header.addStretch()
        self.stats = QLabel("Найдено: 0  •  Файлы: 0  •  Папки: 0", objectName="secondary")
        self.stats.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.stats.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.stats)
        layout.addLayout(header)
        self.tree = _DocumentTree()
        self.tree.setObjectName("documentTree")
        self.tree.setHeaderHidden(True)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.itemChanged.connect(self._propagate_check)
        self._folder_animation = AnimatedIcon("folder", self)
        self._animated_item = None
        self._folder_animation.changed.connect(self._set_folder_frame)
        self._root_animation = AnimatedIcon("folder", self)
        self._root_item = None
        self._root_animation.changed.connect(self._set_root_frame)
        self.tree.setMouseTracking(True)
        self.tree.itemEntered.connect(self._hover_item)
        self.tree.viewport().installEventFilter(self)
        layout.addWidget(self.tree)
        self.show_empty()
        from app.localization import localization
        localization.widgets.add(self)

    def retranslate(self):
        from app.localization import tr
        item = self.tree.topLevelItem(0)
        if item and item.data(0, Qt.ItemDataRole.UserRole+2):
            item.setText(0,tr(item.data(0, Qt.ItemDataRole.UserRole+2)))

    def show_empty(self) -> None:
        self._stop_folder_animation()
        self._root_animation.stop()
        self._root_item = None
        self.tree.clear()
        self.tree.setRootIsDecorated(False)
        item = QTreeWidgetItem(["Здесь появится структура выбранных файлов"])
        from app.localization import tr
        item.setData(0, Qt.ItemDataRole.UserRole+2, 'Здесь появится структура выбранных файлов')
        item.setText(0,tr('Здесь появится структура выбранных файлов'))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setForeground(0, Qt.GlobalColor.gray)
        self.tree.addTopLevelItem(item)
        self.stats.setText("Найдено: 0  •  Файлы: 0  •  Папки: 0")
        self.badge.hide()

    def populate(self, root: FileItem) -> None:
        self._stop_folder_animation()
        self._root_animation.stop()
        self._root_item = None
        self.tree.blockSignals(True)
        self.tree.clear()
        self.tree.setRootIsDecorated(True)
        top = self._make_item(root)
        if root.name == 'Выбранные документы' and not root.path:
            from app.localization import tr
            top.setData(0, Qt.ItemDataRole.UserRole+2, root.name)
            top.setText(0,tr(root.name))
        self.tree.addTopLevelItem(top)
        if root.is_folder:
            self._root_item = top
            if self.isVisible():
                self._root_animation.start()
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
        path = Path(model.name)
        name = filename_stem(path.stem, path.suffix) + path.suffix if not model.is_folder and path.suffix else model.name
        item = QTreeWidgetItem([name])
        item.setToolTip(0, model.path or model.name)
        item.setData(0, Qt.ItemDataRole.UserRole, model.path)
        extension = Path(model.path or model.name).suffix.lower().lstrip(".")
        icon = "folder" if model.is_folder else extension if extension in {"docx", "pdf"} else "file"
        item.setData(0, Qt.ItemDataRole.UserRole + 1, model.is_folder)
        item.setIcon(0, self._folder_animation.frames[0] if model.is_folder else QIcon(icon_path(icon)))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked if model.checked else Qt.CheckState.Unchecked)
        for child in model.children:
            item.addChild(self._make_item(child))
        return item

    @Slot(object, object)
    def mark_completed(self, source, output):
        """Published documents stay visible and are excluded from the next attempt."""
        def visit(item):
            if item.data(0, Qt.ItemDataRole.UserRole) == str(source):
                blocked = self.tree.blockSignals(True)
                item.setData(0, Qt.ItemDataRole.UserRole + 3, str(output))
                item.setData(0, Qt.ItemDataRole.UserRole + 4, 100)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                self._update_parent(item.parent())
                self.tree.blockSignals(blocked)
            for index in range(item.childCount()):
                visit(item.child(index))
        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))
        self._update_folder_progress()

    def set_progress(self, progress):
        if not progress.source_path:
            return
        def visit(item):
            if item.data(0, Qt.ItemDataRole.UserRole) == progress.source_path:
                blocked = self.tree.blockSignals(True)
                item.setData(0, Qt.ItemDataRole.UserRole + 4, progress.file_percent)
                # A confirmed rerun starts a new fill, while its previous output survives.
                if progress.file_percent < 100:
                    item.setData(0, Qt.ItemDataRole.UserRole + 3, None)
                self.tree.blockSignals(blocked)
            for index in range(item.childCount()):
                visit(item.child(index))
        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))
        self._update_folder_progress()
        self.tree.viewport().update()

    def _update_folder_progress(self):
        """Fill ancestor rows from the selected/processed descendant documents."""
        def aggregate(item):
            if not item.data(0, Qt.ItemDataRole.UserRole + 1):
                completed = bool(item.data(0, Qt.ItemDataRole.UserRole + 3))
                progress = item.data(0, Qt.ItemDataRole.UserRole + 4)
                supported = Path(item.data(0, Qt.ItemDataRole.UserRole) or item.text(0)).suffix.lower() in {'.pdf', '.docx', '.zip'}
                included = supported and (completed or progress is not None or item.checkState(0) == Qt.CheckState.Checked)
                if not included:
                    return 0, 0, False
                percent = 100 if completed else min(99, max(0, int(progress or 0)))
                return percent, 1, completed or progress is not None
            total, count, active = 0, 0, False
            for index in range(item.childCount()):
                value, children, touched = aggregate(item.child(index))
                total += value
                count += children
                active |= touched
            percent = (100 if total == 100 * count else min(99, round(total / count))) if count and active else None
            item.setData(0, Qt.ItemDataRole.UserRole + 4, percent)
            return total, count, active
        blocked = self.tree.blockSignals(True)
        for index in range(self.tree.topLevelItemCount()):
            aggregate(self.tree.topLevelItem(index))
        self.tree.blockSignals(blocked)
        self.tree.viewport().update()

    def set_busy(self, busy):
        # Keep the view enabled for full-row hover; only selection is locked.
        starting = busy and not getattr(self, '_busy', False)
        self._busy = busy
        def visit(item):
            flags = item.flags()
            if starting and not item.data(0, Qt.ItemDataRole.UserRole + 1) and item.checkState(0) == Qt.CheckState.Checked:
                item.setData(0, Qt.ItemDataRole.UserRole + 4, 0)
            item.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable if busy
                          else flags | Qt.ItemFlag.ItemIsUserCheckable)
            for index in range(item.childCount()):
                visit(item.child(index))
        blocked = self.tree.blockSignals(True)
        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))
        self.tree.blockSignals(blocked)

        self._update_folder_progress()

    def _set_folder_frame(self, icon):
        if self._animated_item is not None:
            blocked = self.tree.blockSignals(True)
            self._animated_item.setIcon(0, icon)
            self.tree.blockSignals(blocked)

    def _set_root_frame(self, icon):
        if self._root_item is not None:
            blocked = self.tree.blockSignals(True)
            self._root_item.setIcon(0, icon)
            self.tree.blockSignals(blocked)

    def _stop_folder_animation(self):
        self._folder_animation.stop()
        self._animated_item = None

    def _hover_item(self, item, _column):
        if item is self._animated_item:
            return
        self._stop_folder_animation()
        if item is not self._root_item and item.data(0, Qt.ItemDataRole.UserRole + 1):
            self._animated_item = item
            self._folder_animation.start()

    def eventFilter(self, watched, event):
        if watched is self.tree.viewport():
            if event.type() in (QEvent.Type.Leave, QEvent.Type.Hide):
                self._stop_folder_animation()
            elif event.type() == QEvent.Type.MouseMove and self.tree.itemAt(event.pos()) is None:
                self._stop_folder_animation()
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        self._stop_folder_animation()
        self._root_animation.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._root_item is not None:
            self._root_animation.start()

    def selected_paths(self):
        paths = []
        def visit(item):
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path and item.checkState(0) == Qt.CheckState.Checked:
                paths.append(Path(path))
            for index in range(item.childCount()):
                visit(item.child(index))
        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))
        return paths

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
        self._update_folder_progress()

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
