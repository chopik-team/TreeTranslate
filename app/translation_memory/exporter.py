"""Versioned streaming JSON-lines (.tmemory); explicit exports only."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from .models import Status

EXPORT_FIELDS = ('source_language', 'target_language', 'source_text', 'target_text', 'domain', 'context',
                 'origin', 'status', 'quality', 'created_at', 'updated_at', 'document_type',
                 'engine_origin', 'confirmed_by_user', 'is_template')


@contextmanager
def atomic_text(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.tm-export-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def export_memory(repository, path, *, confirmed_only=False):
    count = 0
    with repository.db.connect() as con:
        pairs = [list(r) for r in con.execute('SELECT DISTINCT source_language,target_language FROM units')]
        domains = [r[0] for r in con.execute('SELECT DISTINCT domain FROM units')]
        with atomic_text(path) as stream:
            stream.write(json.dumps(dict(format='TreeTranslate.tmemory', version=1, schema_version=1,
                                         language_pairs=pairs, domains=domains,
                                         provenance='explicit-local-export'), ensure_ascii=False)+'\n')
            for row in con.execute('SELECT * FROM units ORDER BY id'):
                if confirmed_only and row['status'] != Status.CONFIRMED:
                    continue
                stream.write(json.dumps({k: row[k] for k in EXPORT_FIELDS}, ensure_ascii=False)+'\n')
                count += 1
    return count


def export_dataset(repository, path):
    count = 0
    with atomic_text(path) as stream:
        for row in repository.rows():
            if row['status'] != Status.CONFIRMED or row['is_template']:
                continue
            stream.write(json.dumps({k: row[k] for k in ('source_text', 'target_text', 'source_language', 'target_language', 'domain')}, ensure_ascii=False)+'\n')
            count += 1
    return count


def export_tmx(repository, path):
    count = 0
    with atomic_text(path) as stream:
        stream.write('<?xml version="1.0" encoding="UTF-8"?>\n<tmx version="1.4">\n')
        header = ET.Element('header', creationtool='TreeTranslate', creationtoolversion='AW0.7',
                            segtype='sentence', **{'o-tmf': 'TreeTranslate', 'adminlang': 'en',
                                                   'srclang': '*all*', 'datatype': 'PlainText'})
        stream.write(ET.tostring(header, encoding='unicode')+'\n<body>\n')
        for row in repository.rows():
            if row['is_template'] or row['status'] in (Status.AUTO, Status.REJECTED):
                continue
            tu = ET.Element('tu', srclang=row['source_language'])
            ET.SubElement(tu, 'prop', type='domain').text = row['domain']
            for lang, text in ((row['source_language'], row['source_text']), (row['target_language'], row['target_text'])):
                tuv = ET.SubElement(tu, 'tuv', {'{http://www.w3.org/XML/1998/namespace}lang': lang})
                ET.SubElement(tuv, 'seg').text = text
            stream.write(ET.tostring(tu, encoding='unicode')+'\n')
            count += 1
        stream.write('</body>\n</tmx>\n')
    return count
