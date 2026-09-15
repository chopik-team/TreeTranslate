from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config.constants import APP_NAME, ORGANIZATION_NAME
from app.config.logging_config import configure_logging
from app.gui.main_window import MainWindow
from app.gui.styles.theme_manager import ThemeManager
from app.services.settings_service import SettingsService


class TreeTranslateApplication:
    def __init__(self) -> None:
        self.logger = configure_logging()
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setApplicationName(APP_NAME)
        self.qt_app.setOrganizationName(ORGANIZATION_NAME)
        self.settings = SettingsService()
        self.theme_manager = ThemeManager(self.qt_app, self.settings)
        self.theme_manager.apply_saved_theme()
        self.window = MainWindow()
        self.qt_app.aboutToQuit.connect(self.window.translation_service.shutdown)
        self.qt_app.aboutToQuit.connect(self.window.text_page.shutdown)
        self.logger.info("Application UI initialized")

    def run(self) -> int:
        self.window.show()
        self.logger.info("Application started")
        return self.qt_app.exec()
