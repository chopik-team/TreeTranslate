from pathlib import Path
from contextlib import closing
import os
import sqlite3
import tempfile

from .database import SCHEMA_VERSION
from .errors import InvalidMemoryData


def integrity(database):
    with database.connect() as con:
        return [r[0] for r in con.execute('PRAGMA integrity_check')]


def duplicates(database):
    with database.connect() as con:
        return [dict(row) for row in con.execute('''SELECT source_language,target_language,domain,count(*) AS count
            FROM units GROUP BY source_language,target_language,source_normalized,target_text,domain,context,is_template
            HAVING count(*)>1''')]


def optimize(database, *, vacuum=False):
    if database.readonly:
        raise InvalidMemoryData('Встроенную память изменять нельзя.')
    with database.connect() as con:
        con.commit()
        con.execute('PRAGMA optimize')
        if vacuum:
            con.execute('VACUUM')


def backup(database, destination):
    destination = Path(destination)
    if destination.resolve() == database.path.resolve():
        raise InvalidMemoryData('Резервная копия должна иметь отдельный путь.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.tm-backup-', dir=destination.parent)
    os.close(fd)
    try:
        with database.connect() as source:
            with closing(sqlite3.connect(name)) as target:
                source.backup(target)
        os.replace(name, destination)
    finally:
        Path(name).unlink(missing_ok=True)


def restore(database, source_path):
    """Validate first, keep a pre-restore backup, then use SQLite's atomic backup API."""
    if database.readonly or Path(source_path).resolve() == database.path.resolve():
        raise InvalidMemoryData('Недопустимое восстановление памяти.')
    source = sqlite3.connect(Path(source_path).resolve().as_uri()+'?mode=ro', uri=True)
    try:
        source.execute('PRAGMA trusted_schema=OFF')
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or source.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
            raise InvalidMemoryData('Резервная копия повреждена или имеет другую версию.')
        source.execute('SELECT source_hash,normalized_hash,status FROM units LIMIT 1')
        source.execute('SELECT revision FROM metadata')
        source.execute('SELECT pair,key,unit_id FROM fuzzy_keys LIMIT 1')
        with database.lock:
            # Never replace a live WAL file with a copied database file.
            with tempfile.NamedTemporaryFile(prefix='tm-before-restore-', suffix='.db',
                                              dir=database.path.parent, delete=False) as stream:
                previous = Path(stream.name)
            backup(database, previous)
            with database.connect(write=True) as target:
                revision = target.execute('SELECT revision FROM metadata').fetchone()[0]
                target.commit()
                source.backup(target)
                target.execute('UPDATE metadata SET revision=max(revision,?)+1', (revision,))
        return previous
    finally:
        source.close()
