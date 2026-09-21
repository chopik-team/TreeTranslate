from PySide6.QtCore import QSettings
from pathlib import Path

from app.config.settings import AppSettings, PerformanceSettings


class SettingsService:
    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings()

    def load(self) -> AppSettings:
        return AppSettings(
            source_language=self._settings.value("language/source", "Определить автоматически"),
            target_language=self._settings.value("language/target", "Русский"),
            translation_mode=self._settings.value("translation/mode", "Автоматический"),
            acceleration=self._settings.value("performance/device", "Auto"),
            translate_folders=self._settings.value("translation/translate_folders", True, bool),
            translate_filenames=self._settings.value("translation/translate_filenames", False, bool),
        )

    def save_value(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)

    def sync(self) -> None:
        self._settings.sync()

    def interface_theme(self) -> str:
        return str(self.value("interface/theme", "Тёмная"))

    def output_location(self) -> tuple[str, str]:
        mode = str(self.value("general/output_location", "near_original"))
        path = str(self.value("general/output_path", ""))
        # Compatibility with settings written by AW 0.2-alpha.
        if mode == "Рядом с оригиналом":
            mode = "near_original"
        elif mode == "Выбранная папка":
            mode = "custom"
        return mode, path

    def restore_job_enabled(self) -> bool:
        return self.value("general/restore_job", False, bool)

    def save_unfinished_job(self, paths) -> None:
        normalized = [str(Path(path).resolve()) for path in paths]
        self.save_value("job/unfinished", bool(normalized))
        self.save_value("job/source_paths", normalized)
        self.sync()

    def unfinished_job_paths(self) -> tuple[Path, ...]:
        if not self.restore_job_enabled() or not self.value("job/unfinished", False, bool):
            return ()
        stored = self.value("job/source_paths", [])
        if isinstance(stored, str):
            stored = [stored]
        return tuple(Path(value) for value in stored if value and Path(value).exists())

    def clear_unfinished_job(self) -> None:
        self._settings.remove("job/unfinished")
        self._settings.remove("job/source_paths")
        self.sync()

    def load_performance(self) -> PerformanceSettings:
        return PerformanceSettings(
            mode=str(self._settings.value("performance/mode", "Автоматический")),
            device=str(self._settings.value("performance/device", "Auto")),
            cpu_threads=str(self._settings.value("performance/cpu_threads", "Автоматически")),
            gpu_usage=str(self._settings.value("performance/gpu", "Автоматически")),
            ram_limit=str(self._settings.value("performance/ram", "Автоматически")),
            vram_limit=str(self._settings.value("performance/vram", "Автоматически")),
            unload_model=self._settings.value("performance/unload_model", True, bool),
            reduce_load=self._settings.value("performance/reduce_load", True, bool),
        )

    def value(self, key: str, default: object, value_type=None):
        if value_type is None:
            return self._settings.value(key, default)
        return self._settings.value(key, default, value_type)
