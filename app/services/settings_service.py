from PySide6.QtCore import QSettings, QObject, Signal
from pathlib import Path

from app.config.settings import AppSettings, PerformanceSettings


class SettingsService(QObject):
    changed = Signal(str, object)
    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self._settings = settings or QSettings()

    def load(self) -> AppSettings:
        remember = self.value('general/remember_language', True, bool)
        return AppSettings(
            source_language=self._settings.value("language/source", "Определить автоматически") if remember else "Определить автоматически",
            target_language=self._settings.value("language/target", "Русский") if remember else "Русский",
            translation_mode="Автоматический",
            acceleration=self._settings.value("performance/device", "Auto"),
            translate_folders=self._settings.value("translation/translate_folders", True, bool),
            translate_filenames=self._settings.value("translation/translate_filenames", False, bool),
        )

    def save_value(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)
        self.changed.emit(key, value)

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
        # UI policy is automatic; explicit profiles remain available in the
        # developer request APIs. Ignore obsolete manual resource controls.
        device = str(self._settings.value('performance/device', 'Auto'))
        if device not in ('Auto', 'CPU', 'GPU'):
            device = 'Auto'
        self._settings.setValue('performance/device', device)
        self._settings.setValue('performance/mode', 'Автоматический')
        return PerformanceSettings(
            device=device,
        )

    def value(self, key: str, default: object, value_type=None):
        if value_type is None:
            return self._settings.value(key, default)
        if value_type is bool:
            value = self._settings.value(key, default)
            if isinstance(value, bool): return value
            if str(value).lower() in ('true','1'): return True
            if str(value).lower() in ('false','0'): return False
            return default
        try:
            return self._settings.value(key, default, value_type)
        except (ValueError, TypeError):
            return default
