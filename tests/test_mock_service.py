import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from app.models.translation_job import JobState
from app.services.mock_translation_service import MockTranslationService


def test_mock_service_control_flow() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    service = MockTranslationService()
    service.start()
    assert service.state is JobState.TRANSLATING
    service.pause_or_resume()
    assert service.state is JobState.PAUSED
    service.pause_or_resume()
    assert service.state is JobState.TRANSLATING
    service.cancel()
    assert service.state is JobState.CANCELLED
    service.simulate_error()
    assert service.state is JobState.ERROR


def test_mock_service_completes_without_sleep() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    service = MockTranslationService()
    service.start()
    for _ in range(25):
        service._tick()
    assert service.state is JobState.COMPLETED
    assert service.progress.percent == 100


def test_basic_text_dictionary() -> None:
    service = MockTranslationService()
    assert service.mock_translate_text("Привет") == "Hi"
    assert service.mock_translate_text("hello") == "Привет"
