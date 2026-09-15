"""Existing QTextEdit extended with cursor-aware, explicitly accepted suggestions."""
from html import escape

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QStandardItem, QStandardItemModel, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QCompleter, QTextEdit, QToolTip

from app.gui.styles.theme import color


class AssistedTextEdit(QTextEdit):
    word_hovered = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setMouseTracking(True)
        self._snapshot = None
        self._suppress = False
        self._preedit = False
        self._dismissed = None
        self._completion_model = QStandardItemModel(self)
        self.completer = QCompleter(self._completion_model, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.completer.setMaxVisibleItems(9)
        self.completer.popup().setObjectName("wordSuggestions")
        self.completer.popup().setAccessibleName("Подсказки ввода")
        self.completer.popup().setMinimumWidth(280)
        self.completer.popup().installEventFilter(self)
        self.completer.activated["QModelIndex"].connect(self._accept)
        self.textChanged.connect(self.dismiss_suggestions)
        self.cursorPositionChanged.connect(self.dismiss_suggestions)
        self.verticalScrollBar().valueChanged.connect(self.dismiss_suggestions)
        self.setToolTip(
            "Дополнение и исправление слова: 1–9 — выбрать вариант, Enter — принять первый, "
            "Esc — закрыть.\nShift+Enter — новая строка. Выделите слово для словаря."
        )

    def token_cursor(self, cursor=None):
        cursor = QTextCursor(cursor or self.textCursor())
        if not cursor.hasSelection():
            original = QTextCursor(cursor)
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            if not any(char.isalpha() for char in cursor.selectedText()) and original.position() > 0:
                original.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
                original.select(QTextCursor.SelectionType.WordUnderCursor)
                if any(char.isalpha() for char in original.selectedText()):
                    cursor = original
        word = cursor.selectedText()
        if not word or len(word) > 160 or any(char.isspace() for char in word):
            return None
        return cursor

    def suggestion_snapshot(self):
        cursor = self.textCursor()
        token = self.token_cursor()
        if self._preedit or cursor.hasSelection() or token is None or cursor.position() != token.selectionEnd():
            return None
        return self.document().revision(), token.selectionStart(), token.selectionEnd(), token.selectedText()

    def dismiss_suggestions(self):
        self.completer.popup().hide()
        self._snapshot = None
        self.setExtraSelections([])

    def show_suggestions(self, snapshot, suggestions):
        if self._suppress or not self.hasFocus() or not suggestions or snapshot is None:
            return
        if snapshot != self.suggestion_snapshot() or snapshot == self._dismissed:
            return
        self._snapshot = snapshot
        self._completion_model.clear()
        for number, suggestion in enumerate(suggestions[:9], start=1):
            label = "Дополнить" if suggestion.kind == "completion" else "Исправить"
            item = QStandardItem(f"{number}   {suggestion.word}    {label}")
            item.setData(suggestion.word, Qt.ItemDataRole.UserRole)
            item.setToolTip(
                f"{label} слово. Нажмите {number}, чтобы вставить этот вариант; "
                "Enter вставляет первый вариант."
            )
            self._completion_model.appendRow(item)
        self.completer.setCompletionPrefix("")
        rect = self.cursorRect()
        start = self.textCursor()
        start.setPosition(snapshot[1])
        rect.moveLeft(self.cursorRect(start).left())
        rect.translate(self.viewport().pos())
        rect.translate(0, 5)
        rect.setWidth(max(280, self.completer.popup().sizeHintForColumn(0) + 24))
        self.completer.complete(rect)
        self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
        if any(s.kind == "spelling" for s in suggestions) and suggestions[0].kind == "spelling":
            selection = QTextEdit.ExtraSelection()
            selection.cursor = self.token_cursor()
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
            selection.format.setUnderlineColor(QColor(color("definition")))
            self.setExtraSelections([selection])

    def _accept(self, index=None):
        snapshot = self._snapshot
        if snapshot is None or snapshot != self.suggestion_snapshot():
            self.dismiss_suggestions()
            return
        index = index if index is not None and index.isValid() else self.completer.popup().currentIndex()
        word = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(word, str):
            return
        self._suppress = True
        self.dismiss_suggestions()
        cursor = self.textCursor()
        cursor.setPosition(snapshot[1])
        cursor.setPosition(snapshot[2], QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        cursor.insertText(word)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self._dismissed = self.suggestion_snapshot()
        self._suppress = False

    def _popup_key(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._dismissed = self.suggestion_snapshot()
            self.dismiss_suggestions()
            return True
        digit = event.text()
        if digit and event.modifiers() in {
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.KeypadModifier,
        } and digit in "123456789":
            row = int(digit) - 1
            if row < self._completion_model.rowCount():
                self._accept(self._completion_model.index(row, 0))
            return True
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            if event.modifiers() == Qt.KeyboardModifier.NoModifier:
                self._accept(self._completion_model.index(0, 0))
            else:
                self.dismiss_suggestions()
                super().keyPressEvent(event)
            return True
        if event.key() == Qt.Key.Key_Tab and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self._accept()
            return True
        return False

    def keyPressEvent(self, event):
        if self.completer.popup().isVisible() and self._popup_key(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.completer.popup() and event.type() == QEvent.Type.KeyPress and self._popup_key(event):
            return True
        return super().eventFilter(watched, event)

    def inputMethodEvent(self, event):
        self._preedit = bool(event.preeditString())
        self.dismiss_suggestions()
        super().inputMethodEvent(event)

    def focusOutEvent(self, event):
        self.dismiss_suggestions()
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self.dismiss_suggestions()
        super().hideEvent(event)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.ToolTip:
            cursor = self.word_at_point(event.pos())
            if cursor and cursor.selectedText().strip():
                self.word_hovered.emit(cursor.selectedText(), event.globalPos())
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def word_at_point(self, point):
        cursor = self.token_cursor(self.cursorForPosition(point))
        if cursor is None:
            return None
        start, end = QTextCursor(cursor), QTextCursor(cursor)
        start.setPosition(cursor.selectionStart())
        end.setPosition(cursor.selectionEnd())
        bounds = self.cursorRect(start).united(self.cursorRect(end)).adjusted(-1, 0, 1, 0)
        # cursorForPosition returns the nearest cursor even over empty editor space.
        return cursor if bounds.contains(point) else None

    def show_word_tooltip(self, word, point, reference):
        if QCursor.pos() != point:
            return
        current = self.word_at_point(self.viewport().mapFromGlobal(point))
        if current is None or current.selectedText() != word or not self.isVisible():
            return
        if reference.usage:
            body = reference.usage["note"]
        else:
            values = [value for entry in reference.entries for sense in entry["senses"] for value in sense["translations"]]
            body = " · ".join(dict.fromkeys(values))[:400] or reference.notice
        QToolTip.showText(point, f"<b>{escape(word)}</b><br>{escape(body)}", self, self.viewport().rect())
