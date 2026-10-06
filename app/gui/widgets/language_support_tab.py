"""Presentation-only language cards sharing the About dialog's card styling."""
from html import escape

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.gui.styles.theme import color
from app.gui.widgets.language_combo import language_icon
from app.services.language_support import (
    DEPTH_INFO, RESOURCE_LABELS, count_text, load_support, previous_metric, resource_depth, trend,
)

from app.localization.widgets import QDialog, QLabel, QPushButton


def label(text, name=""):
    result = QLabel(text, objectName=name)
    result.setWordWrap(True)
    return result


def trend_html(previous, current):
    delta, state = trend(previous, current)
    if delta is None:
        return "Первый зафиксированный снимок"
    new_color = color({"positive": "accent_green", "negative": "danger_red", "neutral": "text_primary"}[state])
    change = f"+{delta}" if delta > 0 else str(delta).replace("-", "−")
    return (f'<span style="color:{color("text_secondary")}">{count_text(previous)}</span> → '
            f'<span style="color:{new_color}">{count_text(current)} ({change})</span>')


class LanguageSupportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("languageSupportTab")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(label("Звёзды показывают глубину дополнительных языковых ресурсов.", "secondary"))
        grid = QGridLayout()
        grid.setSpacing(8)
        layout.addLayout(grid, 1)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        snapshot = load_support()
        for index, row in enumerate(snapshot["languages"]):
            card = QFrame(objectName="languageSupportCard")
            card.setProperty("languageCode", row["code"])
            inner = QVBoxLayout(card)
            inner.setContentsMargins(10, 8, 10, 8)
            inner.setSpacing(4)
            heading = QHBoxLayout()
            flag = QLabel()
            flag.setPixmap(language_icon(row["labels"][0]).pixmap(QSize(24, 17)))
            heading.addWidget(flag)
            name = label(row["labels"][0], "aboutSectionTitle")
            name.setToolTip(" / ".join(row["labels"]))
            heading.addWidget(name, 1)
            inner.addLayout(heading)
            depth = resource_depth(row["counts"], row["documents"]["ocr"])
            filled = " ".join("★" * depth)
            empty = " ".join("☆" * (5 - depth))
            stars = label(
                f'<span style="font-size:20px; color:{color("definition")}">{filled}</span>'
                f'<span style="font-size:20px; color:{color("text_muted")}"> {empty}</span>'
            )
            stars.setAccessibleName(f"Глубина языковой базы: {depth} из 5")
            stars.setToolTip(DEPTH_INFO)
            inner.addWidget(stars)
            button = QPushButton("Подробнее", objectName="languageDetailsButton")
            button.setMinimumHeight(32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, r=row, c=card: self.show_details(r, snapshot, c))
            inner.addWidget(button)
            grid.addWidget(card, index // 3, index % 3)

    def show_details(self, row, snapshot, card):
        dialog = getattr(card, "details_dialog", None)
        if dialog is None:
            dialog = make_details(row, snapshot, card)
            card.details_dialog = dialog
        dialog.open()


def make_details(row, snapshot, parent):
    details = QWidget(objectName="languageDetails")
    details_layout = QVBoxLayout(details)
    details_layout.setContentsMargins(0, 6, 0, 0)
    details_layout.setSpacing(8)
    docs = row["documents"]
    details_layout.addWidget(label(f'Документы: DOCX {"✓" if docs["docx"] else "—"} · PDF {"✓" if docs["native_pdf"] else "—"}'))
    ocr = label("OCR: поддерживается" if docs["ocr"] else "OCR: не заявлено")
    if not docs["ocr"]:
        ocr.setToolTip("Для этого языка OCR ещё не прошёл отдельную visual/script QA.")
    details_layout.addWidget(ocr)
    for metric, title in RESOURCE_LABELS.items():
        value = row["counts"][metric]
        previous, version = previous_metric(snapshot, row["code"], metric)
        if value is None:
            text = f"{escape(title)}: {count_text(value)}"
        elif previous is None:
            text = (f"{escape(title)}: {count_text(value)}<br>"
                    f'<span style="color:{color("text_secondary")}">'
                    f'{escape(snapshot["version"])} · Первый зафиксированный снимок</span>')
        else:
            text = (f"{escape(title)}: {trend_html(previous, value)}<br>"
                    f'<span style="color:{color("text_secondary")}">'
                    f'{escape(version)} → {escape(snapshot["version"])}</span>')
        details_layout.addWidget(label(text, "languageResourceMetric"))
    details_layout.addWidget(label(
        f'Код: {row["code"]} · Auto Detect: {"да" if row["auto_detect"] else "не заявлено"}\n'
        + "\nТехнические записи учитываются по исходному языку; повторения между областями не являются уникальными словами.",
        "secondary"))
    dialog = QDialog(parent)
    dialog.setObjectName("languageDetailsDialog")
    dialog.setWindowTitle(" / ".join(row["labels"]))
    dialog_layout = QVBoxLayout(dialog)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(details)
    dialog_layout.addWidget(scroll)
    close = QPushButton("Закрыть")
    close.clicked.connect(dialog.accept)
    dialog_layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
    available = parent.screen().availableGeometry()
    dialog.resize(min(720, available.width() - 80), min(740, available.height() - 80))
    return dialog
