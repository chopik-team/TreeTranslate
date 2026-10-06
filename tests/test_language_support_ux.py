import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QPushButton, QScrollArea, QTabWidget

from app.engine.languages import LANGUAGE_CODES, RELEASE_LANGUAGE_CODES, RELEASE_LANGUAGE_LABELS
from app.gui.dialogs.about_dialog import AboutDialog
from app.gui.widgets.language_selector import LanguageSelector
from app.gui.widgets.language_support_tab import trend_html
from app.services.language_support import load_support, previous_metric, resource_depth, trend
from tools.build_language_support import build_snapshot, resource_counts


def test_generated_snapshot_matches_actual_bundled_data_and_audit():
    snapshot = load_support()
    assert snapshot == build_snapshot()
    actual = resource_counts()
    assert {r["code"] for r in snapshot["languages"]} == RELEASE_LANGUAGE_CODES
    for row in snapshot["languages"]:
        assert row["counts"] == actual[row["code"]]
        assert row["status"] == "RELEASE_READY"
        assert row["documents"]["docx"] and row["documents"]["native_pdf"]
        assert row["documents"]["ocr"] == (row["code"] in {"ru", "en", "zh"})
    english = next(r for r in snapshot["languages"] if r["code"] == "en")
    assert english["labels"] == ["Английский", "Английский (США)"]
    assert all(LANGUAGE_CODES[x] == "en" for x in english["labels"])
    assert all(value is None for code in ("de", "fr", "es", "ja") for value in actual[code].values())
    assert actual["en"]["dictionary_entries"] == 156890  # Articles, not shared model vocabulary.
    assert actual["ru"]["dictionary_entries"] == 45561


@pytest.mark.parametrize("previous,current,expected", [
    (10, 15, (5, "positive")), (15, 10, (-5, "negative")),
    (10, 10, (0, "neutral")), (None, 10, (None, "neutral")),
])
def test_trends(previous, current, expected):
    assert trend(previous, current) == expected
    rendered = trend_html(previous, current)
    assert ("Первый зафиксированный снимок" in rendered) == (previous is None)
    if previous is not None:
        assert "→" in rendered
        from app.gui.styles.theme import color
        token = {"positive": "accent_green", "negative": "danger_red", "neutral": "text_primary"}[expected[1]]
        assert color(token) in rendered


def test_depth_and_history_are_resource_only_and_deterministic():
    snapshot = load_support()
    scores = {r["code"]: resource_depth(r["counts"], r["documents"]["ocr"]) for r in snapshot["languages"]}
    assert scores == {"ru": 5, "en": 4, "zh": 3, "de": 1, "es": 1, "fr": 1, "ja": 1}
    assert previous_metric(snapshot, "en", "dictionary_entries") == (156890, "AW 0.8.2")
    assert previous_metric(snapshot, "zh", "technical_entries") == (4402, "AW 0.8.2")
    assert previous_metric(snapshot, "en", "bilingual_entries") == (62181, "AW 0.8.2")
    assert previous_metric(snapshot, "fr", "bilingual_entries") == (None, None)
    assert resource_depth({}, False) == 1


def test_next_version_preserves_current_snapshot_without_inventing_counts(monkeypatch):
    import tools.build_language_support as builder
    current = load_support()
    monkeypatch.setattr(builder, "APP_VERSION", "future-test-version")
    upcoming = builder.build_snapshot()
    assert upcoming["history"][:-1] == current["history"]
    assert upcoming["history"][-1]["version"] == current["version"]
    assert upcoming["history"][-1]["counts"] == {r["code"]: r["counts"] for r in current["languages"]}


def test_about_tabs_cards_disclosures_and_clean_selector(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("UI attempted network"))
    app = QApplication.instance() or QApplication([])
    dialog = AboutDialog()
    dialog.show()
    tabs = dialog.findChild(QTabWidget, "aboutTabs")
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Поддержка языков", "Движки", "Лицензии и источники"]
    assert tabs.currentIndex() == 0
    app.processEvents()
    cards = dialog.findChildren(QFrame, "languageSupportCard")
    assert {c.property("languageCode") for c in cards} == RELEASE_LANGUAGE_CODES
    for card in cards:
        labels = card.findChildren(QLabel)
        assert not any("Базовый перевод" in x.text() for x in labels)
        assert not any("0 слов" in x.text() for x in labels)
        assert not card.findChildren(QLabel, "languageResourceMetric")
        button = card.findChild(QPushButton, "languageDetailsButton")
        button.click()
        app.processEvents()
        details = card.findChild(QDialog, "languageDetailsDialog")
        assert details.isVisible()
        metrics = card.findChildren(QLabel, "languageResourceMetric")
        labels = card.findChildren(QLabel)
        assert len(metrics) == 4
        assert all(x.isVisible() for x in metrics)
        if card.property("languageCode") in {"de", "es", "fr", "ja"}:
            assert sum("Отдельная база не добавлена" in x.text() for x in labels) == 4
        assert any(x.isVisible() and "Код:" in x.text() for x in labels)
        details.accept()
    assert not isinstance(tabs.widget(0), QScrollArea)
    selector = LanguageSelector()
    assert [selector.target_combo.itemText(i) for i in range(selector.target_combo.count())] == list(RELEASE_LANGUAGE_LABELS)
    assert all(not selector.target_combo.itemIcon(i).isNull() for i in range(selector.target_combo.count()))
    dialog.close()
    selector.close()
