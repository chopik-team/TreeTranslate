"""Short-lived connections, atomic schema migration and revisioned data."""
from contextlib import contextmanager, nullcontext
from pathlib import Path
import sqlite3
from threading import RLock

from .errors import MemoryUnavailable


_PATH_LOCKS_GUARD = RLock()
_PATH_LOCKS: dict[Path, RLock] = {}


def _path_lock(path: Path) -> RLock:
    """Share a writer/initialization lock between database instances."""
    resolved = path.resolve()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(resolved, RLock())

SCHEMA_VERSION = 1
SCHEMA = [
    '''CREATE TABLE units (
        id INTEGER PRIMARY KEY, source_language TEXT NOT NULL, target_language TEXT NOT NULL,
        source_text TEXT NOT NULL, source_normalized TEXT NOT NULL, target_text TEXT NOT NULL,
        source_hash TEXT NOT NULL, normalized_hash TEXT NOT NULL,
        domain TEXT NOT NULL, context TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('CONFIRMED','IMPORTED','REVIEWED','AUTO','REJECTED')),
        quality REAL NOT NULL CHECK(quality BETWEEN 0 AND 1),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_used_at TEXT,
        use_count INTEGER NOT NULL DEFAULT 0, document_type TEXT NOT NULL DEFAULT '',
        source_document TEXT NOT NULL DEFAULT '', engine_origin TEXT NOT NULL DEFAULT '',
        confirmed_by_user INTEGER NOT NULL DEFAULT 0, is_template INTEGER NOT NULL DEFAULT 0,
        UNIQUE(source_language,target_language,source_normalized,target_text,domain,context,is_template))''',
    'CREATE INDEX tm_exact ON units(source_language,target_language,source_hash)',
    'CREATE INDEX tm_normalized ON units(source_language,target_language,normalized_hash)',
    'CREATE INDEX tm_domain ON units(domain,status)',
    'CREATE INDEX tm_status ON units(status)',
    'CREATE INDEX tm_last_used ON units(last_used_at)',
    '''CREATE TABLE fuzzy_keys (pair TEXT NOT NULL, key TEXT NOT NULL,
       unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
       PRIMARY KEY(pair,key,unit_id)) WITHOUT ROWID''',
    'CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL)',
    'INSERT INTO metadata VALUES (1,0)',
]
for action in ('INSERT', 'UPDATE', 'DELETE'):
    event = 'UPDATE OF status,confirmed_by_user,source_text,target_text,domain,context,quality' if action == 'UPDATE' else action
    SCHEMA.append(f'''CREATE TRIGGER tm_revision_{action.lower()} AFTER {event} ON units
                     BEGIN UPDATE metadata SET revision=revision+1 WHERE id=1; END''')


class Database:
    def __init__(self, path, *, readonly=False, timeout_ms=250):
        self.path = Path(path)
        self.readonly, self.timeout_ms = readonly, timeout_ms
        self.lock = RLock()
        self.path_lock = _path_lock(self.path)
        self.ready = False

    @contextmanager
    def connect(self, *, write=False):
        # SQLite serializes writers across processes.  This additional lock
        # prevents separate Database objects in this process from racing while
        # enabling WAL/migrating or beginning short write transactions.
        shared_lock = self.path_lock if write or not self.ready else nullcontext()
        with self.lock, shared_lock:
            con = None
            try:
                if self.readonly:
                    if write:
                        raise MemoryUnavailable('Встроенная память доступна только для чтения.')
                    con = sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True,
                                          timeout=self.timeout_ms/1000)
                else:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    con = sqlite3.connect(self.path, timeout=self.timeout_ms/1000)
                con.row_factory = sqlite3.Row
                con.execute('PRAGMA foreign_keys=ON')
                con.execute(f'PRAGMA busy_timeout={int(self.timeout_ms)}')
                con.execute('PRAGMA trusted_schema=OFF')
                if not self.ready:
                    version = con.execute('PRAGMA user_version').fetchone()[0]
                    if version > SCHEMA_VERSION or self.readonly and version != SCHEMA_VERSION:
                        raise MemoryUnavailable('Версия базы памяти не поддерживается.')
                    if not self.readonly:
                        con.execute('PRAGMA journal_mode=WAL')
                        con.execute('PRAGMA synchronous=FULL')
                        con.execute('BEGIN IMMEDIATE')
                        # Re-read under writer lock: another process may have migrated it.
                        version = con.execute('PRAGMA user_version').fetchone()[0]
                        if version == 0:
                            for sql in SCHEMA:
                                con.execute(sql)
                            con.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                        con.commit()
                    self.ready = True
                con.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                yield con
                con.commit()
            except (sqlite3.Error, OSError):
                if con:
                    con.rollback()
                raise MemoryUnavailable('Память переводов недоступна; перевод моделями остаётся доступен.') from None
            finally:
                if con:
                    con.close()
