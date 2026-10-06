from contextlib import contextmanager
from pathlib import Path
import sqlite3
from .models import HarvestError
from .provenance import canonical_json
from .licenses import validate_source

SCHEMA = '''
CREATE TABLE sources(id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
CREATE TABLE files(hash TEXT,source TEXT,adapter TEXT,path TEXT,offset INTEGER DEFAULT 0,records INTEGER DEFAULT 0,
 config TEXT,complete INTEGER DEFAULT 0,PRIMARY KEY(hash,source));
CREATE TABLE raw_records(source TEXT,record_id TEXT,concept_id TEXT,canonical_id TEXT,payload TEXT,input_hash TEXT,
 PRIMARY KEY(source,record_id));
CREATE INDEX raw_canonical ON raw_records(canonical_id);
CREATE TABLE relations(child TEXT,predicate TEXT,parent TEXT,PRIMARY KEY(child,predicate,parent));
CREATE TABLE concepts(id TEXT PRIMARY KEY,payload TEXT);
CREATE TABLE english_labels(label TEXT,concept TEXT,PRIMARY KEY(label,concept));
CREATE INDEX english_lookup ON english_labels(label);
CREATE TABLE candidates(id TEXT PRIMARY KEY,zh TEXT,ru TEXT,domain TEXT,status TEXT,link_type TEXT,score INTEGER,payload TEXT);
CREATE INDEX candidate_pair ON candidates(zh,domain,ru);
CREATE TABLE candidate_aliases(alias TEXT,domain TEXT,candidate TEXT,PRIMARY KEY(alias,domain,candidate));
CREATE INDEX alias_lookup ON candidate_aliases(alias,domain);
CREATE TABLE conflicts(candidate TEXT,other TEXT,reason TEXT,PRIMARY KEY(candidate,other,reason));
CREATE TABLE reviews(candidate TEXT PRIMARY KEY,decision TEXT,payload TEXT);
CREATE TABLE errors(source TEXT,input_hash TEXT,offset INTEGER,code TEXT,PRIMARY KEY(source,input_hash,offset));
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
PRAGMA user_version=1;
'''


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA trusted_schema=OFF')
            con.execute('PRAGMA journal_mode=WAL')
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version == 0:
                con.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            elif version != 1:
                raise HarvestError('Неизвестная версия build database.')
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def source_add(self, metadata, *, dry_run=False):
        validate_source(metadata)
        if dry_run:
            return metadata
        with self.connect() as con:
            old = con.execute('SELECT metadata FROM sources WHERE id=?', (metadata['source_id'],)).fetchone()
            data = canonical_json(metadata)
            if old and old[0] != data:
                raise HarvestError('Pinned source metadata неизменяемы: задайте новый source_id для новой ревизии.')
            con.execute('INSERT OR IGNORE INTO sources VALUES(?,?)', (metadata['source_id'], data))
