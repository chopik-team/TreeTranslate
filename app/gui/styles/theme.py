from app.config.paths import STYLES_DIR

COLORS = {
    "background": "#0b100e",
    "panel": "#121a16",
    "panel_hover": "#18231d",
    "border": "#26352d",
    "text_primary": "#eef6f1",
    "text_secondary": "#8fa198",
    "accent_green": "#19a653",
    "danger_red": "#e85d68",
}


def load_stylesheet() -> str:
    stylesheet = (STYLES_DIR / "stylesheet.qss").read_text(encoding="utf-8")
    return stylesheet.format(**COLORS)
