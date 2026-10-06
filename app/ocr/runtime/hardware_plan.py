"""Resource ceilings only: no models, thresholds, DPI, ranking or thread tuning."""
from dataclasses import dataclass, asdict
import os
from pathlib import Path
import subprocess
import psutil

GIB = 1024**3
MIB = 1024**2


@dataclass(frozen=True)
class OCRCapabilities:
    ram_total: int
    ram_available: int
    logical_threads: int
    cuda: bool = False
    vram_total: int = 0
    vram_available: int = 0

    @classmethod
    def detect(cls, device):
        memory = psutil.virtual_memory()
        total = free = 0
        executable = Path(os.environ.get('WINDIR', 'C:/Windows'))/'System32/nvidia-smi.exe'
        if device == 'gpu' and executable.is_file():
            try:
                result = subprocess.run([str(executable), '--query-gpu=memory.total,memory.free',
                    '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode == 0:
                    total, free = [int(float(v.strip())*MIB) for v in result.stdout.splitlines()[0].split(',')]
            except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
                pass
        return cls(memory.total, memory.available, os.cpu_count() or 1,
                   device == 'gpu' and total > 0, total, free)


@dataclass(frozen=True)
class OCRHardwarePlan:
    resident_models: int
    resident_ram_bytes: int
    resident_vram_bytes: int
    result_cache_bytes: int
    prepared_region_bytes: int
    ram_reserve_bytes: int
    vram_reserve_bytes: int
    batch_ceiling: int | None = None  # Unproved batch changes are not enabled.

    @classmethod
    def from_capabilities(cls, c):
        ram_total = max(0, c.ram_total); available = min(ram_total, max(0, c.ram_available))
        ram_reserve = min(ram_total, max(2*GIB, int(ram_total*.15)))
        usable_ram = max(0, available-ram_reserve)
        ram_budget = min(int(ram_total*.35), usable_ram)
        total = max(0, c.vram_total); free = min(total, max(0, c.vram_available))
        gpu_reserve = min(total, max(512*MIB, int(total*.15))) if c.cuda else 0
        gpu_budget = min(int(total*.65), max(0, free-gpu_reserve)) if c.cuda else 0
        models = (4 if ram_total >= 32*GIB and gpu_budget >= 3*GIB else
                  2 if ram_total >= 16*GIB and gpu_budget >= GIB else 1)
        return cls(models, ram_budget, gpu_budget,
                   min(256*MIB, usable_ram//100), min(128*MIB, usable_ram//50),
                   ram_reserve, gpu_reserve)

    def as_dict(self):
        return asdict(self)
