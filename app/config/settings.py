from dataclasses import dataclass


@dataclass(slots=True)
class AppSettings:
    source_language: str = "Определить автоматически"
    target_language: str = "Русский"
    translation_mode: str = "Автоматический"
    acceleration: str = "Auto"
    translate_folders: bool = True
