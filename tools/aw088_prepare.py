"""Read-only RAR audit, bounded local ZIP conversion and native corpus inventory.

Developer utility: WinRAR/rarfile are not production runtime dependencies.
No archive-controlled program is executed. No target knowledge is generated.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from time import perf_counter
from zipfile import ZipFile, ZipInfo, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.documents.zip_archive import ArchiveLimits, digest, validate_members
from app.documents.control import JobControl
from tools.knowledge_harvester.corpus import texts

QA = ROOT / 'qa/aw088'
SOURCE = Path(r'C:\Users\PC\Downloads\2022_USER_REPAIR_MAINTENANCE_DISASSEMBLE_(CN7C)_CHINA_koreacustom.ru.rar')
ZIP = SOURCE.with_suffix('.zip')
UNRAR = r'C:\Program Files\WinRAR\UnRAR.exe'


def save(name, value):
    QA.mkdir(parents=True, exist_ok=True)
    (QA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def prepare():
    import rarfile
    QA.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    control = JobControl()
    source_hash = digest(SOURCE, control)
    with rarfile.RarFile(SOURCE) as rar:
        entries = rar.infolist()
    infos = []
    for entry in entries:
        if entry.is_symlink() or getattr(entry, 'file_redir', None):
            raise ValueError('RAR link/redirection rejected')
        info = ZipInfo(entry.filename.rstrip('/') + ('/' if entry.isdir() else ''))
        info.orig_filename = entry.filename
        # RAR directory names already end in slash; no lossy normalization.
        if info.orig_filename != info.filename:
            raise ValueError('RAR directory spelling mismatch')
        info.file_size, info.compress_size = entry.file_size, entry.compress_size
        info.flag_bits = int(entry.needs_password())
        info.external_attr = ((0o40755 if entry.isdir() else 0o100644) << 16)
        infos.append(info)
    if SOURCE.stat().st_size > ArchiveLimits().archive_bytes:
        raise ValueError('compressed RAR budget')
    members = validate_members(infos, control=control)
    inventory = dict(source=str(SOURCE), format='RAR5', bytes=SOURCE.stat().st_size,
        sha256_before=source_hash, entries=len(entries), unpacked_bytes=sum(e.file_size for e in entries),
        largest_member=max(e.file_size for e in entries), max_depth=max(len(e.filename.rstrip('/').split('/')) for e in entries),
        extensions=dict(Counter(Path(e.filename).suffix.lower() for e in entries if not e.isdir())),
        encrypted=False, solid=rarfile.RarFile(SOURCE).is_solid(),
        largest=sorted([dict(member=e.filename, bytes=e.file_size) for e in entries], key=lambda x:x['bytes'], reverse=True)[:20])
    save('archive_inventory.json', inventory)
    save('archive_security.json', dict(metadata='PASS', paths=len(members), links=0, encrypted=0,
        duplicate_names=0, limits=vars(ArchiveLimits()), crc='PENDING_STREAM', conversion='ZIP_STORED; original immutable'))
    # Stream every file in archive order once. UnRAR checks CRC and its exit code
    # is mandatory; stdout has file bytes only with -inul. Never extract by name.
    temporary = ZIP.with_name('.treetranslate-aw088-input.zip')
    if ZIP.exists():
        raise FileExistsError('Conversion already exists; use existing evidence rather than overwrite')
    con = sqlite3.connect(QA / 'native_corpus.db')
    con.execute('CREATE TABLE IF NOT EXISTS documents(member TEXT PRIMARY KEY, sha256 TEXT, size INTEGER, payload TEXT)')
    process = subprocess.Popen([UNRAR, 'p', '-inul', '-p-', str(SOURCE)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    done = pages = native = 0
    try:
        with ZipFile(temporary, 'w', compression=ZIP_STORED, allowZip64=True) as archive:
            for index, member in enumerate(members):
                if member.directory:
                    archive.writestr(member.name, b'')
                    continue
                remaining = member.size
                # Current corpus max 8.4 MB; retain native PDF bytes only within
                # a strict 16 MiB developer parsing budget, never the full archive.
                capture = Path(member.name).suffix.lower() == '.pdf' and member.size <= 16 * 1024 * 1024
                data = bytearray() if capture else None
                value = sha256()
                with archive.open(member.name, 'w', force_zip64=True) as output:
                    while remaining:
                        block = process.stdout.read(min(1024 * 1024, remaining))
                        if not block:
                            raise ValueError('RAR stream truncated')
                        remaining -= len(block)
                        value.update(block)
                        output.write(block)
                        if capture:
                            data.extend(block)
                payload = dict(member=member.name, sha256=value.hexdigest(), bytes=member.size, native=True,
                    source_origin='USER_PROVIDED', permission='CANDIDATES_ONLY', corpus_id='CN7C_2022_REPAIR_MAINTENANCE')
                if capture:
                    try:
                        import pypdfium2 as pdfium
                        with pdfium.PdfDocument(bytes(data)) as doc:
                            payload['pages'] = len(doc)
                        lines = texts(bytes(data), '.pdf')
                        if sum(map(len, lines)) > 8_000_000:
                            raise ValueError('native text budget')
                        payload['lines'] = lines
                        payload['native_chars'] = sum(map(len, lines))
                        pages += payload['pages']
                        native += bool(payload['native_chars'])
                    except Exception as error:
                        payload['parse_error'] = type(error).__name__
                con.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?)',
                    (member.name, value.hexdigest(), member.size, json.dumps(payload, ensure_ascii=False)))
                done += 1
                if done % 500 == 0:
                    con.commit()
                    print(json.dumps(dict(files=done, pages=pages, native_documents=native, seconds=round(perf_counter()-started, 2))), flush=True)
        if process.stdout.read(1):
            raise ValueError('Unexpected extra RAR stream bytes')
        if process.wait() != 0:
            raise ValueError('RAR CRC/extraction failure')
        con.commit()
        after = digest(SOURCE, control)
        if after != source_hash:
            raise ValueError('Source changed')
        temporary.rename(ZIP)
        inventory.update(sha256_after=after, immutable=True, converted_zip=str(ZIP),
            zip_bytes=ZIP.stat().st_size, zip_sha256=digest(ZIP, control))
        save('archive_inventory.json', inventory)
        save('archive_security.json', dict(metadata='PASS', crc='PASS', paths=len(members), links=0,
            encrypted=0, duplicate_names=0, limits=vars(ArchiveLimits()), source_immutable=True,
            conversion='ZIP_STORED, ZIP64 member headers; local only; original RAR retained'))
        save('prepare_timings.json', dict(seconds=perf_counter()-started, files=done, pages=pages, native_documents=native))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
        process.stdout.close()
        con.close()


if __name__ == '__main__':
    prepare()
