"""Native UI smoke and screenshots for AW0.7.5 EN/RU lexical data."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from app.gui.main_window import MainWindow
from app.gui.styles.theme import load_stylesheet
from app.services.mock_translation_service import MockTranslationService


def main():
    app = QApplication([])
    app.setStyleSheet(load_stylesheet())
    window = MainWindow(translation_service=MockTranslationService())
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.resize(1400, 950)
    window.request_navigation(1)
    window.show()
    page = window.text_page
    output = ROOT / "docs" / "qa" / "aw075"
    output.mkdir(parents=True, exist_ok=True)
    state = {"step": 0, "error": None}
    window.preferences.set_languages("Английский", "Русский")
    page.source.editor.setPlainText("bank")

    def advance():
        try:
            reference = page._reference
            if state["step"] == 0 and reference and reference.word == "bank":
                assert len(reference.examples) >= 1
                assert sum(len(entry["senses"]) for entry in reference.entries) >= 2
                window.grab().save(str(output / "english-bank.png"))
                state["step"] = 1
                window.preferences.set_languages("Русский", "Английский")
                page.source.editor.setPlainText("двигателя")
            elif state["step"] == 1 and reference and reference.word == "двигателя":
                assert any(entry["headword"] == "двигатель" for entry in reference.entries)
                assert reference.examples
                window.grab().save(str(output / "russian-inflected-engine.png"))
                state["step"] = 2
                window.close()
        except Exception as error:
            state["error"] = repr(error)
            window.close()

    poll = QTimer(interval=40); poll.timeout.connect(advance); poll.start()
    deadline = QTimer(singleShot=True, interval=10000); deadline.timeout.connect(window.close); deadline.start()
    app.exec()
    assert state == {"step": 2, "error": None}, state
    print("AW0.7.5 English/Russian dictionary UI smoke passed")


if __name__ == "__main__":
    main()
