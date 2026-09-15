from dataclasses import dataclass

from PySide6.QtCore import QItemSelectionModel, QSize, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget


@dataclass(frozen=True, slots=True)
class ModePresentation:
    name: str
    priority: str
    load: str
    device_hint: str

    def as_row(self) -> tuple[str, str, str, str]:
        return self.name, self.priority, self.load, self.device_hint


# No invented words/minute or RAM requirements. Timing depends on text and device.
MODE_PRESENTATIONS = (
    ModePresentation("🍂  Эконом", "бережёт ресурсы", "низкая", "CPU в Auto"),
    ModePresentation("🚶  Быстрый", "быстрый ответ", "умеренная", "CPU или GPU"),
    ModePresentation("🚙  Баланс", "тщательный перевод", "повышенная", "CPU или GPU"),
    ModePresentation("⚡  Турбо", "пакетная обработка", "высокая", "GPU желательно"),
    ModePresentation("🚀  Максимум", "расширенный поиск", "высокая", "CPU или GPU"),
)


class ModeTableView(QTableView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            self.selectionModel().select(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.clearSelection()
        super().leaveEvent(event)


class ModeRequirementsCombo(QComboBox):
    """Mode picker whose popup explains the trade-offs before selection."""

    def __init__(self, include_automatic: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self._model.setHorizontalHeaderLabels(["Режим", "Приоритет", "Нагрузка", "Устройство"])
        rows = [presentation.as_row() for presentation in MODE_PRESENTATIONS]
        if include_automatic:
            rows.insert(0, ("Автоматический", "настройки Баланса", "по устройству", "GPU при наличии"))
        for row in rows:
            items = [QStandardItem(value) for value in row]
            for item in items:
                item.setEditable(False)
            self._model.appendRow(items)
        table = ModeTableView()
        table.setModel(self._model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setShowGrid(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(38)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 170)
        table.setColumnWidth(1, 190)
        table.setColumnWidth(2, 180)
        table.setMinimumHeight(260 if include_automatic else 225)
        self.setModel(self._model)
        self.setModelColumn(0)
        self.setView(table)
        self.setCurrentIndex(0)
        self.setToolTip("Режим задаёт нагрузку и глубину поиска перевода. CPU/GPU выбирается отдельно.\nБолее высокий режим не гарантирует лучший перевод каждой фразы.")

    def showPopup(self) -> None:
        super().showPopup()
        popup = self.view().window()
        popup.resize(790, popup.height())

    def sizeHint(self) -> QSize:
        return QSize(300, 42)

    def minimumSizeHint(self) -> QSize:
        return QSize(230, 38)

    def clean_mode(self) -> str:
        text = self.currentText()
        return text.split("  ", 1)[-1]

    def set_clean_mode(self, mode: str) -> None:
        mode = {"Economy": "Эконом", "Fast": "Быстрый", "Balanced": "Баланс", "Turbo": "Турбо", "Maximum": "Максимум"}.get(mode, mode)
        for row in range(self.count()):
            if self.itemText(row).split("  ", 1)[-1] == mode:
                self.setCurrentIndex(row)
                return


class TranslationMode(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(QLabel("Режим перевода", objectName="caption"))
        self.combo = ModeRequirementsCombo()
        layout.addWidget(self.combo)
