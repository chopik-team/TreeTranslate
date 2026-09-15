import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QInputMethodEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.gui.widgets.assisted_text_edit import AssistedTextEdit
from app.services.lexical_assistance import Suggestion


def editor_with_popup(text="Gam", suggestions=None):
    app = QApplication.instance() or QApplication([])
    editor = AssistedTextEdit()
    editor.resize(600, 300)
    editor.show()
    editor.setFocus()
    editor.setPlainText(text)
    editor.moveCursor(QTextCursor.MoveOperation.End)
    app.processEvents()
    editor.show_suggestions(editor.suggestion_snapshot(), suggestions or (Suggestion("Game", "completion"), Suggestion("Games", "completion")))
    app.processEvents()
    assert editor.completer.popup().isVisible()
    return app, editor


def test_enter_accepts_first_without_newline_and_undo_restores_fragment():
    app, editor = editor_with_popup()
    QTest.keyClick(editor.completer.popup(), Qt.Key.Key_Return)
    assert editor.toPlainText() == "Game"
    editor.undo()
    assert editor.toPlainText() == "Gam"
    editor.close()


def test_enter_delivered_to_editor_accepts_completion():
    app, editor = editor_with_popup()
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == "Game"
    editor.close()


def test_mouse_click_accepts_clicked_variant():
    app, editor = editor_with_popup()
    popup = editor.completer.popup()
    index = popup.model().index(1, 0)
    QTest.mouseClick(popup.viewport(), Qt.MouseButton.LeftButton, pos=popup.visualRect(index).center())
    assert editor.toPlainText() == "Games"
    editor.close()


def test_hover_only_targets_visible_word_not_empty_editor_space():
    app, editor = editor_with_popup()
    editor.dismiss_suggestions()
    cursor = editor.textCursor()
    cursor.setPosition(0)
    point = editor.cursorRect(cursor).center() + QPoint(3, 0)
    assert editor.word_at_point(point).selectedText() == "Gam"
    assert editor.word_at_point(QPoint(400, 240)) is None
    editor.close()


def test_enter_always_uses_first_word_even_after_arrow_selection():
    app, editor = editor_with_popup()
    QTest.keyClick(editor.completer.popup(), Qt.Key.Key_Down)
    QTest.keyClick(editor.completer.popup(), Qt.Key.Key_Return)
    assert editor.toPlainText() == "Game"
    editor.close()


def test_number_key_accepts_matching_variant():
    app, editor = editor_with_popup()
    assert editor.completer.popup().model().index(0, 0).data().startswith("1   Game")
    assert editor.completer.popup().model().index(1, 0).data().startswith("2   Games")
    QTest.keyClick(editor.completer.popup(), Qt.Key.Key_2)
    assert editor.toPlainText() == "Games"
    editor.close()


def test_escape_preserves_input_and_enter_remains_newline():
    app, editor = editor_with_popup()
    snapshot = editor.suggestion_snapshot()
    QTest.keyClick(editor.completer.popup(), Qt.Key.Key_Escape)
    editor.show_suggestions(snapshot, (Suggestion("Game", "completion"),))
    assert not editor.completer.popup().isVisible()
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == "Gam\n"
    editor.close()


def test_shift_enter_never_accepts_completion():
    app, editor = editor_with_popup()
    QTest.keyClick(editor.completer.popup(), Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert editor.toPlainText() == "Gam\n"
    editor.close()


def test_unicode_cursor_and_suffix_are_preserved():
    app, editor = editor_with_popup("😀 Gam", (Suggestion("Game", "completion"),))
    QTest.keyClick(editor.completer.popup(), Qt.Key.Key_Return)
    assert editor.toPlainText() == "😀 Game"
    editor.setPlainText("😀 Gam, next")
    cursor = editor.textCursor()
    cursor.setPosition(6)  # Qt positions count UTF-16 code units, including emoji's surrogate pair.
    editor.setTextCursor(cursor)
    editor.show_suggestions(editor.suggestion_snapshot(), (Suggestion("Game", "completion"),))
    QTest.keyClick(editor.completer.popup(), Qt.Key.Key_Return)
    assert editor.toPlainText() == "😀 Game, next"
    editor.close()


def test_cursor_move_and_edit_invalidate_old_suggestion():
    app, editor = editor_with_popup()
    snapshot = editor.suggestion_snapshot()
    editor.insertPlainText("x")
    editor.show_suggestions(snapshot, (Suggestion("Game", "completion"),))
    assert not editor.completer.popup().isVisible()
    assert editor.toPlainText() == "Gamx"
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    assert editor.suggestion_snapshot() is None
    editor.close()


def test_selected_text_and_ime_composition_are_not_replaced():
    app, editor = editor_with_popup()
    editor.selectAll()
    assert editor.suggestion_snapshot() is None
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QApplication.sendEvent(editor, QInputMethodEvent("拼", []))
    assert editor.suggestion_snapshot() is None
    assert not editor.completer.popup().isVisible()
    assert editor.toPlainText() == "Gam"
    editor.close()
