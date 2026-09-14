from PySide6.QtCore import QItemSelectionModel, QSize, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget


MODE_REQUIREMENTS = (
    ("🍂  Эконом", "минимум нагрузки", "~10–20 слов/мин", "8 ГБ RAM, CPU"),
    ("🚶  Быстрый", "скорость", "~30–50 слов/мин", "16 ГБ RAM"),
    ("🚙  Баланс", "скорость / качество", "~50–100 слов/мин", "16 ГБ + GPU желательно"),
    ("⚡  Турбо", "максимальная скорость", "~100–200+ слов/мин", "32 ГБ + GPU"),
    ("🚀  Максимум", "всё доступное железо", "зависит от GPU", "32 ГБ+ / мощная GPU"),
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
        self._model.setHorizontalHeaderLabels(["Режим", "Приоритет", "Условная скорость", "Требования"])
        rows = list(MODE_REQUIREMENTS)
        if include_automatic:
            rows.insert(0, ("Автоматический", "подбор системой", "зависит от устройства", "определяются автоматически"))
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
