import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app.gui.dialogs.settings_dialog import SettingsDialog
from app.gui.main_window import MainWindow as ProductionMainWindow
from app.services.mock_translation_service import MockTranslationService
from app.models.translation_job import JobState
from app.services.settings_service import SettingsService
from app.services.translation_preferences import TranslationPreferences
from app.services.translation_session_manager import TranslationSessionManager


def MainWindow():
    """AW 0.3 UI tests retain an explicitly injected mock; production uses hybrid."""
    return ProductionMainWindow(translation_service=MockTranslationService())


def test_session_manager_enforces_configurable_single_job_policy() -> None:
    sessions = TranslationSessionManager(max_active_translation_jobs=1)
    assert sessions.start("file")
    assert not sessions.start("text")
    sessions.finish("file")
    assert sessions.start("text")


def test_device_and_profile_are_synchronized_everywhere(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = SettingsService(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    preferences = TranslationPreferences(settings)
    window = MainWindow()
    # Replace the window's live source for this isolated test.
    window.preferences = preferences
    window.translation.preferences.device_changed.disconnect(window.translation._apply_device)
    window.translation.preferences.profile_changed.disconnect(window.translation._apply_profile)
    preferences.device_changed.connect(window.translation._apply_device)
    preferences.profile_changed.connect(window.translation._apply_profile)
    dialog = SettingsDialog(window, settings, preferences)

    preferences.set_device("GPU")
    preferences.set_profile("Турбо")
    assert window.file_page.acceleration.selected() == "GPU"
    assert window.text_page.acceleration.selected() == "GPU"
    assert dialog.device_combo.currentText() == "GPU"
    assert window.file_page.mode.combo.clean_mode() == "Турбо"
    assert window.text_page.mode.combo.clean_mode() == "Турбо"
    assert dialog.performance_mode.clean_mode() == "Турбо"

    dialog.device_combo.setCurrentText("CPU")
    dialog.performance_mode.set_clean_mode("Эконом")
    assert window.file_page.acceleration.selected() == "CPU"
    assert window.text_page.acceleration.selected() == "CPU"
    assert window.file_page.mode.combo.clean_mode() == "Эконом"
    assert window.text_page.mode.combo.clean_mode() == "Эконом"
    dialog.close()
    window.close()


def test_text_page_profile_change_syncs_file_page_and_settings() -> None:
    app = QApplication.instance() or QApplication([])
    old_organization, old_application = app.organizationName(), app.applicationName()
    app.setOrganizationName("CHOPIK Team")
    app.setApplicationName("TreeTranslateTests")
    window = MainWindow()
    window.text_page.mode.combo.set_clean_mode("Эконом")
    window.text_page.mode.combo.set_clean_mode("Максимум")
    assert window.preferences.profile == "Максимум"
    assert window.file_page.mode.combo.clean_mode() == "Максимум"
    assert window.settings.load_performance().mode == "Максимум"
    window.close()
    app.setOrganizationName(old_organization)
    app.setApplicationName(old_application)


def test_stale_text_request_never_overwrites_latest_input() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.text_page.source.editor.setPlainText("Привет")
    window.translation.translate_text("Привет")
    window.text_page.source.editor.setPlainText("Спасибо")
    window.translation.translate_text("Спасибо")
    app.processEvents()
    assert window.text_page.result.editor.toPlainText() == "Thank you"
    window.close()


def test_rapid_typing_is_collapsed_to_latest_debounced_request() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    with patch.object(window.translation.service, "translate_text", return_value="LATEST") as translate:
        for text in ("П", "Пр", "При", "Прив", "Привет"):
            window.text_page.source.editor.setPlainText(text)
        QTest.qWait(450)
        app.processEvents()
    translate.assert_called_once_with("Привет")
    assert window.text_page.result.editor.toPlainText() == "LATEST"
    window.close()


def test_file_job_requires_confirmation_before_text_navigation() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.translation._show_tree()
    window.translation._state_changed(JobState.READY)
    window.translation._start_translation()
    assert window.sessions.is_active("file")

    with patch.object(window, "_confirm_stop_and_switch", return_value=False):
        window.request_navigation(1)
    assert window.stack.currentIndex() == 0
    assert window.translation.service.state is JobState.TRANSLATING

    with patch.object(window, "_confirm_stop_and_switch", return_value=True):
        window.request_navigation(1)
    assert window.stack.currentIndex() == 1
    assert window.translation.service.state is JobState.CANCELLED
    assert not window.sessions.is_active("file")
    window.close()


def test_text_job_requires_confirmation_before_file_navigation() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.navigation.navigate(1)
    window.title_bar.tabs.set_current(1)
    assert window.sessions.start("text")
    with patch.object(window, "_confirm_stop_and_switch", return_value=False):
        window.request_navigation(0)
    assert window.stack.currentIndex() == 1
    assert window.sessions.is_active("text")
    with patch.object(window, "_confirm_stop_and_switch", return_value=True):
        window.request_navigation(0)
    assert window.stack.currentIndex() == 0
    assert not window.sessions.is_active("text")
    window.close()


def test_translate_directories_is_a_persisted_job_config_property() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.file_page.translate_folders.setChecked(False)
    assert window.translation.job_config.translate_directories is False
    assert window.preferences.translate_directories is False
    window.file_page.translate_filenames.setChecked(True)
    assert window.translation.job_config.translate_filenames is True
    assert window.preferences.translate_filenames is True
    assert window.preferences.translate_directories is False
    window.close()


def test_swapped_languages_sync_between_pages_and_settings() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    file_languages = window.file_page.languages
    text_languages = window.text_page.languages
    file_languages.source_combo.setCurrentText("Русский")
    file_languages.target_combo.setCurrentText("Китайский")
    file_languages.swap_button.click()

    assert (file_languages.source_combo.currentText(), file_languages.target_combo.currentText()) == (
        "Китайский", "Русский"
    )
    assert (text_languages.source_combo.currentText(), text_languages.target_combo.currentText()) == (
        "Китайский", "Русский"
    )
    assert (window.preferences.source_language, window.preferences.target_language) == (
        "Китайский", "Русский"
    )
    window.close()
