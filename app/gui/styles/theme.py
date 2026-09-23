from app.config.paths import ICONS_DIR, STYLES_DIR, stylesheet_url

DARK_COLORS = {
    "background": "#0b100e",
    "background_start": "#09110e",
    "background_end": "#0c1512",
    "panel": "#121a16",
    "panel_alt": "#101713",
    "source_panel": "#0e1713",
    "example_card": "#141d18",
    "outline_panel": "#102018",
    "outline_hover": "#143222",
    "nav_panel": "#0d1512",
    "panel_soft": "#101a15",
    "panel_raised": "#19231e",
    "panel_hover": "#18231d",
    "panel_pressed": "#101713",
    "panel_disabled": "#121713",
    "panel_active": "#10271b",
    "drop_active": "#13271b",
    "drop_border_active": "#1b7540",
    "hover": "#1a2820",
    "selected": "#235f3a",
    "border": "#26352d",
    "border_strong": "#385044",
    "border_focus": "#416151",
    "text_primary": "#eef6f1",
    "text_secondary": "#8fa198",
    "text_muted": "#718078",
    "disabled": "#59665f",
    "accent_green": "#19a653",
    "accent": "#19a653",
    "accent_hover": "#20b960",
    "toggle_off": "#59645e",
    "danger_red": "#e85d68",
    "danger_hover": "#7c3037",
    "close_hover": "#c42b3a",
    "splitter": "#31463b",
    "splitter_hover": "#1bc869",
    "splitter_grip": "#17251e",
    "splitter_grip_hover": "#184b2d",
    "definition": "#d9b94f",
    "definition_panel": "#201e12",
    "info_hover": "#1a2a21",
    "control_hover": "#202923",
    "choice_selected": "#153d27",
    "popup": "#162019",
    "indicator_border": "#526359",
    "input": "#0f1612",
    "scroll_handle": "#35463d",
    "scroll_handle_hover": "#47705a",
    "alternate_row": "#111914",
    "row_hover": "#1a2620",
    "grid_line": "#1c2922",
    "header": "#0c120f",
    "menu": "#111a16",
    "menu_border": "#315040",
    "menu_selected": "#174c2c",
    "nav_selected": "#1d5e37",
    "tooltip_border": "#3d5a4b",
}


def color(name: str, theme_name: str = "Тёмная") -> str:
    """Return a named theme token for custom-painted controls."""
    return THEMES.get(theme_name, DARK_COLORS).get(name, DARK_COLORS["text_primary"])

THEMES = {"Тёмная": DARK_COLORS, "Системная": DARK_COLORS}


def load_stylesheet(theme_name: str = "Тёмная") -> str:
    stylesheet = (STYLES_DIR / "stylesheet.qss").read_text(encoding="utf-8")
    values = dict(THEMES.get(theme_name, DARK_COLORS))
    values.update(
        radio_unchecked_url=stylesheet_url(ICONS_DIR / "radio_unchecked.svg"),
        radio_checked_url=stylesheet_url(ICONS_DIR / "radio_checked.svg"),
        tree_check_url=stylesheet_url(ICONS_DIR / "tree-check.svg"),
        tree_partial_url=stylesheet_url(ICONS_DIR / "tree-partial.svg"),
    )
    return stylesheet.format(**values)
