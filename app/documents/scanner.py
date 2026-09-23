from dataclasses import dataclass
import os
from pathlib import Path

from app.documents.control import JobControl
from app.documents.errors import DocumentError


@dataclass(frozen=True)
class SourceFile:
    path: Path
    root: Path | None
    relative: Path
    size: int


@dataclass(frozen=True)
class ScanResult:
    files: tuple[SourceFile, ...]
    skipped: tuple[Path, ...] = ()


def scan_sources(paths, control: JobControl) -> ScanResult:
    files, skipped, seen = [], [], set()
    def add(path, root):
        control.checkpoint()
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            skipped.append(path)
            return
        hidden = bool(getattr(path.stat(), "st_file_attributes", 0) & 0x2)
        service_name = path.name.startswith(("~$", ".", ".treetranslate-"))
        if path.suffix.lower() not in {".docx", ".pdf"} or hidden or service_name:
            skipped.append(path)
            return
        resolved = path.resolve(strict=True)
        if resolved not in seen:
            seen.add(resolved)
            files.append(SourceFile(resolved, root, resolved.relative_to(root) if root else Path(path.name), resolved.stat().st_size))
    try:
        # Directories first make nested/repeated selections deterministic and preserve hierarchy.
        for path in sorted((Path(p).absolute() for p in paths), key=lambda p: (not p.is_dir(), len(p.parts), str(p).casefold())):
            control.checkpoint()
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                skipped.append(path)
            elif path.is_dir():
                root = path.resolve(strict=True)
                for parent, directories, names in os.walk(root, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)):
                    control.checkpoint()
                    directories[:] = sorted(d for d in directories if not (Path(parent) / d).is_symlink()
                                            and not (hasattr(Path(parent) / d, "is_junction") and (Path(parent) / d).is_junction()))
                    for name in sorted(names):
                        add(Path(parent) / name, root)
            elif path.is_file():
                add(path, None)
            else:
                raise DocumentError("Выбранный файл или каталог недоступен.")
    except OSError:
        raise DocumentError("Не удалось прочитать выбранные файлы или каталоги.") from None
    return ScanResult(tuple(files), tuple(skipped))
