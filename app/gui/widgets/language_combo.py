from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QComboBox

from app.config.paths import ICONS_DIR


LANGUAGE_ICON_FILES = {
    "Русский": "language_ru.png",
    "Английский": "language_en_us.png",
    "English (US)": "language_en_us.png",
    "English (UK)": "language_en_gb.png",
    "Немецкий": "language_de.png",
    "Deutsch": "language_de.png",
    "Испанский": "language_es.png",
    "Español": "language_es.png",
    "Французский": "language_fr.png",
    "Français": "language_fr.png",
    "Română": "language_ro.png",
    "Китайский": "language_zh.png",
    "中文": "language_zh.png",
    "Японский": "language_ja.png",
    "日本語": "language_ja.png",
}


def language_icon(language: str) -> QIcon:
    filename = LANGUAGE_ICON_FILES.get(language)
    if not filename:
        return QIcon()
    return QIcon(str(Path(ICONS_DIR) / "languages" / filename))


class LanguageComboBox(QComboBox):
    """Language selector using TreeTranslate's bundled flag assets."""

    def __init__(self, languages=(), parent=None) -> None:
        super().__init__(parent)
        self.setIconSize(QSize(24, 17))
        self.add_languages(languages)

    def add_languages(self, languages) -> None:
        for language in languages:
            icon = language_icon(language)
            if icon.isNull():
                self.addItem(language)
            else:
                self.addItem(icon, language)
