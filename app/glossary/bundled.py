"""Read-only packaged knowledge, prepared explicitly by developer tools."""
from hashlib import sha256
import json
import logging
from app.config.paths import ASSETS_DIR


def bundled_paths(root=None):
    root = ASSETS_DIR / 'knowledge' if root is None else root
    manifest = root / 'manifest.json'
    if not manifest.is_file():
        return ()
    paths = []
    try:
        data = json.loads(manifest.read_text('utf-8'))
        if data.get('version') != 1:
            raise ValueError('version')
        for entry in data['packs']:
            path = (root / entry['file']).resolve()
            if not path.is_relative_to(root.resolve()) or path.suffix != '.db':
                raise ValueError('path')
            digest=sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
            if digest.hexdigest() != entry['sha256']:
                raise ValueError('checksum')
            paths.append(path)
    except (OSError,ValueError,KeyError,TypeError):
        logging.getLogger('treetranslate.glossary').warning('Bundled knowledge unavailable; user glossary and models remain available')
        return ()
    return tuple(paths)
