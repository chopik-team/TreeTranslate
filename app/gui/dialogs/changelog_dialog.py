from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.config.paths import icon_path


RELEASES = (
    (
        "AW 0.2",
        "ТЕКУЩИЙ ЦИКЛ РАЗРАБОТКИ",
        (
            "Упрощён блок дополнительных параметров: убрана лишняя иконка у перевода папок.",
            "Улучшена подсказка ускорения: SVG-иконка и описание Auto, CPU и GPU при наведении.",
            "Дальнейшая полировка интерфейса и пользовательских сценариев.",
            "Подготовка UI-контрактов к будущему Translation Engine.",
            "Расширение тестов состояний и адаптивности.",
        ),
    ),
    (
        "AW 0.1",
        "ПЕРВЫЙ UI-РЕЛИЗ",
        (
            "Страницы перевода файлов и текста с полноценными состояниями UI.",
            "Drag-and-drop, дерево файлов, языки, режимы и настройки производительности.",
            "Автоматический mock-перевод текста, словарь и примеры использования.",
            "Кликабельный логотип, меню проекта, настройки и тёмная тема.",
            "Модульная архитектура и граница будущего Translation Engine.",
            "Масштабируемые SVG-ресурсы и автоматические smoke-тесты.",
        ),
    ),
)


class ChangelogDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("История изменений TreeTranslate")
        self.setWindowIcon(QIcon(icon_path("clock")))
        self.setMinimumSize(760, 560)
        self.resize(900, 680)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)
        root.addWidget(QLabel("ИСТОРИЯ ИЗМЕНЕНИЙ", objectName="heading"))
        intro = QLabel("Циклы разработки TreeTranslate и основные изменения каждого релиза.", objectName="secondary")
        root.addWidget(intro)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        releases = QVBoxLayout(content)
        releases.setContentsMargins(0, 4, 8, 4)
        releases.setSpacing(12)
        for version, subtitle, entries in RELEASES:
            releases.addWidget(self._release_card(version, subtitle, entries))
        releases.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def _release_card(version: str, subtitle: str, entries: tuple[str, ...]) -> QFrame:
        card = QFrame(objectName="changelogCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QLabel(f"{version} — {subtitle}", objectName="changelogTitle")
        layout.addWidget(title)
        for entry in entries:
            label = QLabel(f"•  {entry}")
            label.setWordWrap(True)
            layout.addWidget(label)
        return card
