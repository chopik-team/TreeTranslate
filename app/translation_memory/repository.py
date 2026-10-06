from datetime import datetime, timezone
import math
import re

from .errors import InvalidMemoryData
from .models import Status, TranslationUnit, TRUST
from .normalization import digest, normalize, fuzzy_keys, SLOT


def now():
    return datetime.now(timezone.utc).isoformat()


def validate(entry):
    allowed = {'source_language', 'target_language', 'source_text', 'target_text', 'domain', 'context',
               'origin', 'status', 'quality', 'document_type', 'source_document', 'engine_origin',
               'confirmed_by_user', 'is_template', 'created_at', 'updated_at'}
    if not isinstance(entry, dict) or set(entry) - allowed:
        raise InvalidMemoryData('Неизвестные поля записи памяти.')
    row = dict(entry)
    for key in ('source_language', 'target_language'):
        value = row.get(key, '')
        if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{2,8})*', value) or value.lower() == 'auto':
            raise InvalidMemoryData('Нужна явная языковая пара.')
        row[key] = value.lower()
    for key in ('source_text', 'target_text'):
        if not isinstance(row.get(key), str) or not row[key].strip() or len(row[key]) > 20000 or '\x00' in row[key]:
            raise InvalidMemoryData('Недопустимая длина или формат сегмента.')
    for key, default, limit in [('domain', 'general', 128), ('context', '', 2048), ('origin', 'user', 256),
                                ('document_type', '', 64), ('source_document', '', 256), ('engine_origin', '', 128)]:
        row.setdefault(key, default)
        if not isinstance(row[key], str) or len(row[key]) > limit:
            raise InvalidMemoryData('Недопустимые метаданные памяти.')
    try:
        row['status'] = Status(row.get('status', Status.AUTO))
        row['quality'] = float(row.get('quality', 1.0))
    except (ValueError, TypeError):
        raise InvalidMemoryData('Недопустимый статус или оценка качества.') from None
    if not math.isfinite(row['quality']) or not 0 <= row['quality'] <= 1:
        raise InvalidMemoryData('Оценка качества должна быть от 0 до 1.')
    row['confirmed_by_user'] = row['status'] == Status.CONFIRMED
    row['is_template'] = bool(row.get('is_template', False))
    if row['is_template']:
        if any(row[k].count(SLOT) != 1 or '{' in row[k].replace(SLOT, '') or '}' in row[k].replace(SLOT, '')
               for k in ('source_text', 'target_text')):
            raise InvalidMemoryData('Шаблон должен содержать ровно один NUMBER_1 в каждой части.')
        # A single explicit slot; never infer an alignment or grammatical agreement.
        if any(re.search(r'\d', row[k].replace(SLOT, '')) for k in ('source_text', 'target_text')):
            raise InvalidMemoryData('Числа вне параметра шаблона не поддерживаются.')
    row['source_normalized'] = normalize(row['source_text'])
    row['source_hash'] = digest(row['source_text'])
    row['normalized_hash'] = digest(row['source_normalized'])
    row['created_at'] = row['updated_at'] = now()
    return row


def unit(row):
    return TranslationUnit(**{k: row[k] for k in TranslationUnit.__dataclass_fields__})


class Repository:
    def __init__(self, database):
        self.db = database

    def insert_many(self, entries):
        ids = []
        with self.db.connect(write=True) as con:
            for entry in entries:
                row = validate(entry)
                keys = list(row)
                values = [row[k] for k in keys]
                existing = con.execute('''SELECT id,status FROM units WHERE source_language=? AND target_language=?
                    AND source_normalized=? AND target_text=? AND domain=? AND context=? AND is_template=?''',
                    [row[k] for k in ('source_language','target_language','source_normalized','target_text','domain','context','is_template')]).fetchone()
                if existing:
                    uid = existing['id']
                    # Imports must not silently demote confirmations or revive rejection.
                    if existing['status'] != Status.REJECTED and TRUST[row['status']] > TRUST[existing['status']]:
                        con.execute('UPDATE units SET status=?,confirmed_by_user=?,updated_at=? WHERE id=?',
                                    (row['status'], row['confirmed_by_user'], now(), uid))
                else:
                    uid = con.execute(f'INSERT INTO units ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})', values).lastrowid
                    con.executemany('INSERT INTO fuzzy_keys VALUES (?,?,?)',
                        ((row['source_language']+'>'+row['target_language'], key, uid) for key in fuzzy_keys(row['source_normalized'])))
                ids.append(uid)
        return ids

    def status(self, uid, status):
        status = Status(status)
        with self.db.connect(write=True) as con:
            con.execute('UPDATE units SET status=?,confirmed_by_user=?,updated_at=? WHERE id=?',
                        (status, status == Status.CONFIRMED, now(), uid))

    def touch(self, uid):
        with self.db.connect(write=True) as con:
            con.execute('UPDATE units SET use_count=use_count+1,last_used_at=? WHERE id=?', (now(), uid))

    def rows(self):
        # A stable SQLite snapshot, streamed without loading the whole TM.
        with self.db.connect() as con:
            for row in con.execute('SELECT * FROM units ORDER BY id'):
                yield dict(row)
