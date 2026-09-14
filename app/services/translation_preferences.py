from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.services.settings_service import SettingsService


class TranslationPreferences(QObject):
    """Single live source for translation controls shared by all pages."""

    device_changed = Signal(str)
    profile_changed = Signal(str)
    languages_changed = Signal(str, str)
    translate_directories_changed = Signal(bool)

    def __init__(self, settings: SettingsService | None = None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings or SettingsService()
        app = self.settings.load()
        performance = self.settings.load_performance()
        self.device = performance.device
        self.profile = performance.mode
        self.source_language = app.source_language
        self.target_language = app.target_language
        self.translate_directories = app.translate_folders

    def set_device(self, value: str) -> None:
        if value == self.device:
            return
        self.device = value
        self.settings.save_value("performance/device", value)
        self.device_changed.emit(value)

    def set_profile(self, value: str) -> None:
        if value == self.profile:
            return
        self.profile = value
        self.settings.save_value("performance/mode", value)
        self.profile_changed.emit(value)

    def set_languages(self, source: str, target: str) -> None:
        if (source, target) == (self.source_language, self.target_language):
            return
        self.source_language, self.target_language = source, target
        self.settings.save_value("language/source", source)
        self.settings.save_value("language/target", target)
        self.languages_changed.emit(source, target)

    def set_translate_directories(self, enabled: bool) -> None:
        if enabled == self.translate_directories:
            return
        self.translate_directories = enabled
        self.settings.save_value("translation/translate_folders", enabled)
        self.translate_directories_changed.emit(enabled)
