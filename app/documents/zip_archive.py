"""ZIP input contracts, bounded extraction and validated no-clobber publication."""
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path, PurePosixPath
import logging
import os
import re
import stat
import unicodedata
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED

from app.documents.errors import DocumentError, SourceChangedError
from app.documents.pdf_diagnostics import timed_stage

logger = logging.getLogger('treetranslate.documents.archive')


@dataclass(frozen=True)
class ArchiveLimits:
    members: int = 100000
    archive_bytes: int = 4 * 1024 * 1024 * 1024
    total_bytes: int = 16 * 1024 * 1024 * 1024
    member_bytes: int = 2 * 1024 * 1024 * 1024
    compression_ratio: int = 200
    path_chars: int = 1024
    depth: int = 32


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    size: int
    directory: bool


def digest(path, control):
    value = sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            control.checkpoint()
            value.update(block)
    return value.hexdigest()


def safe_member(name, limits=ArchiveLimits()):
    if (not name or len(name) > limits.path_chars or '\\' in name or name.startswith('/')
            or any(ord(c) < 32 for c in name)):
        raise DocumentError('ZIP содержит небезопасный путь. Архив не обработан.')
    parts = name.rstrip('/').split('/')
    if len(parts) > limits.depth:
        raise DocumentError('ZIP превышает допустимую глубину каталогов.')
    for part in parts:
        if (not part or part in {'.', '..'} or part.endswith((' ', '.'))
                or re.search(r'[<>:"|?*]', part)
                or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', part, re.I)):
            raise DocumentError('ZIP содержит небезопасное имя. Архив не обработан.')
    return '/'.join(parts)


def validate_members(infos, limits=ArchiveLimits(), control=None):
    if not infos or len(infos) > limits.members:
        raise DocumentError('ZIP пуст или превышает допустимое число записей.')
    members, names, files = [], set(), set()
    total = 0
    for info in infos:
        if control:
            control.checkpoint()
        if info.flag_bits & 1:
            raise DocumentError('Зашифрованные ZIP пока не поддерживаются.')
        if info.orig_filename != info.filename:
            raise DocumentError('ZIP содержит повреждённое имя записи.')
        name = safe_member(info.filename, limits)
        key = unicodedata.normalize('NFC', name).casefold()
        if key in names:
            raise DocumentError('ZIP содержит повторяющиеся пути.')
        names.add(key)
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind not in {0, stat.S_IFREG, stat.S_IFDIR} or info.external_attr & 0x400:
            raise DocumentError('ZIP содержит ссылку или специальный файл.')
        directory = info.is_dir()
        if (kind == stat.S_IFDIR and not directory) or (directory and info.file_size):
            raise DocumentError('ZIP содержит некорректную запись каталога.')
        if not directory:
            files.add(key)
        total += info.file_size
        if (info.file_size > limits.member_bytes or total > limits.total_bytes
                or info.file_size > max(1, info.compress_size) * limits.compression_ratio):
            raise DocumentError('ZIP превышает лимиты размера или сжатия.')
        members.append(ArchiveMember(info.filename, info.file_size, directory))
    for key in names:
        parts = key.split('/')
        if any('/'.join(parts[:i]) in files for i in range(1, len(parts))):
            raise DocumentError('ZIP содержит конфликт файла и каталога.')
    return tuple(members)


def inventory(path, control, limits=ArchiveLimits(), verify_crc=True, validation_stage='archive_validate_input', progress=None):
    try:
        if Path(path).stat().st_size > limits.archive_bytes:
            raise DocumentError('ZIP превышает лимиты размера или сжатия.')
        with timed_stage('archive_open'), ZipFile(path, 'r') as archive:
            with timed_stage(validation_stage):
                control.checkpoint()
                members = validate_members(archive.infolist(), limits, control)
                if verify_crc:
                    for index, member in enumerate(members, 1):
                        control.checkpoint()
                        if progress:
                            progress(index, len(members))
                        if member.directory:
                            continue
                        with archive.open(member.name) as stream:
                            size = 0
                            while block := stream.read(1024 * 1024):
                                control.checkpoint()
                                size += len(block)
                                if size > member.size:
                                    raise DocumentError('ZIP содержит некорректный размер записи.')
                            if size != member.size:
                                raise DocumentError('ZIP содержит некорректный размер записи.')
                return members
    except (BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError):
        raise DocumentError('Не удалось открыть ZIP: архив повреждён или имеет неподдерживаемую структуру.') from None


def extract(path, root, members, control, archive=None):
    from contextlib import nullcontext
    root = Path(root).resolve()
    with timed_stage('archive_extract'), (nullcontext(archive) if archive else ZipFile(path, 'r')) as archive:
        for member in members:
            control.checkpoint()
            target = root.joinpath(*PurePosixPath(member.name).parts).resolve()
            if not target.is_relative_to(root):
                raise DocumentError('Небезопасная распаковка ZIP остановлена.')
            if member.directory:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member.name) as source, target.open('xb') as output:
                size = 0
                while block := source.read(1024 * 1024):
                    control.checkpoint()
                    size += len(block)
                    if size > member.size:
                        raise DocumentError('ZIP содержит некорректный размер записи.')
                    output.write(block)
                if size != member.size:
                    raise DocumentError('ZIP содержит некорректный размер записи.')


def append_file(archive, path, name, control):
    """Append one validated document without retaining previous member payloads."""
    safe_member(name)
    with Path(path).open('rb') as source, archive.open(name, 'w', force_zip64=True) as output:
        while block := source.read(1024 * 1024):
            control.checkpoint()
            output.write(block)


def disk_budget(members, archive_bytes=None):
    """Output estimate plus one working document, rendering and reserve.

    The output estimate uses input compression plus per-document font/layout
    overhead. It is not an upper bound; ENOSPC still prevents publication.
    """
    total = sum(m.size for m in members)
    largest = max((m.size for m in members), default=0)
    # A translated PDF may add fonts and continuation pages. Rendering itself
    # is page-at-a-time; retain a fixed reserve rather than the entire corpus.
    documents = sum(not m.directory and Path(m.name).suffix.lower() in {'.pdf', '.docx'} for m in members)
    output = int((archive_bytes if archive_bytes is not None else total) * 1.5) + documents * 128 * 1024 + len(members) * 1024
    render = max(256 * 1024 * 1024, largest * 2)
    reserve = 512 * 1024 * 1024
    return dict(output=output, working_member=largest, rendering=render,
                reserve=reserve, required=output + largest + render + reserve)


def check_disk(members, output_parent, workspace_parent, archive_bytes=None):
    import shutil
    budget = disk_budget(members, archive_bytes)
    output_parent, workspace_parent = Path(output_parent).resolve(), Path(workspace_parent).resolve()
    same_volume = output_parent.anchor.casefold() == workspace_parent.anchor.casefold()
    working = budget['working_member'] + budget['rendering']
    output_need = budget['output'] + budget['reserve'] + (working if same_volume else 0)
    if (shutil.disk_usage(output_parent).free < output_need
            or (not same_volume and shutil.disk_usage(workspace_parent).free < working + budget['reserve'])):
        raise DocumentError('Недостаточно свободного места для результата архива и временной обработки документа.')
    logger.info('archive_disk_budget output=%d working=%d rendering=%d reserve=%d same_volume=%s',
                budget['output'], budget['working_member'], budget['rendering'], budget['reserve'], same_volume)
    return budget


def pack(root, temporary, expected, control):
    # Caller owns this file through mkstemp, just like the document writer.
    with timed_stage('archive_pack'), ZipFile(temporary, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for name in expected:
            control.checkpoint()
            path = root.joinpath(*PurePosixPath(name).parts)
            if name.endswith('/'):
                archive.writestr(name, b'')
            else:
                with path.open('rb') as source, archive.open(name, 'w', force_zip64=True) as output:
                    while block := source.read(1024 * 1024):
                        control.checkpoint()
                        output.write(block)


def validate_output(path, expected, control):
    with timed_stage('archive_validate_output'):
        # These bytes were produced locally from an already bounded inventory.
        # Highly compressible copied assets are valid; size/depth limits still apply.
        members = inventory(path, control, replace(ArchiveLimits(), compression_ratio=1_000_000,
            archive_bytes=32 * 1024**3, total_bytes=32 * 1024**3, member_bytes=4 * 1024**3),
            validation_stage='archive_validate_output_members')
        if set(m.name for m in members) != set(expected) or len(members) != len(expected):
            raise DocumentError('Проверка ZIP не пройдена: состав архива не совпадает с ожидаемым.')


def publish(temporary, destination, source, source_hash, control):
    with timed_stage('archive_publish'):
        for collision in range(10000):
            final = destination if not collision else destination.with_stem(f'{destination.stem} ({collision})')
            if final.exists() or final == source:
                continue
            def action():
                if digest(source, control) != source_hash:
                    raise SourceChangedError()
                if os.name == 'nt':
                    os.rename(temporary, final)
                else:
                    os.link(temporary, final)
                    temporary.unlink()
            try:
                control.publish(action)
            except FileExistsError:
                continue
            return final
    raise DocumentError('Не удалось выбрать свободное имя ZIP.')
