from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app.config.constants import APP_VERSION, GITHUB_URL
from app.config.paths import TREE_TRANSLATE_LOGO, icon_path
from app.gui.widgets.translation_mode import ModeRequirementsCombo
from app.services.settings_service import SettingsService


class SettingsDialog(QDialog):
    SECTIONS = ("Общие", "Перевод", "Производительность", "Интерфейс", "О программе")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.settings = SettingsService()
        self.setWindowTitle("Настройки TreeTranslate")
        self.setMinimumSize(900, 620)
        self.resize(980, 690)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.addWidget(QLabel("Настройки", objectName="heading"))
        content = QHBoxLayout()
        content.setSpacing(22)
        self.sections = QListWidget(objectName="settingsNav")
        self.sections.setFixedWidth(205)
        self.sections.addItems(self.SECTIONS)
        self.pages = QStackedWidget()
        builders = (self._general_page, self._translation_page, self._performance_page, self._interface_page, self._about_page)
        for builder in builders:
            self.pages.addWidget(self._scrollable(builder()))
        self.sections.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sections.setCurrentRow(0)
        content.addWidget(self.sections)
        content.addWidget(self.pages, 1)
        root.addLayout(content, 1)
        footer = QHBoxLayout()
        footer.addWidget(QLabel("Изменения сохраняются автоматически", objectName="secondary"))
        footer.addStretch()
        close = QPushButton("Готово")
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    @staticmethod
    def _page(title: str, description: str) -> tuple[QWidget, QVBoxLayout, QFormLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 2, 14, 12)
        layout.setSpacing(13)
        layout.addWidget(QLabel(title, objectName="heading"))
        layout.addWidget(QLabel(description, objectName="secondary"))
        form = QFormLayout()
        form.setHorizontalSpacing(30)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        return page, layout, form

    def _combo(self, key: str, default: str, options: Iterable[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(list(options))
        combo.setCurrentText(str(self.settings.value(key, default)))
        combo.currentTextChanged.connect(lambda value, k=key: self.settings.save_value(k, value))
        return combo

    def _check(self, key: str, text: str, default: bool) -> QCheckBox:
        check = QCheckBox(text)
        check.setChecked(self.settings.value(key, default, bool))
        check.toggled.connect(lambda value, k=key: self.settings.save_value(k, value))
        return check

    @staticmethod
    def _add_checks(layout: QVBoxLayout, checks: Iterable[QCheckBox]) -> None:
        for check in checks:
            layout.addWidget(check)

    def _general_page(self) -> QWidget:
        page, layout, form = self._page("Общие", "Основное поведение приложения и сохранение результатов.")
        form.addRow("Язык интерфейса", self._combo("general/ui_language", "Русский", ["Русский"]))
        form.addRow("Папка сохранения", self._combo("general/output_location", "Рядом с оригиналом", ["Рядом с оригиналом", "Выбрать папку при запуске"]))
        template = QLineEdit(str(self.settings.value("general/output_template", "{name}_{lang}")))
        preview = QLabel(objectName="secondary")
        def update_template(value: str) -> None:
            self.settings.save_value("general/output_template", value)
            preview.setText("Пример: " + value.replace("{name}", "Manual").replace("{lang}", "RU"))
        template.textChanged.connect(update_template)
        update_template(template.text())
        template_box = QVBoxLayout()
        template_box.addWidget(template)
        template_box.addWidget(preview)
        form.addRow("Шаблон выходной папки", template_box)
        layout.addSpacing(4)
        self._add_checks(layout, [
            self._check("general/preserve_originals", "Не изменять оригинальные файлы", True),
            self._check("general/open_output", "Открывать папку после завершения", True),
            self._check("general/remember_language", "Запоминать последний выбранный язык", True),
            self._check("general/restore_job", "Восстанавливать незавершённую задачу после запуска", True),
        ])
        layout.addStretch()
        return page

    def _translation_page(self) -> QWidget:
        page, layout, form = self._page("Перевод", "Значения по умолчанию для новых задач.")
        form.addRow("Исходный язык", self._combo("translation/source", "Авто", ["Авто", "Китайский", "Английский", "Немецкий", "Японский"]))
        form.addRow("Язык перевода", self._combo("translation/target", "Русский", ["Русский", "Английский", "Немецкий", "Испанский", "Французский"]))
        form.addRow("Режим", self._combo("translation/mode", "Автоматический", ["Автоматический", "Economy", "Fast", "Balanced", "Turbo", "Maximum"]))
        layout.addSpacing(4)
        self._add_checks(layout, [
            self._check("translation/folders", "Переводить названия папок", True),
            self._check("translation/files", "Переводить названия файлов", True),
            self._check("translation/content", "Переводить содержимое документов", True),
            self._check("translation/cache", "Использовать кэш повторяющихся фраз", True),
            self._check("translation/terms", "Использовать словарь терминов", True),
            self._check("translation/keep_name", "Сохранять оригинальное имя рядом", False),
        ])
        glossary = QPushButton("Управление пользовательским глоссарием")
        glossary.setEnabled(False)
        glossary.setToolTip("Функция запланирована для следующего этапа")
        layout.addWidget(glossary, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _performance_page(self) -> QWidget:
        page, layout, form = self._page("Производительность", "Параметры сохраняются, но пока не управляют Translation Engine.")
        form.addRow("Устройство", self._combo("performance/device", "Auto", ["Auto", "CPU", "GPU"]))
        profile = ModeRequirementsCombo(include_automatic=False)
        profile.set_clean_mode(str(self.settings.value("performance/profile", "Баланс")))
        profile.currentIndexChanged.connect(lambda: self.settings.save_value("performance/profile", profile.clean_mode()))
        form.addRow("Профиль", profile)
        form.addRow("Количество потоков CPU", self._combo("performance/cpu_threads", "Автоматически", ["Автоматически", "2", "4", "6", "8", "12", "16"]))
        form.addRow("Использование GPU", self._combo("performance/gpu", "Автоматически", ["Автоматически", "Отключено", "Предпочтительно"]))
        form.addRow("Ограничение RAM", self._combo("performance/ram", "Автоматически", ["Автоматически", "4 GB", "8 GB", "16 GB", "32 GB"]))
        form.addRow("Ограничение VRAM", self._combo("performance/vram", "Автоматически", ["Автоматически", "2 GB", "4 GB", "8 GB", "12 GB", "16 GB"]))
        self._add_checks(layout, [
            self._check("performance/unload_model", "Освобождать модель из памяти после завершения", True),
            self._check("performance/reduce_load", "Автоматически снижать нагрузку при нехватке памяти", True),
        ])
        recommend = QPushButton("Определить рекомендуемые настройки")
        recommend.clicked.connect(lambda: QMessageBox.information(self, "Рекомендации", "Определение конфигурации появится вместе с Translation Engine."))
        layout.addWidget(recommend, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(QLabel("Benchmark оборудования будет добавлен позднее.", objectName="secondary"))
        layout.addStretch()
        return page

    def _interface_page(self) -> QWidget:
        page, layout, form = self._page("Интерфейс", "Внешний вид и отображение прогресса.")
        form.addRow("Тема", self._combo("interface/theme", "Тёмная", ["Тёмная", "Системная"]))
        form.addRow("Масштаб интерфейса", self._combo("interface/scale", "Автоматически", ["Автоматически", "100%", "125%", "150%"]))
        accent = QComboBox()
        accent.addItem("Фирменный зелёный TreeTranslate")
        accent.setEnabled(False)
        form.addRow("Акцентный цвет", accent)
        self._add_checks(layout, [
            self._check("interface/animations", "Анимации интерфейса", True),
            self._check("interface/eta", "Показывать расчёт оставшегося времени", True),
            self._check("interface/detailed_progress", "Показывать подробный прогресс", True),
            self._check("interface/extensions", "Показывать расширения файлов", True),
            self._check("interface/tray", "Сворачивать приложение в системный трей", False),
        ])
        layout.addStretch()
        return page

    def _about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 14, 12)
        logo = QSvgWidget(str(TREE_TRANSLATE_LOGO))
        logo.setFixedSize(100, 100)
        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        for text, name in (("TreeTranslate", "heading"), (APP_VERSION, "secondary"), ("Developed by CHOPIK Team", "secondary")):
            layout.addWidget(QLabel(text, objectName=name, alignment=Qt.AlignmentFlag.AlignCenter))
        layout.addSpacing(12)
        buttons = QHBoxLayout()
        github = QPushButton(QIcon(icon_path("external_link")), "GitHub")
        github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        updates = QPushButton(QIcon(icon_path("refresh")), "Проверить обновления")
        updates.clicked.connect(lambda: QMessageBox.information(self, "Обновления", "Установлена актуальная версия AW 0.1."))
        licenses = QPushButton(QIcon(icon_path("help")), "Лицензии")
        licenses.clicked.connect(lambda: QMessageBox.information(self, "Лицензии", "Сведения о лицензиях будут добавлены перед выпуском."))
        for button in (github, updates, licenses):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        attribution = QLabel('Иконки: Velora Icon Pack · <a href="https://www.flaticon.com/uicons">Flaticon</a> · <a href="https://icons8.com">Icons8</a>')
        attribution.setOpenExternalLinks(True)
        layout.addWidget(attribution)
        details = QLabel("Сторонние компоненты\nPython 3.12 · PySide6 / Qt 6\n\nTranslation backend\nНе подключён — используется mock-сервис.", objectName="secondary")
        details.setWordWrap(True)
        layout.addWidget(details)
        layout.addStretch()
        return page
