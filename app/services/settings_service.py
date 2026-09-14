from PySide6.QtCore import QSettings

from app.config.settings import AppSettings


class SettingsService:
    def __init__(self) -> None:
        self._settings = QSettings()

    def load(self) -> AppSettings:
        return AppSettings(
            source_language=self._settings.value("language/source", "Определить автоматически"),
            target_language=self._settings.value("language/target", "Русский"),
            translation_mode=self._settings.value("translation/mode", "Автоматический"),
            acceleration=self._settings.value("translation/acceleration", "Auto"),
            translate_folders=self._settings.value("translation/folders", True, bool),
        )

    def save_value(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)

    def value(self, key: str, default: object, value_type=None):
        if value_type is None:
            return self._settings.value(key, default)
        return self._settings.value(key, default, value_type)
