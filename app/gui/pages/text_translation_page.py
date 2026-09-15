from html import escape

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QApplication, QTextBrowser, QVBoxLayout, QWidget,
)

from app.config.paths import icon_path
from app.gui.styles.theme import color
from app.gui.widgets.acceleration_selector import AccelerationSelector
from app.gui.widgets.language_selector import LanguageSelector
from app.gui.widgets.translation_mode import TranslationMode
from app.gui.widgets.assisted_text_edit import AssistedTextEdit
from app.services.lexical_assistance import language_code, lookup_key
from app.services.lexical_worker import LexicalWorker


class TextTranslationPage(QWidget):
    translate_requested = Signal(str)
    variant_chosen = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._translate_timer = QTimer(self, singleShot=True, interval=420)
        self._translate_timer.timeout.connect(self._request_translation)
        self._assist_timer = QTimer(self, singleShot=True, interval=160)
        self._assist_timer.timeout.connect(self._request_assistance)
        self._lexical = LexicalWorker(self)
        self._lexical.ready.connect(self._assistance_ready)
        self._assist_id = 0
        self._hover_id = 0
        self._reference = None
        self._resolved_source = None
        self._variants = []
        self._related = []
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        settings = QFrame(objectName="panel")
        settings_layout = QHBoxLayout(settings)
        settings_layout.setContentsMargins(16, 10, 16, 10)
        self.languages = LanguageSelector()
        self.mode = TranslationMode()
        self.acceleration = AccelerationSelector()
        settings_layout.addWidget(self.languages, 3)
        settings_layout.addSpacing(18)
        settings_layout.addWidget(self.mode, 2)
        settings_layout.addSpacing(18)
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
        self.engine_status = QLabel("", objectName="secondary")
        self.engine_status.setWordWrap(True)
        self.engine_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status.addWidget(self.engine_status, 1)
        root.addLayout(status)
        self.reference_area = self._build_reference_area()
        self.reference_area.hide()
        root.addWidget(self.reference_area, 4)
        self.source.editor.textChanged.connect(self._source_changed)
        self.source.editor.cursorPositionChanged.connect(self._schedule_assistance)
        self.source.editor.selectionChanged.connect(self._schedule_assistance)
        for editor in (self.source.editor, self.result.editor):
            editor.word_hovered.connect(lambda word, point, editor=editor: self._hover_word(editor, word, point))
        self.languages.source_combo.currentTextChanged.connect(self.refresh_assistance)
        self.languages.target_combo.currentTextChanged.connect(self.refresh_assistance)

    def _editor(self, title: str, placeholder: str, read_only: bool = False) -> QWidget:
        panel = QFrame(objectName="textEditorPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        header.addWidget(QLabel(title, objectName="heading"))
        header.addStretch()
        editor = AssistedTextEdit()
        editor.setAccessibleName(title)
        editor.setPlaceholderText(placeholder)
        editor.setReadOnly(read_only)
        if read_only:
            editor.setToolTip("Наведите курсор на слово, чтобы увидеть словарное значение.")
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

    def _examples_panel(self) -> QFrame:
        panel = QFrame(objectName="referencePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.addWidget(QLabel("Примеры использования", objectName="heading"))
        self.examples_text = self._reference_browser()
        layout.addWidget(self.examples_text)
        return panel

    def _dictionary_panel(self) -> QFrame:
        panel = QFrame(objectName="referencePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.addWidget(QLabel("Словарь", objectName="heading"))
        self.dictionary_text = self._reference_browser()
        self.dictionary_text.anchorClicked.connect(self._reference_link)
        layout.addWidget(self.dictionary_text)
        return panel

    @staticmethod
    def _reference_browser():
        browser = QTextBrowser(objectName="referenceText")
        browser.setOpenLinks(False)
        browser.setOpenExternalLinks(False)
        browser.setMinimumHeight(160)
        browser.document().setDefaultStyleSheet(
            "p { margin: 8px 0; } a { color: " + color("accent_green")
            + "; } small { color: " + color("text_secondary") + "; }")
        return browser

    def _source_language(self):
        value = language_code(self.languages.source_combo.currentText())
        return self._resolved_source if value == "auto" and self._resolved_source else value

    def refresh_assistance(self, *_args):
        self._resolved_source = None
        self._schedule_assistance()

    def set_resolved_languages(self, source, target):
        self._resolved_source = source
        self._schedule_assistance()

    def _schedule_assistance(self):
        self._assist_id += 1
        self._hover_id += 1
        self.source.editor.dismiss_suggestions()
        self._reference = None
        if self.source.editor.toPlainText().strip():
            if not self._reference_is_allowed():
                self.reference_area.hide()
            elif not self.reference_area.isHidden():
                self.examples_text.setPlainText("Обновляем примеры…")
                self.dictionary_text.setPlainText("Поиск в локальном словаре…")
            self._assist_timer.start()
        else:
            self.reference_area.hide()
            self._assist_timer.stop()

    def _request_assistance(self, word=None):
        editor = self.source.editor
        token = editor.token_cursor()
        whole = editor.toPlainText().strip()
        selected = editor.textCursor().selectedText().strip()
        term = word or selected or (whole if len(whole) <= 160 and len(whole.split()) <= 3 else token.selectedText() if token else "")
        if not term:
            return
        # Strip sentence punctuation for a one-word lookup, preserving accents and apostrophes.
        term = term.strip(" .,!?;:。！？\"“”()[]")
        snapshot = editor.suggestion_snapshot()
        self._lexical.submit(("reference", self._assist_id, snapshot), term, self._source_language(),
                             self.languages.target_combo.currentText(), spelling=bool(snapshot),
                             suggestion_word=snapshot[3] if snapshot else None)

    def _hover_word(self, editor, word, point):
        self._hover_id += 1
        source, target = self._source_language(), self.languages.target_combo.currentText()
        if editor is self.result.editor:
            source, target = target, source
        self._lexical.submit(("hover", self._hover_id, editor, point), word, source, target)

    def _assistance_ready(self, result):
        ticket, reference, suggestions = result
        if reference is None:
            return
        if ticket[0] == "hover":
            if ticket[1] == self._hover_id:
                ticket[2].show_word_tooltip(reference.word, ticket[3], reference)
        elif ticket[1] == self._assist_id:
            if ticket[0] == "reference":
                if self._reference_is_allowed():
                    self._render_reference(reference)
                else:
                    self.reference_area.hide()
                self.source.editor.show_suggestions(ticket[2], suggestions)

    def _reference_is_allowed(self) -> bool:
        text = self.source.editor.toPlainText().strip()
        selected = self.source.editor.textCursor().selectedText().strip()
        if selected:
            return len(selected) <= 160 and len(selected.split()) == 1
        return bool(text) and len(text) <= 160 and len(text.split()) == 1

    def _render_reference(self, reference):
        self._reference = reference
        self._variants, self._related = [], []
        usage = reference.usage
        title = f"<h3>{escape(reference.word)}</h3>"
        if usage:
            examples = title + f"<p>{escape(usage['note'])}</p>"
            for source, target, context in usage["examples"]:
                examples += f"<p><small>{escape(context)}</small><br><b>{escape(source)}</b><br>{escape(target)}</p>"
            examples += "<p><small>TreeTranslate · учебные примеры · CC0</small></p>"
        else:
            examples = title + "<p>Для этого слова пока нет учебных примеров.</p><p>Выделите слово в исходном тексте, чтобы посмотреть его значения.</p>"
        self.examples_text.setHtml(examples)
        dictionary = title
        curated_values = set()
        if usage:
            action = "Нажмите вариант, чтобы вставить его в перевод." if self._can_use_variant() else "Нажмите вариант, чтобы скопировать его."
            dictionary += f"<p><small>{action}</small></p>"
            for value, context in usage["variants"]:
                curated_values.add(lookup_key(value))
                dictionary += self._variant_html(value, context)
            self._related = usage.get("related", [])
        pos_labels = {"n":"сущ.", "v":"гл.", "adj":"прил.", "adv":"нареч.", "interjection":"междометие", "pn":"имя собственное"}
        for entry in reference.entries:
            pronunciation = " · ".join(entry["pronunciation"][:2])
            pos = ", ".join(pos_labels.get(p, p) for p in entry["pos"])
            dictionary += f"<p><b>{escape(entry['headword'])}</b> {escape(pronunciation)} <small>{escape(pos)}</small></p>"
            for sense in entry["senses"][:10]:
                definition = "; ".join(sense["definitions"][:2])
                values = [value for value in sense["translations"][:6] if lookup_key(value) not in curated_values]
                if values:
                    links = []
                    for value in values:
                        self._variants.append(value.replace("\u0301", ""))
                        action = "use" if self._can_use_variant() else "copy"
                        hint = "Вставить в перевод" if action == "use" else "Скопировать вариант"
                        links.append(f'<a href="{action}:{len(self._variants)-1}" title="{hint}">{escape(value)}</a>')
                    dictionary += "<p>" + " · ".join(links) + f"<br><small>{escape(definition)}</small></p>"
        if reference.entries:
            dictionary += "<p><small>FreeDict / WikDict / Wiktionary · CC BY-SA 3.0<br>Определения приведены на языке исходного словаря.</small></p>"
        if self._related:
            dictionary += "<p><b>Связанные слова</b><br>" + " · ".join(f'<a href="word:{i}">{escape(word)}</a>' for i, word in enumerate(self._related)) + "</p>"
        if reference.notice:
            dictionary += f"<p>{escape(reference.notice)}</p>"
        self.dictionary_text.setHtml(dictionary)
        self.reference_area.show()

    def _can_use_variant(self):
        return self._reference is not None and lookup_key(self.source.editor.toPlainText().strip(" .,!?;:。！？\"“”()[]")) == lookup_key(self._reference.word)

    def _variant_html(self, value, context):
        self._variants.append(value.replace("\u0301", ""))
        index = len(self._variants) - 1
        action = "use" if self._can_use_variant() else "copy"
        hint = "Вставить в перевод" if action == "use" else "Скопировать вариант"
        return f'<p><a href="{action}:{index}" title="{hint}"><b>{escape(value)}</b></a><br><small>{escape(context)}</small></p>'

    def _reference_link(self, url):
        action, _, number = url.toString().partition(":")
        if not number.isdigit():
            return
        index = int(number)
        if action == "word" and index < len(self._related):
            self._assist_id += 1
            self._request_assistance(self._related[index])
        elif action in {"use", "copy"} and index < len(self._variants):
            value = self._variants[index]
            if action == "use" and self._can_use_variant():
                self.variant_chosen.emit(value)
            else:
                QApplication.clipboard().setText(value)

    def shutdown(self):
        self._assist_timer.stop()
        self._lexical.shutdown()

    def _source_changed(self) -> None:
        text = self.source.editor.toPlainText()
        self._resolved_source = None
        self._schedule_assistance()
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

    def set_result(self, text: str) -> None:
        self.result.editor.setPlainText(text)

    def set_status(self, text: str) -> None:
        self.engine_status.setText(text)
