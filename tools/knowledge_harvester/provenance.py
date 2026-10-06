from hashlib import sha256
import json


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest_json(value):
    return sha256(canonical_json(value).encode('utf-8')).hexdigest()


def file_hash(path):
    digest = sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
