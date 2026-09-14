from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HardwareProfile:
    cpu: str
    logical_cores: int
    ram_gb: int
    gpu: str


@dataclass(frozen=True)
class HardwareRecommendation:
    device: str
    profile: str
    cpu_threads: str
    gpu_usage: str
    ram_limit: str
    vram_limit: str


class HardwareProfileService:
    def __init__(self, profile_path: Path | None = None) -> None:
        default_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CHOPIK Team" / "TreeTranslate"
        self.profile_path = profile_path or default_root / "hardware_profile.json"

    def detect(self) -> HardwareProfile:
        return HardwareProfile(
            cpu=self._cpu_name(),
            logical_cores=os.cpu_count() or 1,
            ram_gb=self._ram_gb(),
            gpu=self._gpu_name(),
        )

    def save(self, profile: HardwareProfile) -> None:
        recommendation = self.recommend(profile)
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "hardware": asdict(profile),
            "recommendation": asdict(recommendation),
        }
        self.profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> HardwareProfile | None:
        try:
            payload = json.loads(self.profile_path.read_text(encoding="utf-8"))
            return HardwareProfile(**payload["hardware"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def recommend(profile: HardwareProfile) -> HardwareRecommendation:
        has_gpu = profile.gpu != "Не определена"
        if profile.ram_gb >= 32 and has_gpu:
            mode, ram = "Турбо", "32 GB"
        elif profile.ram_gb >= 16:
            mode, ram = "Баланс", "16 GB"
        else:
            mode, ram = "Эконом", "8 GB" if profile.ram_gb >= 8 else "4 GB"
        target_threads = min(max(profile.logical_cores // 2, 2), 16)
        allowed_threads = (2, 4, 6, 8, 12, 16)
        threads = str(max(value for value in allowed_threads if value <= target_threads))
        return HardwareRecommendation(
            device="GPU" if has_gpu else "CPU",
            profile=mode,
            cpu_threads=threads,
            gpu_usage="Предпочтительно" if has_gpu else "Отключено",
            ram_limit=ram,
            vram_limit="Автоматически",
        )

    @staticmethod
    def _cpu_name() -> str:
        return os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor() or "Не определён"

    @staticmethod
    def _ram_gb() -> int:
        if os.name != "nt":
            return 0

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return max(1, round(status.total_physical / 1024**3))
        return 0

    @staticmethod
    def _gpu_name() -> str:
        if os.name != "nt":
            return "Не определена"
        command = (
            "Get-CimInstance Win32_VideoController | "
            "Where-Object { $_.Name } | Select-Object -ExpandProperty Name"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return ", ".join(names) if names else "Не определена"
        except (OSError, subprocess.SubprocessError):
            return "Не определена"
