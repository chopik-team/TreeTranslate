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
    archive: Path | None = None
    archive_hash: str = ''


@dataclass(frozen=True)
class ScanResult:
    files: tuple[SourceFile, ...]
    skipped: tuple[Path, ...] = ()


def scan_sources(paths, control: JobControl, progress=None) -> ScanResult:
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
    def add_archive(path):
        from app.documents.zip_archive import inventory, digest
        from app.documents.pdf_diagnostics import timed_stage
        resolved = path.resolve(strict=True)
        if resolved in seen:
            return
        seen.add(resolved)
        if progress:
            progress(0, 0)
        source_hash = digest(resolved, control)
        with timed_stage('archive_scan'):
            members = inventory(resolved, control, progress=progress)
            supported = [m for m in members if not m.directory and Path(m.name).suffix.lower() in {'.pdf', '.docx'}]
            from app.documents.run_metrics import observe
            observe('archive_event','scan',source=str(resolved),source_sha256=source_hash,scanned_members=len(members),
                accepted_members=len(supported),skipped_members=len(members)-len(supported),crc_status='PASS')
            for member in supported:
                relative = Path(member.name)
                files.append(SourceFile(resolved / relative, resolved, relative, member.size, resolved, source_hash))
            if not supported:
                files.append(SourceFile(resolved, None, Path(resolved.name), resolved.stat().st_size, resolved, source_hash))
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
                if path.suffix.lower() == '.zip':
                    add_archive(path)
                else:
                    add(path, None)
            else:
                raise DocumentError("Выбранный файл или каталог недоступен.")
    except OSError:
        raise DocumentError("Не удалось прочитать выбранные файлы или каталоги.") from None
    return ScanResult(tuple(files), tuple(skipped))
