from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow, QMessageBox, QSizeGrip, QStackedWidget, QVBoxLayout, QWidget

from app.config.constants import APP_NAME, BOOSTY_URL, DEFAULT_WINDOW_SIZE, MINIMUM_WINDOW_SIZE
from app.controllers.navigation_controller import NavigationController
from app.controllers.translation_ui_controller import TranslationUiController
from app.gui.dialogs.about_dialog import AboutDialog
from app.gui.dialogs.changelog_dialog import ChangelogDialog
from app.gui.dialogs.settings_dialog import SettingsDialog
from app.gui.pages.file_translation_page import FileTranslationPage
from app.gui.pages.text_translation_page import TextTranslationPage
from app.gui.widgets.brand_menu import BrandMenu
from app.gui.widgets.title_bar import TitleBar


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(*MINIMUM_WINDOW_SIZE)
        self.resize(*DEFAULT_WINDOW_SIZE)
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)
        self.stack = QStackedWidget()
        self.file_page = FileTranslationPage()
        self.text_page = TextTranslationPage()
        self.stack.addWidget(self.file_page)
        self.stack.addWidget(self.text_page)
        layout.addWidget(self.stack, 1)
        self.size_grip = QSizeGrip(root)
        self.size_grip.setFixedSize(18, 18)
        self.navigation = NavigationController(self.stack, self)
        self.translation = TranslationUiController(self.file_page, self.text_page, self)
        self.brand_menu = BrandMenu(self)
        self.title_bar.page_changed.connect(self.navigation.navigate)
        self.title_bar.brand_requested.connect(self.open_brand_menu)
        self.brand_menu.settings_requested.connect(self.open_settings)
        self.brand_menu.about_requested.connect(self.open_about)
        self.brand_menu.changelog_requested.connect(self.open_changelog)
        self.brand_menu.support_requested.connect(self.open_support_page)
        self.brand_menu.exit_requested.connect(self.close)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.size_grip.move(self.width() - self.size_grip.width() - 3, self.height() - self.size_grip.height() - 3)
        self.size_grip.raise_()

    def open_brand_menu(self) -> None:
        position = self.title_bar.brand.mapToGlobal(self.title_bar.brand.rect().bottomLeft())
        self.brand_menu.show_at(position)

    def open_settings(self) -> None:
        SettingsDialog(self).exec()
        self.translation.refresh_performance_controls()

    def open_about(self) -> None:
        AboutDialog(self).exec()

    def open_changelog(self) -> None:
        ChangelogDialog(self).exec()

    @staticmethod
    def open_support_page() -> None:
        QDesktopServices.openUrl(QUrl(BOOSTY_URL))

    def show_placeholder(self, title: str) -> None:
        QMessageBox.information(
            self,
            title,
            "Этот раздел будет доступен в следующей версии TreeTranslate.",
        )
