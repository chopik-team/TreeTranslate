from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QComboBox

from app.gui.dialogs.settings_dialog import SettingsDialog
from app.gui.styles.theme import load_stylesheet
from app.gui.styles.theme_manager import ThemeManager
from app.services.settings_service import SettingsService


def make_settings(tmp_path) -> SettingsService:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return SettingsService(backend)


def test_local_settings_round_trip(tmp_path) -> None:
    settings = make_settings(tmp_path)
    values = {
        "interface/theme": "Системная",
        "general/ui_language": "Русский",
        "language/source": "Китайский",
        "language/target": "Японский",
        "performance/device": "GPU",
        "performance/mode": "Турбо",
        "translation/translate_folders": False,
        "translation/translate_filenames": True,
        "general/output_location": "custom",
        "general/output_path": "D:/Translations",
    }
    for key, value in values.items():
        settings.save_value(key, value)
    settings.sync()

    restored = make_settings(tmp_path)
    assert restored.interface_theme() == "Системная"
    assert restored.output_location() == ("custom", "D:/Translations")
    assert restored.load().source_language == "Китайский"
    assert restored.load().target_language == "Японский"
    assert restored.load().acceleration == "GPU"
    assert restored.load().translate_folders is False
    assert restored.load().translate_filenames is True
    assert restored.load_performance().mode == "Турбо"


def test_legacy_output_location_values_are_migrated(tmp_path) -> None:
    settings = make_settings(tmp_path)
    settings.save_value("general/output_location", "Выбранная папка")
    settings.save_value("general/output_path", "E:/Ready")
    assert settings.output_location() == ("custom", "E:/Ready")


def test_custom_output_path_is_shown_after_dialog_reopens(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = make_settings(tmp_path)
    settings.save_value("general/output_location", "custom")
    settings.save_value("general/output_path", "D:/Translations")
    settings.sync()

    dialog = SettingsDialog(settings=make_settings(tmp_path))
    combo = dialog.findChild(QComboBox, "outputLocation")
    assert combo.currentText() == "D:/Translations"
    dialog.close()


def test_theme_is_applied_and_restored_from_local_settings(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = make_settings(tmp_path)
    manager = ThemeManager(app, settings)
    manager.apply("Системная")
    settings.sync()

    restored = make_settings(tmp_path)
    selected = ThemeManager(app, restored).apply_saved_theme()
    assert selected == "Системная"
    assert app.styleSheet() == load_stylesheet("Системная")


def test_open_output_defaults_to_disabled(tmp_path) -> None:
    settings = make_settings(tmp_path)
    assert settings.value("general/open_output", False, bool) is False


def test_unfinished_job_restore_defaults_off_and_round_trips_local_paths(tmp_path) -> None:
    settings = make_settings(tmp_path)
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    assert settings.restore_job_enabled() is False

    settings.save_value("general/restore_job", True)
    settings.save_unfinished_job([source])
    assert settings.unfinished_job_paths() == (source.resolve(),)

    settings.save_value("general/restore_job", False)
    assert settings.unfinished_job_paths() == ()
    settings.clear_unfinished_job()
    assert settings.value("job/unfinished", False, bool) is False
