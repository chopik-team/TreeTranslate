from hashlib import sha256
import re
from ..models import RawConcept, HarvestError

LINE = re.compile(r'^(\S+) (\S+) \[([^\]]+)\] /(.+)/$')


def parse(line):
    match = LINE.fullmatch(line.strip())
    if not match:
        raise HarvestError('Некорректная строка CC-CEDICT.')
    traditional, simplified, pinyin, senses = match.groups()
    definitions = senses.split('/')
    uid = sha256(line.encode('utf-8')).hexdigest()
    # Definitions are not preferred English labels and never directly align to Russian.
    return RawConcept(uid, 'cedict:' + uid, {'zh-hans': simplified, 'zh-hant': traditional},
                      definitions=definitions, metadata={'pinyin': pinyin, 'original_line': line})
