from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QWidget

from app.config.constants import SUPPORTED_FILE_FILTER


class FilePicker:
    @staticmethod
    def choose_files(parent: QWidget) -> list[Path]:
        names, _ = QFileDialog.getOpenFileNames(parent, "Выберите документы DOCX или PDF", "", SUPPORTED_FILE_FILTER)
        return [Path(name) for name in names]

    @staticmethod
    def choose_folder(parent: QWidget) -> Path | None:
        name = QFileDialog.getExistingDirectory(parent, "Выберите папку")
        return Path(name) if name else None
