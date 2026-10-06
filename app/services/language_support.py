"""Small generated, offline presentation snapshot; no model or database loading."""
import json

from app.config.paths import ASSETS_DIR

RESOURCE_LABELS = {
    "technical_entries": "Техническая база · записи по областям",
    "dictionary_entries": "Словарь · статьи",
    "bilingual_entries": "Двуязычный словарь · записи",
    "usage_examples": "Примеры использования · предложения",
}
DEPTH_INFO = (
    "Уровень показывает глубину дополнительных языковых ресурсов TreeTranslate "
    "и не является оценкой качества базового машинного перевода."
)


def load_support():
    return json.loads((ASSETS_DIR / "language-support.json").read_text(encoding="utf-8"))


def resource_depth(counts, ocr):
    """One starting star, then one per resource family (not volume or quality)."""
    return 1 + sum((bool(ocr), bool(counts.get("technical_entries")),
                    bool(counts.get("dictionary_entries") or counts.get("bilingual_entries")),
                    bool(counts.get("usage_examples"))))


def previous_metric(snapshot, code, metric):
    for historical in reversed(snapshot["history"]):
        value = historical["counts"].get(code, {}).get(metric)
        if value is not None:
            return value, historical["version"]
    return None, None


def trend(previous, current):
    if previous is None or current is None:
        return None, "neutral"
    delta = current - previous
    return delta, "positive" if delta > 0 else "negative" if delta < 0 else "neutral"


def count_text(value):
    return f"{value:,}".replace(",", " ") if value is not None else "Отдельная база не добавлена"
