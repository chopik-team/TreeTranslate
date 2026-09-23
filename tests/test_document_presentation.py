from pathlib import Path
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QLabel

from app.config.constants import SUPPORTED_FILE_FILTER
from app.config.paths import icon_path
from app.documents.control import JobControl
from app.documents.scanner import scan_sources
from app.gui.main_window import MainWindow
from app.services.hybrid_translation_service import HybridTranslationService
from test_document_service import make_engine


@pytest.mark.parametrize("names,expected", [
    (["manual.PDF"], "Найдено PDF: 1"),
    (["manual.DOCX"], "Найдено DOCX: 1"),
    (["manual.pdf", "manual.docx"], "Найдено DOCX/PDF: 2"),
    (["notes.txt"], "Найдено: 0"),
])
def test_detected_formats_and_icons(tmp_path, names, expected):
    app = QApplication.instance() or QApplication([])
    for name in names:
        (tmp_path / name).write_bytes(b"scan-only fixture")
    service = HybridTranslationService(engine=make_engine())
    window = MainWindow(translation_service=service)
    try:
        service.files.scan_result = scan_sources([tmp_path], JobControl())
        window.translation._show_tree()
        assert window.file_page.file_status.text().startswith(expected + ".")
        tree = window.file_page.file_tree.tree
        folder = tree.topLevelItem(0).child(0)
        if service.files.scan_result.files:
            for i in range(folder.childCount()):
                item = folder.child(i)
                suffix = Path(item.text(0)).suffix.lower().lstrip(".")
                expected_icon = QIcon(icon_path(suffix)).pixmap(24, 24).toImage()
                assert item.icon(0).pixmap(24, 24).toImage() == expected_icon
        for suffix in ("docx", "pdf"):
            label = window.file_page.drop_zone.findChild(QLabel, f"dropIcon_{suffix}")
            assert label is not None and not label.pixmap().isNull()
            assert f"*.{suffix}" in SUPPORTED_FILE_FILTER
    finally:
        window.close()
