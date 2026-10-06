from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.gui.widgets.language_combo import LanguageComboBox
from app.engine.languages import AUTOMATIC_LANGUAGE, RELEASE_LANGUAGE_LABELS

from app.localization.widgets import QComboBox, QLabel, QPushButton


class LanguageSelector(QWidget):
    languages_swapped = Signal(str, str)
    AUTOMATIC = AUTOMATIC_LANGUAGE
    LANGUAGES = RELEASE_LANGUAGE_LABELS

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._syncing = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.source = self._combo("Исходный язык", [self.AUTOMATIC, *self.LANGUAGES])
        self.swap_button = QPushButton("⇄", objectName="languageSwap")
        self.swap_button.setToolTip("Поменять языки местами")
        self.swap_button.setAccessibleName("Поменять языки местами")
        self.swap_button.setFixedSize(42, 42)
        # LanguageResolver rejects an automatic target, so it must never be a
        # release-facing choice.
        self.target = self._combo("Язык перевода", list(self.LANGUAGES))
        self.target.combo.setCurrentText("Русский")
        layout.addWidget(self.source, 1)
        layout.addWidget(self.swap_button, alignment=Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(self.target, 1)
        self.source.combo.currentTextChanged.connect(lambda: self._keep_languages_distinct("source"))
        self.target.combo.currentTextChanged.connect(lambda: self._keep_languages_distinct("target"))
        self.swap_button.clicked.connect(self.swap_languages)

    def swap_languages(self) -> None:
        source = self.source_combo.currentText()
        target = self.target_combo.currentText()
        if source == self.AUTOMATIC:
            return
        self._syncing = True
        self.source_combo.blockSignals(True)
        self.target_combo.blockSignals(True)
        self.source_combo.setCurrentText(target)
        self.target_combo.setCurrentText(source)
        self.source_combo.blockSignals(False)
        self.target_combo.blockSignals(False)
        self._syncing = False
        self.languages_swapped.emit(target, source)

    def _keep_languages_distinct(self, changed: str) -> None:
        if self._syncing:
            return
        source = self.source.combo.currentText()
        target = self.target.combo.currentText()
        if source == self.AUTOMATIC or source != target:
            return
        self._syncing = True
        if changed == "target":
            self.source.combo.setCurrentText(self.AUTOMATIC)
        else:
            fallback = "Русский" if source != "Русский" else "Английский"
            self.target.combo.setCurrentText(fallback)
        self._syncing = False

    @staticmethod
    def _combo(label: str, items: list[str]) -> QWidget:
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(5)
        box.addWidget(QLabel(label, objectName="caption"))
        combo = LanguageComboBox(items)
        widget.combo = combo
        box.addWidget(combo)
        return widget

    @property
    def source_combo(self) -> QComboBox:
        return self.source.combo

    @property
    def target_combo(self) -> QComboBox:
        return self.target.combo
