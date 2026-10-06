from contextlib import contextmanager
from pathlib import Path
from threading import RLock,local
import sqlite3
import os
from .errors import GlossaryUnavailable

VERSION=1
_INITIALIZATION_LOCK=RLock()
SCHEMA=[
'''CREATE TABLE entries(id INTEGER PRIMARY KEY,source_term TEXT NOT NULL,target_term TEXT NOT NULL,
 source_language TEXT NOT NULL,target_language TEXT NOT NULL,source_normalized TEXT NOT NULL,
 domain TEXT NOT NULL,context TEXT NOT NULL,priority INTEGER NOT NULL,case_sensitive INTEGER NOT NULL,
 whole_word INTEGER NOT NULL,status TEXT NOT NULL,origin TEXT NOT NULL,trust REAL NOT NULL,
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,notes TEXT NOT NULL,source_pack TEXT NOT NULL,
 provenance TEXT NOT NULL,mode TEXT NOT NULL,variants TEXT NOT NULL,forbidden_target_variants TEXT NOT NULL,
 UNIQUE(source_language,target_language,source_normalized,target_term,domain,context,case_sensitive,whole_word,mode))''',
'''CREATE TABLE aliases(pair TEXT NOT NULL,domain TEXT NOT NULL,hash TEXT NOT NULL,entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
 term TEXT NOT NULL,PRIMARY KEY(pair,domain,hash,entry_id,term)) WITHOUT ROWID''',
'''CREATE TABLE lengths(pair TEXT NOT NULL,domain TEXT NOT NULL,length INTEGER NOT NULL,PRIMARY KEY(pair,domain,length)) WITHOUT ROWID''',
'''CREATE TABLE suppressions(pair TEXT NOT NULL,domain TEXT NOT NULL,source TEXT NOT NULL,PRIMARY KEY(pair,domain,source)) WITHOUT ROWID''',
'''CREATE TABLE packs(pack_id TEXT PRIMARY KEY,version TEXT NOT NULL,path TEXT NOT NULL,enabled INTEGER NOT NULL,manifest TEXT NOT NULL)''',
'CREATE INDEX glossary_pair ON entries(source_language,target_language,domain,status)',
'CREATE TABLE metadata(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)',
'INSERT INTO metadata VALUES(1,0)',
]
for table in ('entries','suppressions','packs'):
    for action in ('INSERT','UPDATE','DELETE'):
        SCHEMA.append(f'CREATE TRIGGER rev_{table}_{action} AFTER {action} ON {table} BEGIN UPDATE metadata SET revision=revision+1; END')


class Database:
    def __init__(self,path,*,readonly=False,timeout_ms=250,persistent_reads=False):
        self.path=Path(path);self.readonly=readonly;self.timeout_ms=timeout_ms
        self.lock=RLock();self.ready=False
        self.persistent_reads=persistent_reads;self._local=local()
        self._path_key=None;self._absolute_path=None

    def identity(self):
        info=self.path.stat()
        path_key=self.path,os.getcwd() if not self.path.is_absolute() else ''
        if path_key!=self._path_key:
            self._absolute_path=str(self.path.absolute());self._path_key=path_key
        return self._absolute_path,info.st_dev,info.st_ino

    def close(self):
        """Close only this thread's handle; never share a SQLite connection."""
        con=getattr(self._local,'connection',None)
        self._local.connection=None
        self._local.revision_cache=None
        if con is not None:con.close()

    def _open(self):
        if not self.readonly:self.path.parent.mkdir(parents=True,exist_ok=True)
        con=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=self.timeout_ms/1000) if self.readonly else sqlite3.connect(self.path,timeout=self.timeout_ms/1000)
        try:
            con.row_factory=sqlite3.Row
            con.execute('PRAGMA foreign_keys=ON');con.execute('PRAGMA trusted_schema=OFF')
            con.execute(f'PRAGMA busy_timeout={int(self.timeout_ms)}')
            if not self.ready:self.initialize(con)
        except BaseException:
            con.close();raise
        return con

    def revision_state(self):
        """Observe external commits without reopening a read transaction.

        SQLite data_version belongs to this thread's persistent connection.
        Revision is read in the original transaction whenever that version or
        the file identity changes. Writes on this handle invalidate below.
        """
        if not self.persistent_reads:
            with self.connect() as con:return self.identity(),con.execute('SELECT revision FROM metadata').fetchone()[0]
        with self.lock:
            con=getattr(self._local,'connection',None)
            try:identity=self.identity() if self.path.exists() else None
            except OSError:
                self.close()
                raise GlossaryUnavailable('Глоссарий недоступен. Перевод без него остаётся доступен.') from None
            if con is None or con.in_transaction or self._local.identity!=identity:
                with self.connect() as current:
                    revision=current.execute('SELECT revision FROM metadata').fetchone()[0]
                con=getattr(self._local,'connection',None)
                if con is None or con.in_transaction:return self.identity(),revision
                identity=self._local.identity
            try:
                version=con.execute('PRAGMA data_version').fetchone()[0]
                token=identity,self._local.epoch,version
                cached=getattr(self._local,'revision_cache',None)
                if cached is None or cached[0]!=token:
                    with self.connect() as current:revision=current.execute('SELECT revision FROM metadata').fetchone()[0]
                    self._local.revision_cache=token,revision
                return token,self._local.revision_cache[1]
            except (sqlite3.Error,OSError):
                self.close()
                raise GlossaryUnavailable('Глоссарий недоступен. Перевод без него остаётся доступен.') from None

    def initialize(self,con):
        # Serialize schema/WAL setup only, not normal reads and imports.
        # Reopening a v1 database must not acquire an unnecessary writer lock.
        with _INITIALIZATION_LOCK:
            version=con.execute('PRAGMA user_version').fetchone()[0]
            if version>VERSION or self.readonly and version!=VERSION:
                raise GlossaryUnavailable('Версия глоссария не поддерживается.')
            if not self.readonly and version==0:
                con.execute('PRAGMA journal_mode=WAL');con.execute('PRAGMA synchronous=FULL')
                con.execute('BEGIN IMMEDIATE')
                version=con.execute('PRAGMA user_version').fetchone()[0]
                if version>VERSION:raise GlossaryUnavailable('Версия глоссария не поддерживается.')
                if version==0:
                    for sql in SCHEMA:con.execute(sql)
                    con.execute(f'PRAGMA user_version={VERSION}')
                con.commit()
            self.ready=True

    @contextmanager
    def connect(self,*,write=False):
        with self.lock:
            con=None;retained=False;changes_before=None
            try:
                if write and self.readonly:raise GlossaryUnavailable('Встроенный словарь доступен только для чтения.')
                if self.persistent_reads and not write:
                    con=getattr(self._local,'connection',None)
                    if con is not None and self._local.identity!=self.identity():
                        self.close();self.ready=False;con=None
                    if con is not None and con.in_transaction:con=None
                    elif con is not None:retained=True
                    if con is None and getattr(self._local,'connection',None) is None:
                        con=self._open();self._local.connection=con
                        self._local.epoch=getattr(self._local,'epoch',0)+1
                        self._local.identity=self.identity();retained=True
                if con is None:con=self._open()
                changes_before=con.total_changes
                con.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                yield con
                con.commit()
            except (sqlite3.Error,OSError):
                if con is not None and getattr(self._local,'connection',None) is con:self.close()
                raise GlossaryUnavailable('Глоссарий недоступен. Перевод без него остаётся доступен.') from None
            finally:
                if con and changes_before is not None and getattr(self._local,'connection',None) is con and con.total_changes!=changes_before:
                    self._local.revision_cache=None
                if con and not retained:con.close()
                elif con and getattr(self._local,'connection',None) is con and con.in_transaction:
                    con.rollback()
