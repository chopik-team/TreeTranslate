import os
from dataclasses import replace
from threading import Event, get_ident
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.config.settings import PerformanceSettings
from app.engine.types import TranslationResult
from app.gui.main_window import MainWindow
from app.services.hybrid_translation_service import HybridTranslationService


def wait_for(predicate, timeout=3000):
    deadline = monotonic() + timeout / 1000
    while not predicate() and monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


class SlowEngine:
    def __init__(self):
        self.entered, self.release = Event(), Event()
        self.calls = []
        self.threads = []
        self.closed = False

    def translate(self, request, cancelled):
        self.calls.append(request)
        self.threads.append(get_ident())
        if len(self.calls) == 1:
            self.entered.set()
            assert self.release.wait(5)
        return TranslationResult(request.text.upper(), request.source_language, request.target_language,
                                 "fake", "cpu", 1, "test", False, request.request_id)

    def shutdown(self):
        self.closed = True
        self.close_thread = get_ident()


def test_service_coalesces_pending_requests_and_emits_on_gui_thread():
    app = QApplication.instance() or QApplication([])
    engine = SlowEngine()
    service = HybridTranslationService(engine=engine)
    results, busy = [], []
    service.text_completed.connect(lambda r: results.append((r, get_ident())))
    service.text_busy_changed.connect(busy.append)
    policy = PerformanceSettings(device="CPU")
    service.submit_text("one", "en", "ru", policy, "1")
    assert engine.entered.wait(2)
    for i in range(2, 20):
        service.submit_text(str(i), "en", "ru", policy, str(i))
    assert len(engine.calls) == 1
    engine.release.set()
    wait_for(lambda: not service.text_busy)
    assert [r.request_id for r in engine.calls] == ["1", "19"]
    assert [result.request_id for result, _ in results] == ["19"]
    assert all(thread != get_ident() for thread in engine.threads)
    assert results[0][1] == get_ident()
    assert busy == [True, False]
    service.shutdown()
    assert engine.closed
    assert engine.close_thread == engine.threads[0]


def test_edit_clear_and_cancel_hold_session_until_native_call_finishes():
    app = QApplication.instance() or QApplication([])
    engine = SlowEngine()
    window = MainWindow(translation_service=HybridTranslationService(engine=engine))
    window.text_page.source.editor.setPlainText("first")
    window.translation.translate_text("first")
    window.text_page._translate_timer.stop()
    assert engine.entered.wait(2)
    assert window.sessions.is_active("text")
    window.text_page.source.editor.clear()
    window.translation.cancel_text_requests()
    window.translation._start_translation()
    assert not window.sessions.is_active("file")
    assert window.sessions.is_active("text")
    engine.release.set()
    wait_for(lambda: not window.sessions.is_active("text"))
    assert window.text_page.result.editor.toPlainText() == ""
    window.translation._start_translation()
    assert window.sessions.is_active("file")
    window.close()


def test_new_language_invalidates_in_flight_result_and_retranslates():
    app = QApplication.instance() or QApplication([])
    engine = SlowEngine()
    window = MainWindow(translation_service=HybridTranslationService(engine=engine))
    window.preferences.set_languages("Английский", "Русский")
    window.text_page.source.editor.setPlainText("sample")
    window.translation.translate_text("sample")
    window.text_page._translate_timer.stop()
    assert engine.entered.wait(2)
    window.preferences.set_languages("Английский", "Китайский")
    engine.release.set()
    wait_for(lambda: len(engine.calls) == 2 and not window.translation_service.text_busy)
    assert engine.calls[-1].target_language == "Китайский"
    assert window.text_page.result.editor.toPlainText() == "SAMPLE"
    window.close()


def test_debounce_does_not_block_event_loop():
    app = QApplication.instance() or QApplication([])
    engine = SlowEngine()
    window = MainWindow(translation_service=HybridTranslationService(engine=engine))
    for text in ["H", "He", "Hel", "Hello"]:
        window.text_page.source.editor.setPlainText(text)
    wait_for(lambda: engine.entered.is_set())
    assert [r.text for r in engine.calls] == ["Hello"]
    # GUI events still run while native work is waiting.
    window.text_page.source.editor.setPlainText("Latest")
    QTest.qWait(450)
    assert window.translation_service._pending[0].text == "Latest"
    engine.release.set()
    wait_for(lambda: not window.translation_service.text_busy)
    assert window.text_page.result.editor.toPlainText() == "LATEST"
    window.close()
