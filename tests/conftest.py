"""Each test gets local preferences; never modify the user's desktop registry."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid, ownedByPython
from app.localization import localization


@pytest.fixture(scope='session')
def qt_application():
    # Keep one application alive for the entire suite, as in the real process.
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolated_ui_preferences(tmp_path, monkeypatch, qt_application):
    from app.services import settings_service
    monkeypatch.setattr(settings_service, 'QSettings',
                        lambda: QSettings(str(tmp_path/'default-ui.ini'),QSettings.Format.IniFormat))
    localization.use('ru-RU')
    existing = set(qt_application.topLevelWidgets())
    yield
    # close() hides a QWidget; it does not release its native resources. Dispose
    # test-owned windows while Qt and the test's patched services are still live.
    created = {widget for widget in set(qt_application.topLevelWidgets()) - existing
               if ownedByPython(widget) and widget.parent() is None}
    for widget in created:
        if isValid(widget):
            widget.close()
    for widget in created:
        if isValid(widget):
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    localization.use('ru-RU')
