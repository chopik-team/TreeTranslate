"""Stream official AGROVOC LOD N-Triples into the existing JSONL adapter contract.

Build-only SQLite staging, resumable ZIP decompression, no runtime dependency.
Only materialized SKOS labels in the licensed ZH/RU/EN languages are exported.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
from zipfile import ZipFile

from .models import HarvestError
from .provenance import canonical_json, file_hash
from .sources.agrovoc import SKOS

CONCEPT = 'http://aims.fao.org/aos/agrovoc/c_'
PREDICATES = {SKOS + p for p in ('prefLabel', 'altLabel', 'definition', 'broader', 'exactMatch')}
TRIPLE = re.compile(r'^<([^>]+)>\s+<([^>]+)>\s+(.+)\s+\.\s*$')
LITERAL = re.compile(r'^"((?:[^"\\]|\\.)*)"@([a-zA-Z-]+)$')
ESCAPE = re.compile(r'\\(U[0-9A-Fa-f]{8}|u[0-9A-Fa-f]{4}|[tbnrf"\\])')


def literal(value):
    def replace(match):
        token = match[1]
        return chr(int(token[1:], 16)) if token[0] in 'uU' else {
            't': '\t', 'b': '\b', 'n': '\n', 'r': '\r', 'f': '\f', '"': '"', '\\': '\\'
        }[token]
    # Reject unsupported escapes rather than silently changing a source label.
    if re.search(r'\\.', ESCAPE.sub('', value)):
        raise HarvestError('Unsupported N-Triples literal escape')
    return ESCAPE.sub(replace, value)


def convert(archive_path, output, *, staging, max_uncompressed=2 * 1024**3):
    archive_path, output, staging = map(Path, (archive_path, output, staging))
    if output.exists():
        raise HarvestError('JSONL output already exists; use a new output path.')
    staging.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = file_hash(archive_path)
    con = sqlite3.connect(staging)
    try:
        con.executescript('''CREATE TABLE IF NOT EXISTS facts(
            subject TEXT,predicate TEXT,value TEXT,language TEXT,is_uri INTEGER,
            PRIMARY KEY(subject,predicate,value,language));
            CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY,payload TEXT);''')
        saved = con.execute('SELECT payload FROM state WHERE id=1').fetchone()
        state = json.loads(saved[0]) if saved else dict(sha256=digest, offset=0, lines=0, complete=False, modified=[])
        if state['sha256'] != digest:
            raise HarvestError('Staging belongs to a different source SHA256.')
        with ZipFile(archive_path) as archive:
            members = [entry for entry in archive.infolist() if entry.filename.endswith('.nt')]
            if len(members) != 1 or members[0].file_size > max_uncompressed:
                raise HarvestError('Expected one bounded N-Triples member.')
            member = members[0]
            if not state['complete']:
                with archive.open(member) as stream:
                    stream.seek(state['offset'])
                    while True:
                        line = stream.readline(4 * 1024**2 + 1)
                        if not line:
                            break
                        if len(line) > 4 * 1024**2:
                            raise HarvestError('N-Triples record limit')
                        state['lines'] += 1
                        if b'<http://aims.fao.org/aos/agrovoc> <http://purl.org/dc/terms/modified>' in line:
                            state['modified'].append(line.decode('utf-8').strip())
                        if b'http://www.w3.org/2004/02/skos/core#' in line:
                            match = TRIPLE.fullmatch(line.decode('utf-8').strip())
                            if match and match[1].startswith(CONCEPT) and match[2] in PREDICATES:
                                subject, predicate, obj = match.groups()
                                if predicate in (SKOS + 'broader', SKOS + 'exactMatch'):
                                    if obj.startswith('<') and obj.endswith('>'):
                                        con.execute('INSERT OR IGNORE INTO facts VALUES(?,?,?,?,1)', (subject, predicate, obj[1:-1], ''))
                                else:
                                    label = LITERAL.fullmatch(obj)
                                    if label and label[2].lower() in ('zh', 'ru', 'en'):
                                        con.execute('INSERT OR IGNORE INTO facts VALUES(?,?,?,?,0)', (subject, predicate, literal(label[1]), label[2].lower()))
                        if state['lines'] % 10000 == 0:
                            state['offset'] = stream.tell()
                            con.execute('INSERT OR REPLACE INTO state VALUES(1,?)', (canonical_json(state),))
                            con.commit()
                    state.update(offset=stream.tell(), complete=True)
                    con.execute('INSERT OR REPLACE INTO state VALUES(1,?)', (canonical_json(state),))
                    con.commit()
            counts = Counter()
            with output.open('x', encoding='utf-8', newline='\n') as target:
                for (subject,) in con.execute('SELECT DISTINCT subject FROM facts ORDER BY subject'):
                    node = {'@id': subject}
                    for predicate, value, language, is_uri in con.execute(
                        'SELECT predicate,value,language,is_uri FROM facts WHERE subject=? ORDER BY predicate,language,value', (subject,)):
                        node.setdefault(predicate, []).append({'@id': value} if is_uri else {'@language': language, '@value': value})
                        counts[predicate.rsplit('#', 1)[-1] + ':' + language] += 1
                    target.write(canonical_json(node) + '\n')
                    counts['concepts'] += 1
        result = dict(archive_sha256=digest, archive_bytes=archive_path.stat().st_size,
                      member=member.filename, uncompressed_bytes=member.file_size, jsonl_sha256=file_hash(output),
                      counts=dict(counts), state=state, languages=['zh', 'ru', 'en'])
        output.with_suffix('.conversion.json').write_text(canonical_json(result) + '\n', 'utf-8')
        return result
    finally:
        con.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--staging', type=Path, required=True)
    args = parser.parse_args()
    print(canonical_json(convert(args.archive, args.output, staging=args.staging)))
