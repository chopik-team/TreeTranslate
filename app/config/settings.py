from dataclasses import dataclass


@dataclass(slots=True)
class AppSettings:
    source_language: str = "Определить автоматически"
    target_language: str = "Русский"
    translation_mode: str = "Автоматический"
    acceleration: str = "Auto"
    translate_folders: bool = True
    translate_filenames: bool = False


@dataclass(slots=True)
class PerformanceSettings:
    mode: str = "Автоматический"
    device: str = "Auto"
    cpu_threads: str = "Автоматически"
    gpu_usage: str = "Автоматически"
    ram_limit: str = "Автоматически"
    vram_limit: str = "Автоматически"
    unload_model: bool = True
    reduce_load: bool = True


@dataclass(slots=True)
class TranslationJobConfig:
    """UI-side contract to be passed to the future Translation Engine."""

    translate_directories: bool = True
    translate_filenames: bool = False
