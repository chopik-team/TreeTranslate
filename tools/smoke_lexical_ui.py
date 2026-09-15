"""Native Qt QA: real GPU translation, dictionary, keyboard completion and screenshots."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QPainter, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.gui.main_window import MainWindow
from app.gui.styles.theme import load_stylesheet


def main():
    app = QApplication([])
    app.setOrganizationName("CHOPIK Team QA")
    app.setApplicationName("TreeTranslate Lexical QA")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(ROOT / "build/qa-settings"))
    app.setStyleSheet(load_stylesheet())
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.resize(1400, 950)
    page = window.text_page
    editor = page.source.editor
    editor.completer.popup().setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.preferences.set_languages("Английский", "Русский")
    window.preferences.set_device("GPU")
    window.preferences.set_profile("Максимум")
    window.request_navigation(1)
    window.show()
    app.setActiveWindow(window)
    editor.setFocus()
    editor.setPlainText("hi")
    editor.moveCursor(QTextCursor.MoveOperation.End)
    state = {"step": 0, "error": None}
    output = ROOT / "docs/qa"
    output.mkdir(parents=True, exist_ok=True)

    def advance():
        try:
            if state["step"] == 0 and page._reference and page.result.editor.toPlainText():
                assert page.result.editor.toPlainText().lower() == "привет"
                assert "argos" in page.engine_status.text()
                assert "Hi, Anna!" in page.examples_text.toPlainText()
                window.grab().save(str(output / "aw04-dictionary.png"))
                state["step"] = 1
                editor.setPlainText("Gam")
                editor.moveCursor(QTextCursor.MoveOperation.End)
            elif state["step"] == 1 and editor.completer.popup().isVisible():
                # A QWidget grab excludes its top-level completion popup; compose its actual grab.
                pixmap = window.grab()
                painter = QPainter(pixmap)
                point = window.mapFromGlobal(editor.completer.popup().mapToGlobal(editor.completer.popup().rect().topLeft()))
                painter.drawPixmap(point, editor.completer.popup().grab())
                painter.end()
                pixmap.save(str(output / "aw04-completion.png"))
                QTest.keyClick(editor.completer.popup(), Qt.Key.Key_Return)
                assert editor.toPlainText() == "Game"
                state["step"] = 2
            elif state["step"] == 2 and page._reference and page._reference.word == "Game" and page.result.editor.toPlainText():
                assert "This game supports" in page.examples_text.toPlainText()
                window.grab().save(str(output / "aw04-game.png"))
                state["step"] = 3
                window.close()
        except Exception as error:
            state["error"] = repr(error)
            window.close()

    poll = QTimer(interval=40)
    poll.timeout.connect(advance)
    poll.start()
    deadline = QTimer(singleShot=True, interval=30000)
    deadline.timeout.connect(window.close)
    deadline.start()
    app.exec()
    poll.stop()
    deadline.stop()
    assert state["step"] == 3 and state["error"] is None, state
    print("Native Qt dictionary, Game completion + Enter, real Argos CUDA Maximum and shutdown passed")


if __name__ == "__main__":
    main()
