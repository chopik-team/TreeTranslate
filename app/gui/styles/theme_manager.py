from PySide6.QtWidgets import QApplication

from app.gui.styles.theme import THEMES, load_stylesheet
from app.services.settings_service import SettingsService


class ThemeManager:
    def __init__(self, application: QApplication, settings: SettingsService) -> None:
        self.application = application
        self.settings = settings

    @property
    def available_themes(self) -> tuple[str, ...]:
        return tuple(THEMES)

    def apply_saved_theme(self) -> str:
        return self.apply(self.settings.interface_theme())

    def apply(self, theme_name: str) -> str:
        selected = theme_name if theme_name in THEMES else "Тёмная"
        self.application.setStyleSheet(load_stylesheet(selected))
        self.settings.save_value("interface/theme", selected)
        return selected
