from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout

from app.config.constants import APP_VERSION, ORGANIZATION_NAME, PROJECT_GITHUB_URL
from app.config.paths import TREE_TRANSLATE_LOGO, icon_path


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("О проекте TreeTranslate")
        self.setWindowIcon(QIcon(icon_path("info")))
        self.setMinimumSize(620, 540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 26)
        logo = QSvgWidget(str(TREE_TRANSLATE_LOGO))
        logo.setFixedSize(92, 92)
        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        title = QPushButton("TreeTranslate", objectName="aboutProjectLink")
        title.setCursor(Qt.CursorShape.PointingHandCursor)
        title.setToolTip("Открыть TreeTranslate на GitHub")
        title.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(PROJECT_GITHUB_URL)))
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        version = QLabel(f"{APP_VERSION} · Windows", objectName="secondary", alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        layout.addSpacing(8)
        intro = QLabel(
            "TreeTranslate — настольное приложение для локального перевода файлов, "
            "папок, архивов, документов и обычного текста с сохранением понятной структуры.\n\n"
            "Выберите материалы и языки — приложение сохранит структуру проекта и поможет "
            "последовательно обработать весь выбранный контент."
        )
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(intro)
        layout.addSpacing(12)
        credits = QFrame(objectName="aboutCredits")
        credits_layout = QGridLayout(credits)
        credits_layout.setContentsMargins(18, 14, 18, 14)
        credits_layout.setHorizontalSpacing(24)
        credits_layout.setVerticalSpacing(9)
        credit_rows = (
            ("Проект", ORGANIZATION_NAME),
            ("Концепт", "Алексей Широков · Станислав Смирнов"),
            ("Дизайн", "Станислав Смирнов"),
            ("Код", "ChatGPT 5.6 Sol"),
        )
        for row, (role, names) in enumerate(credit_rows):
            credits_layout.addWidget(QLabel(role, objectName="caption"), row, 0)
            value = QLabel(names)
            value.setWordWrap(True)
            credits_layout.addWidget(value, row, 1)
        credits_layout.setColumnStretch(1, 1)
        layout.addWidget(credits)
        layout.addStretch()
        attribution = QLabel(
            "Иконки: TreeTranslate Icon Pack · Flaticon · Icons8"
        )
        attribution.setObjectName("secondary")
        layout.addWidget(attribution)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
