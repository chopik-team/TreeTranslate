from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from app.config.constants import APP_VERSION, GITHUB_URL, ORGANIZATION_NAME
from app.config.paths import TREE_TRANSLATE_LOGO, icon_path


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("О проекте TreeTranslate")
        self.setWindowIcon(QIcon(icon_path("info")))
        self.setMinimumSize(620, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 26)
        logo = QSvgWidget(str(TREE_TRANSLATE_LOGO))
        logo.setFixedSize(92, 92)
        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        title = QPushButton("TreeTranslate", objectName="aboutProjectLink")
        title.setCursor(Qt.CursorShape.PointingHandCursor)
        title.setToolTip("Открыть страницу CHOPIK Team")
        title.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(QLabel(APP_VERSION, objectName="secondary", alignment=Qt.AlignmentFlag.AlignCenter))
        intro = QLabel(
            "TreeTranslate — настольное приложение для удобного локального перевода "
            "папок, документов и текста. На этапе AW 0.1 интерфейс работает с mock-сервисом; "
            "Translation Engine будет подключён отдельно."
        )
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(intro)
        actions = QHBoxLayout()
        github = QPushButton(QIcon(icon_path("external_link")), "GitHub")
        github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        updates = QPushButton(QIcon(icon_path("refresh")), "Проверить обновления")
        updates.clicked.connect(lambda: QMessageBox.information(self, "Обновления", "Установлена актуальная версия AW 0.1."))
        licenses = QPushButton(QIcon(icon_path("help")), "Лицензии")
        licenses.clicked.connect(lambda: QMessageBox.information(self, "Лицензии", "Сведения о лицензиях будут включены перед публичным выпуском."))
        for button in (github, updates, licenses):
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addStretch()
        attribution = QLabel(
            'Иконки: Velora Icon Pack · <a href="https://www.flaticon.com/uicons">Flaticon</a> · '
            '<a href="https://icons8.com">Icons8</a>'
        )
        attribution.setOpenExternalLinks(True)
        layout.addWidget(attribution)
        credits = QLabel(
            f"Разработчик: {ORGANIZATION_NAME}\nВерсия: {APP_VERSION} — Windows\n"
            "Translation backend: не подключён (mock UI)"
        )
        credits.setObjectName("secondary")
        layout.addWidget(credits)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
