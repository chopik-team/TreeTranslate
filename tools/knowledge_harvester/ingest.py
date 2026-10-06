from dataclasses import asdict
import gzip
import bz2
import json
from pathlib import Path
from .models import HarvestError
from .sources import ADAPTERS
from .config import fingerprint
from .provenance import file_hash, canonical_json
from .normalization import normalize


def validate(record, source, config):
    if len(record.aliases) > 16 or sum(len(v) for v in record.aliases.values()) > config['max_aliases']:
        raise HarvestError('alias_limit')
    for lang, term in record.labels.items():
        if lang.split('-')[0] not in source['languages']:
            raise HarvestError('unlicensed_language')
        if not isinstance(term, str) or not term.strip() or len(term) > config['max_term_chars'] or '\x00' in term:
            raise HarvestError('term_limit')
    for lang, aliases in record.aliases.items():
        if lang.split('-')[0] not in source['languages']:
            raise HarvestError('unlicensed_language')
        if any(not isinstance(v, str) or not v.strip() or len(v) > config['max_term_chars'] or '\x00' in v for v in aliases):
            raise HarvestError('alias_limit')
    if len(record.mappings) > 1:
        raise HarvestError('ambiguous_explicit_mapping')
    payload = asdict(record)
    payload['normalized_labels'] = {k: normalize(v) for k, v in record.labels.items()}
    return payload


def ingest(store, path, source_id, adapter, config, *, sample=None, dry_run=False):
    if sample is not None and sample <= 0:
        raise HarvestError('--sample должен быть положительным.')
    path = Path(path)
    if adapter not in ADAPTERS:
        raise HarvestError('Неизвестный adapter.')
    digest = file_hash(path)
    config_hash = fingerprint(config)
    if dry_run:
        return {'sha256': digest, 'adapter': adapter, 'sample': sample}
    with store.connect() as con:
        found = con.execute('SELECT metadata FROM sources WHERE id=?', (source_id,)).fetchone()
        if not found:
            raise HarvestError('Сначала зарегистрируйте source metadata.')
        source = json.loads(found[0])
        if source.get('input_sha256') and source['input_sha256'] != digest:
            raise HarvestError('Input SHA256 не соответствует pinned source metadata.')
        checkpoint = con.execute('SELECT * FROM files WHERE hash=? AND source=?', (digest, source_id)).fetchone()
        if checkpoint and (checkpoint['config'] != config_hash or checkpoint['adapter'] != adapter):
            raise HarvestError('Resume требует тот же adapter/config.')
        offset, processed = (checkpoint['offset'], checkpoint['records']) if checkpoint else (0, 0)
        if checkpoint and checkpoint['complete']:
            return {'sha256': digest, 'processed': processed, 'resumed': True, 'complete': True}
        con.execute('INSERT OR IGNORE INTO files(hash,source,adapter,path,config) VALUES(?,?,?,?,?)',
                    (digest, source_id, adapter, str(path.resolve()), config_hash))
        con.commit()
        opener = gzip.open if path.suffix == '.gz' else bz2.open if path.suffix == '.bz2' else open
        accepted = rejected = current = 0
        with opener(path, 'rb') as stream:
            stream.seek(offset)  # gzip/bz2 replay decompression; uncompressed JSONL seeks directly.
            while sample is None or current < sample:
                start = stream.tell()
                line = stream.readline(config['max_record_bytes'] + 1)
                if not line:
                    con.execute('UPDATE files SET complete=1 WHERE hash=? AND source=?', (digest, source_id))
                    break
                oversized = len(line) > config['max_record_bytes']
                if oversized:
                    while line and not line.endswith(b'\n'):
                        line = stream.readline(config['max_record_bytes'] + 1)
                        if stream.tell() > config['max_decompressed_bytes']:
                            raise HarvestError('decompression_limit')
                if stream.tell() > config['max_decompressed_bytes']:
                    raise HarvestError('decompression_limit')
                current += 1; processed += 1
                try:
                    if oversized:
                        raise HarvestError('record_limit')
                    text = line.decode('utf-8').strip()
                    if text in ('', '[', ']') or adapter == 'cedict' and text.startswith('#'):
                        continue
                    record = ADAPTERS[adapter](text if adapter == 'cedict' else json.loads(text.rstrip(',')))
                    payload = validate(record, source, config)
                    payload.update(source=source_id, input_hash=digest, input_offset=start,
                                   original_languages=sorted(record.labels))
                    canonical = record.mappings[0] if record.mappings else record.concept_id
                    before = con.total_changes
                    con.execute('INSERT OR IGNORE INTO raw_records VALUES(?,?,?,?,?,?)',
                                (source_id, record.source_record_id, record.concept_id, canonical, canonical_json(payload), digest))
                    if con.total_changes > before:
                        accepted += 1
                        con.execute("INSERT INTO metadata VALUES('data_revision','1') ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")
                        con.executemany('INSERT OR IGNORE INTO relations VALUES(?,?,?)',
                                        [(canonical, prop, parent) for prop, parent in record.relations])
                except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
                    rejected += 1
                    con.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?,?)',
                                (source_id, digest, start, str(error) if isinstance(error, HarvestError) else type(error).__name__))
                finally:
                    con.execute('UPDATE files SET offset=?,records=? WHERE hash=? AND source=?', (stream.tell(), processed, digest, source_id))
                    if current % config['batch_size'] == 0:
                        con.commit()
        return {'sha256': digest, 'processed': processed, 'accepted_this_run': accepted, 'rejected_this_run': rejected,
                'offset': stream.tell() if not stream.closed else con.execute('SELECT offset FROM files WHERE hash=? AND source=?', (digest, source_id)).fetchone()[0]}
