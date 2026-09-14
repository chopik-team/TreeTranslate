from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.config.paths import icon_path
from app.gui.widgets.acceleration_selector import AccelerationSelector
from app.gui.widgets.language_selector import LanguageSelector


class TextTranslationPage(QWidget):
    translate_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._translate_timer = QTimer(self, singleShot=True, interval=420)
        self._translate_timer.timeout.connect(self._request_translation)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        settings = QFrame(objectName="panel")
        settings_layout = QHBoxLayout(settings)
        settings_layout.setContentsMargins(16, 10, 16, 10)
        self.languages = LanguageSelector()
        self.acceleration = AccelerationSelector()
        settings_layout.addWidget(self.languages, 3)
        settings_layout.addSpacing(24)
        settings_layout.addWidget(self.acceleration, 2)
        root.addWidget(settings)
        editors = QHBoxLayout()
        editors.setSpacing(10)
        self.source = self._editor("Исходный текст", "Введите или вставьте текст для перевода…")
        self.result = self._editor("Перевод", "Перевод появится автоматически", read_only=True)
        editors.addWidget(self.source, 1)
        editors.addWidget(self.result, 1)
        root.addLayout(editors, 3)
        status = QHBoxLayout()
        self.counter = QLabel("0 символов", objectName="secondary")
        status.addWidget(self.counter)
        status.addStretch()
        root.addLayout(status)
        self.reference_area = self._build_reference_area()
        self.reference_area.hide()
        root.addWidget(self.reference_area, 4)
        self.source.editor.textChanged.connect(self._source_changed)

    def _editor(self, title: str, placeholder: str, read_only: bool = False) -> QWidget:
        panel = QFrame(objectName="textEditorPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        header.addWidget(QLabel(title, objectName="heading"))
        header.addStretch()
        editor = QTextEdit()
        editor.setPlaceholderText(placeholder)
        editor.setReadOnly(read_only)
        editor.setMinimumHeight(170)
        panel.editor = editor
        if not read_only:
            action = QPushButton(QIcon(icon_path("close")), "", objectName="iconButton")
            action.setFixedSize(30, 30)
            action.setToolTip("Очистить текст")
            action.clicked.connect(editor.clear)
            header.addWidget(action)
        layout.addLayout(header)
        layout.addWidget(editor)
        return panel

    def _build_reference_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        columns = QHBoxLayout(content)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(10)
        self.examples_panel = self._examples_panel()
        self.dictionary_panel = self._dictionary_panel()
        columns.addWidget(self.examples_panel, 3)
        columns.addWidget(self.dictionary_panel, 2)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _examples_panel() -> QFrame:
        panel = QFrame(objectName="referencePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.addWidget(QLabel("Примеры использования", objectName="heading"))
        chips = QHBoxLayout()
        for word in ("все", "hi", "hello", "salutation", "hey", "howdy"):
            chip = QLabel(word, objectName="chip")
            chips.addWidget(chip)
        chips.addStretch()
        layout.addLayout(chips)
        examples = (
            ("Привет, милый. Я сейчас стою в Пантеоне.", "Hi, honey. I'm standing in the Pantheon."),
            ("Привет! — улыбнулся Джейми. — Я вернулся.", "Hello! Jamie grinned. I'm back."),
            ("Всем привет с Вишнёвого фестиваля!", "Salutations from the Cherry Festival!"),
        )
        for source, translated in examples:
            card = QFrame(objectName="exampleCard")
            box = QVBoxLayout(card)
            box.setContentsMargins(12, 8, 12, 8)
            box.addWidget(QLabel(source))
            box.addWidget(QLabel(translated, objectName="secondary"))
            layout.addWidget(card)
        layout.addStretch()
        return panel

    @staticmethod
    def _dictionary_panel() -> QFrame:
        panel = QFrame(objectName="referencePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.addWidget(QLabel("Словарь", objectName="heading"))
        layout.addWidget(QLabel("привет   сущ., междометие", objectName="dictionaryWord"))
        for number, value in enumerate(("hi · hello · salutation", "hey", "regards"), start=1):
            layout.addWidget(QLabel(f"{number}   {value}", objectName="definition"))
        layout.addSpacing(8)
        layout.addWidget(QLabel("Связанные слова", objectName="heading"))
        layout.addWidget(QLabel("Синонимы", objectName="caption"))
        related = QLabel("здравствуйте   ·   добрый день   ·   здорово   ·   салют   ·   поклон   ·   чао", objectName="relatedWords")
        related.setWordWrap(True)
        layout.addWidget(related)
        layout.addStretch()
        return panel

    def _source_changed(self) -> None:
        text = self.source.editor.toPlainText()
        self.counter.setText(f"{len(text)} символов")
        if not text.strip():
            self._translate_timer.stop()
            self.result.editor.clear()
            self.reference_area.hide()
            return
        self._translate_timer.start()

    def _request_translation(self) -> None:
        text = self.source.editor.toPlainText()
        if not text.strip():
            self.reference_area.hide()
            return
        self.translate_requested.emit(text)
        self.reference_area.show()

    def set_result(self, text: str) -> None:
        self.result.editor.setPlainText(text)
