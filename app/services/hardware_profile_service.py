from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import subprocess
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

from app.config.paths import APP_DATA_DIR


@dataclass(frozen=True)
class HardwareProfile:
    cpu: str
    logical_cores: int
    ram_gb: int
    gpu: str
    vram_gb: int = 0


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
        self.profile_path = profile_path or APP_DATA_DIR / "hardware_profile.json"

    def detect(self) -> HardwareProfile:
        return HardwareProfile(
            cpu=self._cpu_name(),
            logical_cores=os.cpu_count() or 1,
            ram_gb=self._ram_gb(),
            gpu=self._gpu_name(),
            vram_gb=self._vram_gb(),
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
            hardware = payload["hardware"]
            hardware.setdefault("vram_gb", 0)
            return HardwareProfile(**hardware)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def recommend(profile: HardwareProfile) -> HardwareRecommendation:
        has_gpu = profile.gpu != "Не определена"
        if profile.ram_gb >= 32 and has_gpu:
            mode, ram = "Турбо", "24 GB"
        elif profile.ram_gb >= 16:
            mode, ram = "Баланс", "12 GB"
        else:
            mode, ram = "Эконом", "6 GB" if profile.ram_gb >= 8 else "2 GB"
        target_threads = min(max(profile.logical_cores // 2, 2), 16)
        allowed_threads = (2, 4, 6, 8, 12, 16)
        threads = str(max(value for value in allowed_threads if value <= target_threads))
        return HardwareRecommendation(
            device="GPU" if has_gpu else "CPU",
            profile=mode,
            cpu_threads=threads,
            gpu_usage="Предпочтительно" if has_gpu else "Отключено",
            ram_limit=ram,
            vram_limit="Автоматически" if not profile.vram_gb else f"{max(1, profile.vram_gb - 2)} GB",
        )

    @staticmethod
    def _cpu_name() -> str:
        name = HardwareProfileService._powershell_value(
            "Get-CimInstance Win32_Processor | Where-Object { $_.Name } | "
            "Select-Object -First 1 -ExpandProperty Name"
        )
        return HardwareProfileService._normalize_device_name(
            name or platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", ""),
            "Не определён",
        )

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
        names = HardwareProfileService._powershell_value(command, multiple=True)
        return HardwareProfileService._normalize_device_name(names, "Не определена")

    @staticmethod
    def _vram_gb() -> int:
        # NVIDIA's driver tool reports dedicated memory accurately; WMI's
        # AdapterRAM is a 32-bit field and truncates modern cards above 4 GB.
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
            if values:
                return max(1, round(max(values) / 1024))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass

        value = HardwareProfileService._powershell_value(
            "Get-CimInstance Win32_VideoController | Where-Object { $_.AdapterRAM -gt 0 } | "
            "Measure-Object AdapterRAM -Maximum | Select-Object -ExpandProperty Maximum"
        )
        try:
            detected = max(0, round(int(value) / 1024**3))
            # 4 GB is also WMI's common overflow ceiling; do not present it as
            # a trustworthy value for a GPU that may have substantially more.
            return detected if 0 < detected < 4 else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_device_name(value: str, fallback: str) -> str:
        if not value or not value.strip():
            return fallback
        cleaned = re.sub(r"\((?:R|TM)\)", "", value, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+\d+-Core Processor$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+CPU(?:\s+Processor)?\s*(?:@.*)?$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
        return cleaned or fallback

    @staticmethod
    def _powershell_value(command: str, multiple: bool = False) -> str:
        if os.name != "nt":
            return ""
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
            return ", ".join(names) if multiple else (names[0] if names else "")
        except (OSError, subprocess.SubprocessError):
            return ""
