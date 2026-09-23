import json
from functools import lru_cache
from app.config.paths import ASSETS_DIR


@lru_cache(maxsize=1)
def configuration():
    return json.loads((ASSETS_DIR / 'config/ocr.json').read_text('utf-8'))


def profile(name):
    key = str(getattr(name, 'value', name)).lower()
    return configuration()['profiles'][key]
