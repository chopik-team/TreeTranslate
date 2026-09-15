import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from threading import Event
from types import SimpleNamespace

from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.gui.pages.text_translation_page import TextTranslationPage
from app.gui.main_window import MainWindow
from app.services.lexical_assistance import Reference
from app.services.lexical_worker import LexicalWorker
from app.services.mock_translation_service import MockTranslationService


def wait_for(predicate, timeout=2000):
    for _ in range(timeout // 10):
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


def test_reference_follows_word_and_clears_immediately():
    app = QApplication.instance() or QApplication([])
    page = TextTranslationPage()
    page.languages.source_combo.setCurrentText("Английский")
    page.languages.target_combo.setCurrentText("Русский")
    page.source.editor.setPlainText("hi")
    wait_for(lambda: page._reference is not None)
    assert not page.reference_area.isHidden()
    assert "Hi, Anna!" in page.examples_text.toPlainText()
    assert "Нажмите вариант" in page.dictionary_text.toPlainText()
    page.source.editor.setPlainText("bank")
    wait_for(lambda: page._reference is not None and page._reference.word == "bank")
    assert "river bank" in page.examples_text.toPlainText()
    assert "Hi, Anna!" not in page.examples_text.toPlainText()
    page.source.editor.clear()
    assert page._reference is None
    assert page.reference_area.isHidden()
    page.shutdown()
    page.close()


def test_selection_in_paragraph_looks_up_word_without_replacing_sentence():
    app = QApplication.instance() or QApplication([])
    page = TextTranslationPage()
    page.languages.source_combo.setCurrentText("Английский")
    page.languages.target_combo.setCurrentText("Русский")
    source = "We sat on the river bank."
    page.source.editor.setPlainText(source)
    cursor = page.source.editor.textCursor()
    start = source.index("bank")
    cursor.setPosition(start)
    cursor.setPosition(start + 4, QTextCursor.MoveMode.KeepAnchor)
    page.source.editor.setTextCursor(cursor)
    wait_for(lambda: page._reference is not None and page._reference.word == "bank")
    page.set_result("Мы сидели на берегу реки.")
    assert not page._can_use_variant()
    page._reference_link(QUrl("copy:0"))
    assert QApplication.clipboard().text() == "банк"
    assert page.source.editor.toPlainText() == source
    assert page.result.editor.toPlainText() == "Мы сидели на берегу реки."
    page.shutdown()
    page.close()


def test_language_change_discards_stale_reference_and_result():
    app = QApplication.instance() or QApplication([])
    page = TextTranslationPage()
    page.languages.source_combo.setCurrentText("Английский")
    page.languages.target_combo.setCurrentText("Русский")
    page.source.editor.setPlainText("hi")
    ticket = ("reference", page._assist_id, None)
    page.languages.target_combo.setCurrentText("Китайский")
    page._assistance_ready((ticket, Reference("hi", "en", "ru"), ()))
    assert page._reference is None
    wait_for(lambda: page._reference is not None)
    assert page._reference.target == "zh"
    assert "привет" not in page.dictionary_text.toPlainText()
    page.shutdown()
    page.close()


def test_reference_panels_hide_for_long_text_but_suggestions_remain_available():
    app = QApplication.instance() or QApplication([])
    page = TextTranslationPage()
    page.show()
    page.source.editor.setFocus()
    page.languages.source_combo.setCurrentText("Английский")
    page.languages.target_combo.setCurrentText("Русский")
    page.source.editor.setPlainText("Gam " + "word " * 100)
    cursor = page.source.editor.textCursor()
    cursor.setPosition(3)
    page.source.editor.setTextCursor(cursor)
    wait_for(lambda: page.source.editor.completer.popup().isVisible())
    assert page.reference_area.isHidden()
    page.shutdown()
    page.close()


def test_reference_panels_hide_as_soon_as_input_contains_multiple_words():
    app = QApplication.instance() or QApplication([])
    page = TextTranslationPage()
    page.languages.source_combo.setCurrentText("Английский")
    page.languages.target_combo.setCurrentText("Русский")
    page.source.editor.setPlainText("hello")
    wait_for(lambda: not page.reference_area.isHidden())

    page.source.editor.setPlainText("hello world")
    assert page.reference_area.isHidden()
    QTest.qWait(250)
    QApplication.processEvents()
    assert page.reference_area.isHidden()
    page.shutdown()
    page.close()


def test_selecting_variant_cancels_inflight_translation_and_keeps_chosen_text():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(translation_service=MockTranslationService())
    page = window.text_page
    window.preferences.set_languages("Английский", "Русский")
    page.source.editor.setPlainText("hi")
    wait_for(lambda: page._reference is not None)
    old_request = window.translation._text_request_id
    page._reference_link(QUrl("use:0"))
    assert page.result.editor.toPlainText() == "привет"
    assert page.engine_status.text() == "Выбран словарный вариант"
    window.translation._text_completed(SimpleNamespace(request_id=str(old_request), translated_text="STALE"))
    assert page.result.editor.toPlainText() == "привет"
    window.close()


def test_worker_coalesces_pending_requests_and_closes_cleanly():
    app = QApplication.instance() or QApplication([])
    started, release = Event(), Event()
    class Lexicon:
        calls = []
        def reference(self, word, source, target):
            self.calls.append(word)
            if word == "first":
                started.set()
                release.wait(2)
            return Reference(word, source, target)
    lexicon = Lexicon()
    worker = LexicalWorker(lexicon=lexicon)
    results = []
    worker.ready.connect(results.append)
    worker.submit(1, "first", "en", "ru")
    assert started.wait(1)
    worker.submit(2, "discard", "en", "ru")
    worker.submit(3, "latest", "en", "ru")
    release.set()
    wait_for(lambda: len(results) == 2)
    worker.shutdown()
    assert lexicon.calls == ["first", "latest"]
    assert [row[0] for row in results] == [1, 3]
