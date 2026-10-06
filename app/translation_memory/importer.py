"""Imports are untrusted unless the caller explicitly opts into trusted data."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from .errors import InvalidMemoryData
from .models import Status

MAX_PACKAGE_BYTES = 256 * 1024 * 1024


def checked_path(path):
    path = Path(path)
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        raise InvalidMemoryData('Пакет памяти превышает 256 МиБ.')
    return path


def import_memory(repository, path, *, trusted=False):
    def entries():
        with checked_path(path).open(encoding='utf-8') as stream:
            try:
                header = json.loads(stream.readline(131072))
                if header.get('format') != 'TreeTranslate.tmemory' or header.get('version') != 1 or header.get('schema_version') != 1:
                    raise InvalidMemoryData('Версия пакета памяти не поддерживается.')
                for line in stream:
                    if len(line) > 131072:
                        raise InvalidMemoryData('Запись пакета слишком велика.')
                    row = json.loads(line)
                    # An imported file cannot claim a local user confirmation.
                    row['status'] = Status.REJECTED if row.get('status') == Status.REJECTED else (Status.IMPORTED if trusted else Status.AUTO)
                    row['origin'] = 'tmemory-import'
                    row.pop('source_document', None)
                    yield row
            except (ValueError, TypeError, AttributeError, UnicodeError):
                raise InvalidMemoryData('Некорректный пакет памяти.') from None
    return len(repository.insert_many(entries()))


def import_tmx(repository, path, *, trusted=False, source_language=None, target_language=None):
    path = checked_path(path)
    # Reject DTD/entities before parsing, including UTF-16: support UTF-8 subset only.
    with path.open('rb') as stream:
        tail = b''
        for chunk in iter(lambda: stream.read(65536), b''):
            data = (tail+chunk).upper()
            if b'<!DOCTYPE' in data or b'<!ENTITY' in data or b'\x00' in data:
                raise InvalidMemoryData('TMX: DTD, сущности и UTF-16 не поддерживаются.')
            tail = data[-16:]
    def entries():
        default_source = source_language
        try:
            root = None
            for event, element in ET.iterparse(path, events=('start', 'end')):
                if root is None:
                    root = element
                    if root.tag != 'tmx' or root.get('version') not in ('1.4', '1.4b'):
                        raise InvalidMemoryData('Поддерживается базовый TMX 1.4/1.4b.')
                if event != 'end':
                    continue
                if element.tag == 'header':
                    default_source = source_language or element.get('srclang')
                if element.tag != 'tu':
                    continue
                src = source_language or element.get('srclang') or default_source
                variants = {}
                for tuv in element.findall('tuv'):
                    lang = tuv.get('{http://www.w3.org/XML/1998/namespace}lang', '').lower()
                    seg = tuv.find('seg')
                    if seg is None or len(seg):
                        raise InvalidMemoryData('TMX inline-коды не поддерживаются; импорт отменён.')
                    if lang in variants:
                        raise InvalidMemoryData('TMX содержит неоднозначные варианты языка.')
                    variants[lang] = seg.text or ''
                src = src.lower() if src else ''
                if src not in variants:
                    raise InvalidMemoryData('TMX: задайте исходный язык явно.')
                domain = next((p.text for p in element.findall('prop') if p.get('type') == 'domain'), 'general')
                for lang, text in variants.items():
                    if lang != src and (target_language is None or lang == target_language.lower()):
                        yield dict(source_language=src, target_language=lang, source_text=variants[src],
                                   target_text=text, domain=domain, origin='tmx-import',
                                   status=Status.IMPORTED if trusted else Status.AUTO)
                element.clear()
                # Clear the body incrementally to avoid retaining hundreds of thousands of nodes.
                body = root.find('body')
                if body is not None:
                    body.clear()
        except ET.ParseError:
            raise InvalidMemoryData('Некорректный TMX; импорт отменён.') from None
    return len(repository.insert_many(entries()))
