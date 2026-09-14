from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class LanguageSelector(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.source = self._combo("Исходный язык", ["Определить автоматически", "Китайский", "Английский", "Немецкий", "Японский"])
        arrow = QLabel("→")
        arrow.setStyleSheet("font-size: 22px; color: #718078")
        self.target = self._combo("Язык перевода", ["Русский", "Английский", "Немецкий", "Испанский", "Французский"])
        layout.addWidget(self.source, 1)
        layout.addWidget(arrow)
        layout.addWidget(self.target, 1)

    @staticmethod
    def _combo(label: str, items: list[str]) -> QWidget:
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(5)
        box.addWidget(QLabel(label, objectName="caption"))
        combo = QComboBox()
        combo.addItems(items)
        widget.combo = combo
        box.addWidget(combo)
        return widget

    @property
    def source_combo(self) -> QComboBox:
        return self.source.combo

    @property
    def target_combo(self) -> QComboBox:
        return self.target.combo
