"""Manual developer smoke test: actual Qt event loop, local models, synthetic text."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import QApplication

from app.gui.main_window import MainWindow
from app.gui.styles.theme import load_stylesheet


def main():
    app = QApplication([])
    app.setOrganizationName("CHOPIK Team QA")
    app.setApplicationName("TreeTranslate AW04 QA")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(Path("build/qa-settings").resolve()))
    app.setStyleSheet(load_stylesheet())
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.preferences.set_languages("Китайский", "Русский")
    window.preferences.set_device("GPU")
    window.preferences.set_profile("Баланс")
    # Exercise the real idle timer in the native GPU worker lifecycle.
    window.translation_service.engine.policy.idle_timeout_seconds = 0.2
    window.request_navigation(1)
    window.show()
    results, errors = [], []

    def complete(result):
        results.append(result)
        print(f"GUI translated backend={result.backend} device={result.device} source={result.source_language}", flush=True)
        if len(results) == 1:
            def next_request():
                assert window.translation_service.engine.runtime._warm is None, "GPU model was not unloaded after idle"
                Path("docs/qa").mkdir(parents=True, exist_ok=True)
                window.grab().save("docs/qa/aw04-real-text.png")
                window.text_page.source.editor.setPlainText("请保存配置文件。")
            QTimer.singleShot(500, next_request)
        elif len(results) == 2:
            def detect_request():
                window.preferences.set_languages("Определить автоматически", "Русский")
                window.text_page.source.editor.setPlainText("Save the configuration file before restarting the application.")
            QTimer.singleShot(0, detect_request)
        else:
            QTimer.singleShot(0, window.close)

    def failed(_request_id, message):
        errors.append(message)
        QTimer.singleShot(0, window.close)

    timeout = QTimer(singleShot=True, interval=30000)
    timeout.timeout.connect(lambda: failed("", "UI translation timed out"))
    window.translation_service.text_completed.connect(complete)
    window.translation_service.text_failed.connect(failed)
    timeout.start()
    window.text_page.source.editor.setPlainText("请重新启动应用程序。")
    app.exec()
    timeout.stop()
    assert not errors, errors
    assert len(results) == 3, len(results)
    assert results[0].backend == "m2m100" and results[0].device == "cuda"
    assert results[1].backend == "m2m100" and results[1].device == "cuda"
    assert results[2].source_language == "en"
    print("Real GUI autotranslation, GPU idle/reload, local language detection and shutdown passed", flush=True)


if __name__ == "__main__":
    main()
