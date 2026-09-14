import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.gui.dialogs.changelog_dialog import ChangelogDialog, RELEASES


def test_changelog_renders_release_history() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = ChangelogDialog()
    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert RELEASES
    assert "AW 0.2-alpha" in text
    assert "AW 0.1" in text
    dialog.close()
