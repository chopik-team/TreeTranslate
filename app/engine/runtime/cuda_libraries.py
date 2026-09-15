"""Load only locally installed CUDA DLLs on first GPU request."""
import os
from pathlib import Path
import sys
import sysconfig

_handles = []


def load_cuda_libraries() -> None:
    if sys.platform != "win32" or _handles:
        return
    import ctypes
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    roots = [bundle / "vendor" / "runtime" / "cuda",
             Path(sysconfig.get_paths()["purelib"]) / "nvidia" / "cublas" / "bin"]
    for root in roots:
        if (root / "cublas64_12.dll").is_file():
            directory = os.add_dll_directory(str(root))
            try:
                libraries = [ctypes.WinDLL(str(root / name)) for name in ("cublasLt64_12.dll", "cublas64_12.dll")]
            except OSError:
                directory.close()
                raise
            _handles.extend([directory, *libraries])
            return
    # A system CUDA installation can still satisfy CT2's native loader.
