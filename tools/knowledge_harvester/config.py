import json
from pathlib import Path
from .models import HarvestError
from .provenance import digest_json

DEFAULT_PATH = Path(__file__).with_name('policy.json')


def load(path=None):
    config = json.loads(Path(path or DEFAULT_PATH).read_text('utf-8'))
    if config.get('version') != 1:
        raise HarvestError('Неподдерживаемая версия harvest policy.')
    for key in ('max_record_bytes', 'max_aliases', 'max_term_chars', 'max_decompressed_bytes', 'batch_size', 'max_traversal_nodes'):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise HarvestError('Некорректный лимит harvest policy.')
    return config


def fingerprint(config):
    return digest_json(config)
