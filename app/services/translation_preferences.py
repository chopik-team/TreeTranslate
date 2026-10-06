from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.services.settings_service import SettingsService
from app.engine.languages import AUTOMATIC_LANGUAGE, language_code


class TranslationPreferences(QObject):
    """Single live source for translation controls shared by all pages."""

    device_changed = Signal(str)
    profile_changed = Signal(str)
    languages_changed = Signal(str, str)
    domain_changed = Signal(str)
    translate_directories_changed = Signal(bool)
    translate_filenames_changed = Signal(bool)

    def __init__(self, settings: SettingsService | None = None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings or SettingsService()
        app = self.settings.load()
        performance = self.settings.load_performance()
        self.device = performance.device
        self.profile = performance.mode
        self.source_language = app.source_language
        # Repair settings saved by builds that exposed an unusable Auto target.
        self.target_language = (
            "Английский" if language_code(app.source_language) == "ru" else "Русский"
        ) if language_code(app.target_language) == "auto" else app.target_language
        if self.target_language != app.target_language:
            self.settings.save_value("language/target", self.target_language)
        if (language_code(self.source_language) != "auto"
                and language_code(self.source_language) == language_code(self.target_language)):
            self.source_language = AUTOMATIC_LANGUAGE
            self.settings.save_value("language/source", self.source_language)
        self.translate_directories = app.translate_folders
        self.translate_filenames = app.translate_filenames
        from app.config.knowledge_domains import DOMAINS
        self.domain = 'auto'

    def set_domain(self, value: str) -> None:
        from app.config.knowledge_domains import DOMAINS
        if value not in dict(DOMAINS) or value == self.domain:
            return
        self.domain = value
        self.settings.save_value('translation/domain', value)
        self.domain_changed.emit(value)

    def set_device(self, value: str) -> None:
        if value not in ('Auto', 'CPU', 'GPU') or value == self.device:
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
        if language_code(target) == "auto":
            target = "Русский" if language_code(source) != "ru" else "Английский"
        if not source:
            source = AUTOMATIC_LANGUAGE
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

    def set_translate_filenames(self, enabled: bool) -> None:
        if enabled == self.translate_filenames:
            return
        self.translate_filenames = enabled
        self.settings.save_value("translation/translate_filenames", enabled)
        self.translate_filenames_changed.emit(enabled)
